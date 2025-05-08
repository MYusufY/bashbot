# Project BashBot
In the past 3-4 years, i developed hundreds of versions of the BashBot - my open-source desktop robot project. Some of them were actually working in ESP32-2432S028 CYD with lvgl, while some of them were working completely in Bash.

This version of BashBot here is the Python one. I started out recently, so its not finished, we are just starting!

# Setup
As i said, the project itself and the documentation isnt in a stable version yet. But still, here's how you can run BashBot on your computer too.

1. Install the dependencies.
```bash
pip install -r requirements.txt
```
2. Edit your api.txt like this:
   First line should be the Gemini API key.
   Second line should be Groq API key - for Whisper!
3. Run main.py
```bash
python3 main.py
```
# Notes
Full documentation + improved BashBot will be coming soon!
