# JARVIS-YOUR-PERSONAL-ASSISTANT
Hindi voice assistant in Python with wake word, dark GUI, Wikipedia, weather and notes YOUR VOICE,YOUR COMMAND
# Jarvis

A Hindi/English voice assistant for Windows, written in Python. It has a simple desktop window (Tkinter), listens to your voice or typed commands, and talks back.

Built by Devansh.

## Features

- Voice input (tap the mic button) and typed commands (press Enter)
- Wake word: say "Jarvis" and it starts listening. Can be turned on or off with a checkbox
- Speaks replies out loud (picks a Hindi voice if your PC has one)
- Time and date
- Weather for a city (uses Open-Meteo, no key needed). Default city is Delhi
- Wikipedia summaries (tries Hindi first, then English)
- Calculator for simple maths
- Google search and YouTube search/play in your browser
- Opens sites: YouTube, Gmail, WhatsApp Web, Instagram, Facebook, Google Maps, Google
- Notes: say "note likho ..." to save, "mere notes" to read the last 5
- Screenshots (saved in a `screenshots` folder)
- Jokes and small talk (hello, how are you, thanks, good morning, good night)
- Optional AI chatbot: if you add your own API key, Jarvis can answer other questions. Works fine without it

Commands work in Hindi (Devanagari) and Roman Hindi / English.

## Install

You need Python 3.8 or newer (Windows).

```
py -m pip install SpeechRecognition pyttsx3 pyaudio pillow
```

Tkinter comes with the normal Python installer. If you get a "tkinter nahi mila" message, reinstall Python with tcl/tk.

## Run

```
py jarvis_v4.py
```

## Wake word

Keep the "Wake word: 'Jarvis'" box ticked. Say "Jarvis" (or "Jarvis time batao" in one go) and the app will respond "जी, बोलिए" and listen for your command.

## Optional: AI chatbot

On first run Jarvis creates `jarvis_config.json` next to the script. You can change `city` there. To use the AI chatbot, either put your key in `api_key` in that file, or set the environment variable `JARVIS_API_KEY`. Leave it empty to skip.

## Privacy

- Your voice is sent to Google's speech recognition service to turn it into text, so you need internet.
- Weather and Wikipedia commands make web requests. If you turn on the AI chatbot, your messages go to the API provider you set.
- No API keys are included in this repo. Never commit your own key. `.gitignore` already skips `jarvis_config.json` and `jarvis_notes.txt`.

## हिंदी में

Jarvis एक हिंदी voice assistant है जो Python में बना है। आप बोलकर या टाइप करके समय, तारीख, मौसम, Wikipedia, Google/YouTube search, नोट्स और screenshot जैसे काम करवा सकते हैं।

चलाने के लिए: पहले `py -m pip install SpeechRecognition pyttsx3 pyaudio pillow`, फिर `py jarvis_v4.py`। "Jarvis" बोलने पर यह सुनना शुरू करता है।



## Credit

Built by Devansh.
