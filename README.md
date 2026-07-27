# Socratic Voice Tutor

A hands-free, voice-to-voice Socratic study partner for your macOS terminal using the Google Gemini API.

## Prerequisites

Ensure you have `ffmpeg` installed to support microphone capture:

```bash
brew install ffmpeg
```

## Installation & Running

1. Open your terminal in the directory.
2. Run the tutor script:

```bash
python3 socratic_tutor.py
```

*Note: On your first run, you will be prompted to enter your Gemini API Key from Google AI Studio. It will be securely cached locally for future sessions.*
