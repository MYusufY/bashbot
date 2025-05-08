import pygame
import pygame.camera
from pygame.locals import *
import sys
import sounddevice as sd
import soundfile as sf
import numpy as np
import os
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

eye_width, eye_height = 100, 150
eye_color = (0, 255, 0)
blink_time = 0
recording = False
vision_input = False
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

cam_list = pygame.camera.list_cameras()
if not cam_list:
    print("No cameras found!")
camera = pygame.camera.Camera(cam_list[0])
camera.start()

try:
    with open("api.txt", "r") as f:
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
        await communicate.save("response.mp3")
        os.system("mpg123 response.mp3 &") 
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

def get_gemini_response(text, use_vision=False):
    client = genai.Client(api_key=api_keys[0])
    
    if not use_vision:
        print("Using regular text mode")
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=text)],
            ),
        ]
        generate_content_config = types.GenerateContentConfig(
            response_mime_type="text/plain",
            system_instruction=[
                types.Part.from_text(text="Your name is bashbot. Answer the questions shortly, funny. Dont use emojis."),
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
    else:
        print("Using vision mode")
        image = camera.get_image()        
        pygame.image.save(image, "temp_img.jpg")
        
        with open('temp_img.jpg', 'rb') as f:
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
                types.Part.from_text(text="Your name is bashbot. Answer the questions shortly, funny. Dont use emojis."),
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

async def main_loop():
    global recording, audio_frames, stream, transcription_text, gemini_response
    global typing_text, typing_index, typing_delay, last_dot_change
    global listening_dots, tts_task, running, text_alpha, text_fade_start, text_display_start
    global vision_input
    
    blink_time = 0

    running = True
    while running:
        current_time = pygame.time.get_ticks()
        for event in pygame.event.get():
            if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE and not recording:
                recording = True
                vision_input = False
                audio_frames = []
                stream = sd.InputStream(callback=record_callback, channels=1, samplerate=sample_rate)
                stream.start()
                listening_dots = 0
                last_dot_change = current_time
            elif event.type == pygame.KEYUP and event.key == pygame.K_SPACE and recording:
                recording = False
                stream.stop()
                stream.close()
                if audio_frames:
                    audio_data = np.concatenate(audio_frames)
                    sf.write('recording.mp3', audio_data, sample_rate)
                    transcription_text = transcribe_audio('recording.mp3')
                    gemini_response = get_gemini_response(transcription_text, use_vision=False)
                    typing_text = gemini_response
                    typing_index = 0
                    typing_delay = 0
                    if tts_task and not tts_task.done():
                        tts_task.cancel()
                    tts_task = asyncio.create_task(speak_text(gemini_response))
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_a and not recording:
                recording = True
                vision_input = True
                audio_frames = []
                stream = sd.InputStream(callback=record_callback, channels=1, samplerate=sample_rate)
                stream.start()
                listening_dots = 0
                last_dot_change = current_time
            elif event.type == pygame.KEYUP and event.key == pygame.K_a and recording:
                recording = False
                stream.stop()
                stream.close()
                if audio_frames:
                    audio_data = np.concatenate(audio_frames)
                    sf.write('recording.mp3', audio_data, sample_rate)
                    transcription_text = transcribe_audio('recording.mp3')
                    gemini_response = get_gemini_response(transcription_text, use_vision=vision_input)
                    typing_text = gemini_response
                    typing_index = 0
                    typing_delay = 0
                    if tts_task and not tts_task.done():
                        tts_task.cancel()
                    tts_task = asyncio.create_task(speak_text(gemini_response))
                vision_input = False

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
            status_text = font.render(f"{'Looking & Listening' if vision_input else 'Listening'}{dots}", True, (255, 255, 255))
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