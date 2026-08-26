# Voice Search

A desktop voice search launcher written in Python.

It listens for a wake word or global hotkey, records a spoken query, converts it to text, lets you review it, and opens the selected search engine in your browser.

## Features

- Wake word activation
- Global hotkey
- Live microphone level meter
- Search confirmation window
- Multiple search destinations
- Math symbol conversion
- Cross-platform Python implementation

## Requirements

- Python 3.11+
- PyAudio
- NumPy
- SpeechRecognition
- OpenWakeWord
- pynput

## Installation

```bash
git clone https://github.com/username/voice-search.git
cd voice-search
pip install -r requirements.txt
python voice_search.py