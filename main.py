import pygame
import pygame.camera
from pygame.locals import *
import sys
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
import time
import asyncio
import edge_tts
from groq import Groq
from google import genai
from google.genai import types

pygame.init()
screen = pygame.display.set_mode((0,0), pygame.FULLSCREEN)
width, height = screen.get_size()
clock = pygame.time.Clock()
font = pygame.font.SysFont('Arial', 30)
pygame.camera.init()
pygame.mouse.set_visible(False)

eye_width, eye_height = 100, 150
eye_color = (0, 255, 0)
blink_time = 0
recording = False
audio_frames = []
sample_rate = 16000
stream = None
transcription_text = ""
gemini_response = ""
api_keys = []
listening_dots = 0
typing_text = ""
typing_index = 0
typing_delay = 0
last_dot_change = 0
dot_change_interval = 750
tts_task = None
text_alpha = 0
text_fade_start = 0
text_fade_duration = 0
text_display_start = 0
exit_area_size = 80
mouse_recording = False

cam_list = pygame.camera.list_cameras()
if not cam_list:
    print("No cameras found!")
camera = pygame.camera.Camera(cam_list[0])
camera.start()

try:
    with open("/home/pi/Desktop/bashbot/api.txt", "r") as f:
        api_keys = [line.strip() for line in f.readlines()]
    if len(api_keys) < 2:
        print("Error: api.txt needs 2 lines (Gemini and Groq keys)")
        sys.exit()
except FileNotFoundError:
    print("Error: api.txt not found")
    sys.exit()

async def speak_text(text):
    global text_display_start, text_fade_duration
    try:
        communicate = edge_tts.Communicate(text)
        await communicate.save("/home/pi/Desktop/bashbot/response.mp3")
        os.system("mpg123 /home/pi/Desktop/bashbot/response.mp3 &") 
        text_fade_duration = len(text) * 50 + 3600
        text_display_start = pygame.time.get_ticks()
    except Exception as e:
        print(f"Error in text-to-speech: {e}")

def record_callback(indata, frames, time, status):
    if recording:
        audio_frames.append(indata.copy())

def transcribe_audio(filename):
    client = Groq(api_key=api_keys[1])
    with open(filename, "rb") as file:
        try:
            transcription = client.audio.transcriptions.create(
                file=(filename, file.read()),
                model="whisper-large-v3",
                response_format="text",
            )
            return transcription
        except Exception as e:
            print(f"Transcription error: {e}")
            return "Error in transcription"

def get_gemini_response(text):
    client = genai.Client(api_key=api_keys[0])
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=text)],
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        response_mime_type="text/plain",
        system_instruction=[
            types.Part.from_text(text="Your name is BashBot. Answer the questions shortly, funny. Dont use emojis. If the prompt requires vision capabilites, like 'What color is this?', 'What am i holding?', 'What is this?' etc. just say 'bbc_vision' and dont say anything else."),
        ],
    )
    response = ""
    for chunk in client.models.generate_content_stream(
        model="gemini-2.0-flash",
        contents=contents,
        config=generate_content_config,
    ):
        if chunk.text:
            response += chunk.text
        
        if "bbc_vision" in response and len(response)<=12:
            print("Using vision mode")
            os.remove("/home/pi/Desktop/bashbot/temp_img.jpg")
            camera.stop()
            time.sleep(0.5)
            camera.start()
            image = camera.get_image()
            pygame.image.save(image, "/home/pi/Desktop/bashbot/temp_img.jpg")

            with open('/home/pi/Desktop/bashbot/temp_img.jpg', 'rb') as f:
                image_bytes = f.read()

            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(
                            data=image_bytes,
                            mime_type='image/jpeg'
                        ),
                        types.Part.from_text(text=text)
                    ]
                )
            ]
            
            generate_content_config = types.GenerateContentConfig(
                response_mime_type="text/plain",
                system_instruction=[
                    types.Part.from_text(text="Your name is BashBot. Answer the questions shortly, funny. Dont use emojis."),
                ],
            )
            
            response = ""
            for chunk in client.models.generate_content_stream(
                model="gemini-2.0-flash",
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    response += chunk.text
    
    return response

def start_recording():
    global recording, audio_frames, stream, listening_dots, last_dot_change
    recording = True
    audio_frames = []
    stream = sd.InputStream(callback=record_callback, channels=1, samplerate=sample_rate)
    stream.start()
    listening_dots = 0
    last_dot_change = pygame.time.get_ticks()

def stop_recording():
    global recording, stream, transcription_text, gemini_response, typing_text, typing_index, typing_delay, tts_task
    recording = False
    stream.stop()
    stream.close()
    if audio_frames:
        audio_data = np.concatenate(audio_frames)
        sf.write('/home/pi/Desktop/bashbot/recording.mp3', audio_data, sample_rate)
        transcription_text = transcribe_audio('/home/pi/Desktop/bashbot/recording.mp3')
        gemini_response = get_gemini_response(transcription_text)
        typing_text = gemini_response
        typing_index = 0
        typing_delay = 0
        if tts_task and not tts_task.done():
            tts_task.cancel()
        tts_task = asyncio.create_task(speak_text(gemini_response))

def is_in_exit_area(pos):
    return pos[0] < exit_area_size and pos[1] < exit_area_size

async def main_loop():
    global recording, audio_frames, stream, transcription_text, gemini_response
    global typing_text, typing_index, typing_delay, last_dot_change
    global listening_dots, tts_task, running, text_alpha, text_fade_start, text_display_start
    global mouse_recording
    
    blink_time = 0

    running = True
    while running:
        current_time = pygame.time.get_ticks()
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and not recording:
                start_recording()
            elif event.type == pygame.KEYUP and event.key == pygame.K_SPACE and recording:
                stop_recording()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if is_in_exit_area(event.pos):
                    running = False
                elif not recording and not mouse_recording:
                    mouse_recording = True
                    start_recording()
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and mouse_recording:
                mouse_recording = False
                if recording:
                    stop_recording()

        screen.fill((0, 0, 0))

        blink_time = (blink_time + 1) % 100
        current_height = eye_height if blink_time < 90 else 10
        left_eye_rect = pygame.Rect(width//2 - 150, height//2 - current_height//2, eye_width, current_height)
        right_eye_rect = pygame.Rect(width//2 + 50, height//2 - current_height//2, eye_width, current_height)
        pygame.draw.rect(screen, eye_color, left_eye_rect)
        pygame.draw.rect(screen, eye_color, right_eye_rect)

        if recording:
            if current_time - last_dot_change >= dot_change_interval:
                last_dot_change = current_time
                listening_dots = (listening_dots + 1) % 4
            dots = "." * listening_dots
            status_text = font.render(f"{'Listening'}{dots}", True, (255, 255, 255))
            screen.blit(status_text, (width//2 - status_text.get_width()//2, height//2 + 100))
        
        if typing_text and text_display_start > 0:
            elapsed = current_time - text_display_start
            
            if elapsed < text_fade_duration:
                progress = elapsed / text_fade_duration
                text_alpha = int(255 * (1 - progress**2))
                
                typing_delay += 1
                if typing_delay >= 3:
                    typing_delay = 0
                    if typing_index < len(typing_text):
                        typing_index += 1
                
                displayed_text = typing_text[:typing_index]
                lines = []
                current_line = ""
                for word in displayed_text.split(' '):
                    test_line = current_line + word + ' '
                    if font.size(test_line)[0] < width - 100:
                        current_line = test_line
                    else:
                        lines.append(current_line)
                        current_line = word + ' '
                if current_line:
                    lines.append(current_line)
                
                for i, line in enumerate(lines):
                    text_surface = font.render(line, True, (255, 255, 255))
                    text_surface.set_alpha(text_alpha)
                    screen.blit(text_surface, (width//2 - text_surface.get_width()//2, height//2 + 150 + i*30))
            else:
                typing_text = ""
                text_display_start = 0

        pygame.display.flip()
        await asyncio.sleep(0)
        clock.tick(60)

    if stream and stream.active:
        stream.stop()
        stream.close()
    camera.stop()
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    asyncio.run(main_loop())
