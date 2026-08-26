# Voice Search Launcher

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat\&logo=python\&logoColor=white)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%7C%20Windows%20%7C%20macOS-lightgrey?style=flat)](#prerequisites)
[![Wake Word](https://img.shields.io/badge/Wake%20Word-openWakeWord-4CAF50?style=flat)](#how-it-works)
[![GUI](https://img.shields.io/badge/GUI-Tkinter-FF9800?style=flat)](#tech-stack)
[![License](https://img.shields.io/badge/License-MIT-blue?style=flat)](LICENSE)

A small desktop voice-to-search launcher written in Python.

Say **"Alexa"** or press **Ctrl + Shift + `**, speak a search query, review the transcription, and open the search in your preferred destination.

> **Speak → Review → Search.**
>
> That's pretty much the whole idea.

---

## About

This is a personal project built while I am still learning programming.

I'm a **beginner developer**, so this project is definitely not perfect. There are probably bugs, questionable design decisions, code that could be cleaner, and things that experienced developers will immediately notice.

That's part of why I'm putting it on GitHub.

If you find something that is broken, inefficient, unnecessarily complicated, or just plain stupid, **feel free to open an issue or submit a pull request.** I'm here to learn.

And if you see something in the code and think:

> "Why on Earth did he do it this way?"

There is a reasonable chance I asked myself the same question three weeks later.

Constructive feedback is very welcome.

---

## Screenshots

### Idle

![Status window - idle](screenshots/status-window-off.png)

### Listening

![Status window - listening](screenshots/status-window-on.png)

### Confirm Search

![Confirm search window](screenshots/confirm-window.png)

---

## Features

* **Wake-word activation** using `openWakeWord`
* **Global hotkey activation** with `pynput`
* **Local microphone capture** using PyAudio
* **Speech transcription** using Google Web Speech through `SpeechRecognition`
* **Editable transcription** before searching
* **Silence timeout** when no speech is detected
* **Audio level meter** while recording
* **Activation and deactivation sounds**
* **Multiple search destinations**
* **Spoken mathematical notation conversion**
* **Destination aliases** designed for natural speech
* **Background transcription** so the GUI remains responsive
* **Thread-safe recording state**
* **Explicit audio-boundary checks** around recording sessions
* **Timestamped runtime logging**

---

## What It Does

The application runs in the background and waits for either:

1. The wake word **"Alexa"**
2. The global hotkey **Ctrl + Shift + `**

Once activated, the application starts buffering microphone audio.

You can then speak a query such as:

```text
google python decorators
```

or:

```text
youtube how to learn C++
```

or:

```text
desmos x squared plus y squared equals 25
```

When recording stops, the captured audio is sent to Google's speech-recognition service for transcription.

The resulting text is displayed in a confirmation window where you can edit it before clicking **Go**.

No magic. No giant AI framework. Just a microphone, some Python, several threads, and the occasional bug.

---

## How It Works

The application is split into a few simple stages:

```text
                 ┌──────────────────┐
                 │    Microphone    │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │     PyAudio      │
                 │   16 kHz / PCM   │
                 └────────┬─────────┘
                          │
             ┌────────────┴────────────┐
             │                         │
             ▼                         ▼
    ┌─────────────────┐       ┌─────────────────┐
    │  openWakeWord   │       │  Active session │
    │  local detection│       │  audio buffer   │
    └────────┬────────┘       └────────┬────────┘
             │                         │
             │ activate                │ deactivate
             └────────────┬────────────┘
                          ▼
                 ┌──────────────────┐
                 │ SpeechRecognition│
                 │ / Google Web     │
                 │ Speech           │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ Transcript +     │
                 │ math processing  │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │ Confirmation     │
                 │ Window           │
                 └────────┬─────────┘
                          │
                          ▼
                 ┌──────────────────┐
                 │   Web Browser    │
                 │ Search Destination│
                 └──────────────────┘
```

The wake-word detection happens locally through `openWakeWord`.

The Google speech-recognition request happens later, after a recording session has ended.

---

## Audio Handling

The application intentionally separates wake-word detection from transcription.

While idle, the microphone stream is read for wake-word detection.

When a session is activated, audio frames are added to the recording buffer.

When the session is deactivated:

1. `is_active` is set to `False`.
2. The current recording buffer is detached from the capture state.
3. The active recording buffer is cleared.
4. The capture loop can no longer append to that detached buffer.
5. The detached audio is passed to the transcription thread.

The code also performs explicit runtime checks after deactivation to verify:

```text
is_active == False
recorded_frames == []
```

This is intentional rather than relying on Python's `assert` statement.

The application also logs capture, hand-off, and transcription events with timestamps.

The goal is to make the audio boundary clear:

**idle audio is used for local wake-word detection; an actual recording session is what gets passed to the transcription service.**

---

## Search Destinations

Queries can optionally start with a destination keyword.

| Destination                | Example                               |
| -------------------------- | ------------------------------------- |
| Google                     | `google python threading`             |
| Wikipedia                  | `wikipedia Alan Turing`               |
| YouTube                    | `youtube python tutorials`            |
| WolframAlpha               | `wolfram alpha integral x squared`    |
| Khan Academy               | `khan academy calculus`               |
| GeeksforGeeks              | `geeks for geeks binary search`       |
| Desmos                     | `desmos x squared plus y squared`     |
| Paul's Notes               | `pauls notes differential equations`  |
| Math Stack Exchange        | `math stack exchange eigenvalues`     |
| Physics Stack Exchange     | `physics stack exchange relativity`   |
| Electronics Stack Exchange | `electronics stack exchange op amp`   |
| MIT OpenCourseWare         | `mit ocw linear algebra`              |
| arXiv                      | `arxiv transformer architecture`      |
| Symbolab                   | `symbolab quadratic equation`         |
| MathWorld                  | `mathworld Fourier transform`         |
| IEEE Xplore                | `ieee machine learning`               |
| Coursera                   | `coursera python course`              |
| GitHub                     | `github tkinter projects`             |
| Stack Overflow             | `stackoverflow python threading`      |
| Octopart                   | `octopart LM358`                      |
| All About Circuits         | `all about circuits transistor`       |
| Engineering Toolbox        | `engineering toolbox reynolds number` |

If no destination is specified, **Google** is used.

### Examples

```text
python list comprehensions
```

Searches Google.

```text
youtube python tkinter tutorial
```

Searches YouTube.

```text
github open source voice assistant
```

Searches GitHub.

```text
wikipedia Nikola Tesla
```

Searches Wikipedia.

---

## Mathematical Speech Conversion

The application includes a lightweight speech-to-math conversion layer before the query is sent to the selected search engine.

For example:

| Spoken phrase              | Converted form |
| -------------------------- | -------------- |
| `x squared`                | `x²`           |
| `x cubed`                  | `x³`           |
| `x power five`             | `x^5`          |
| `x to the fifth power`     | `x^5`          |
| `a over b`                 | `a/b`          |
| `square root of x`         | `√x`           |
| `integral of f x`          | `∫ f x`        |
| `derivative of x squared`  | `d/dx x²`      |
| `greater than or equal to` | `≥`            |
| `less than or equal to`    | `≤`            |
| `not equal to`             | `≠`            |
| `plus or minus`            | `±`            |
| `infinity`                 | `∞`            |
| `theta`                    | `θ`            |
| `alpha`                    | `α`            |
| `pi`                       | `π`            |
| `ohm`                      | `Ω`            |

The confirmation window lets you correct the result before it is opened in the browser.

This is deliberately a simple substitution system rather than a full mathematical parser.

In other words, it is not going to win a Fields Medal anytime soon.

---

## Usage

### 1. Start the application

```bash
python voice_search.py
```

The application starts in the background and displays the status window.

### 2. Activate it

Either say:

```text
Alexa
```

or press:

```text
Ctrl + Shift + `
```

### 3. Speak your query

For example:

```text
youtube how does a python generator work
```

### 4. Stop recording

You can stop with the same wake word or hotkey.

If you stop speaking for the configured timeout period, the session is automatically stopped.

### 5. Review the transcript

The confirmation window shows the processed query.

Edit anything that was transcribed incorrectly.

### 6. Search

Click **Go**.

The application opens the selected destination in your default browser.

---

## Prerequisites

### Python

Python 3.11 or newer is recommended.

Check your version:

```bash
python --version
```

or:

```bash
python3 --version
```

### Microphone

A working microphone is required.

The application expects:

* Mono audio
* 16-bit PCM
* 16 kHz sample rate

### Internet Connection

An internet connection is required for the transcription step because the current implementation uses Google's Web Speech recognition service.

Wake-word detection itself is handled locally by `openWakeWord`.

### PortAudio

PyAudio depends on PortAudio for microphone input/output.

On Linux, PortAudio development packages may be required when installing PyAudio.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/voice-search-launcher.git
cd voice-search-launcher
```

Replace `YOUR_USERNAME` with your GitHub username.

### 2. Create a virtual environment

#### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
```

#### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If you don't have a `requirements.txt` yet, the dependencies are:

```bash
pip install numpy pyaudio SpeechRecognition openwakeword pynput
```

### Linux / Debian / Ubuntu

If PyAudio cannot find PortAudio:

```bash
sudo apt install portaudio19-dev python3-dev
```

Then:

```bash
pip install pyaudio
```

### Arch Linux

```bash
sudo pacman -S portaudio python
```

Then install the Python dependencies inside the virtual environment:

```bash
pip install numpy pyaudio SpeechRecognition openwakeword pynput
```

### Windows

In most cases:

```powershell
pip install numpy pyaudio SpeechRecognition openwakeword pynput
```

### macOS

Install PortAudio first:

```bash
brew install portaudio
```

Then:

```bash
pip install numpy pyaudio SpeechRecognition openwakeword pynput
```

---

## Running the Application

```bash
python voice_search.py
```

You should see the status window.

To stop the application, use the **Quit** button or press:

```text
Ctrl + C
```

---

## Project Structure

```text
voice-search-launcher/
│
├── voice_search.py
├── README.md
├── LICENSE
├── requirements.txt
│
└── screenshots/
    ├── confirm-window.png
    ├── status-window-off.png
    └── status-window-on.png
```

### `voice_search.py`

Contains the complete application:

* audio capture
* wake-word detection
* global hotkey handling
* recording state management
* silence detection
* speech recognition
* mathematical substitutions
* destination parsing
* search URL generation
* Tkinter interface

### `screenshots/`

Contains screenshots displayed in this README.

### `requirements.txt`

Recommended dependency list:

```text
numpy
pyaudio
SpeechRecognition
openwakeword
pynput
```

---

## Use Cases

This application is primarily designed for situations where you want to search for something quickly without switching to a browser and typing the query manually.

### Quick Web Searches

```text
python dictionary comprehension
```

```text
wikipedia Ada Lovelace
```

Useful when you just need to look something up quickly.

---


### Education and Study

The launcher can also be used while studying.

```text
khan academy differential equations
```

```text
mit ocw linear algebra
```

```text
coursera machine learning
```

```text
pauls notes vector calculus
```

---

### Hands-Busy Workflows

Voice input can be useful when your hands are occupied.

For example:

* working at an electronics bench
* following a programming tutorial
* studying mathematics
* checking component information
* looking up documentation while coding
* quickly searching technical references

---

### Accessibility

Voice input can provide an alternative to conventional keyboard-based searching for users who find typing inconvenient.

---

## Privacy

This project uses two different stages for audio processing.

### Wake-Word Detection

The wake-word detector uses `openWakeWord` locally.

The application reads microphone audio continuously so it can detect the configured wake word.

### Speech Transcription

After a recording session is stopped, the captured session audio is passed to:

```text
SpeechRecognition
        ↓
Google Web Speech recognition
```

The current implementation therefore **does send the completed recording session to Google for transcription**.

The application does not intentionally send the idle microphone stream to Google for transcription.

The recording buffer is only appended to while the application is in an active session.

If completely offline transcription is required, the transcription backend could be replaced with a local speech-recognition engine such as Vosk or another offline solution.

---

## Configuration

Most behavior can be adjusted near the top of `voice_search.py`.

For example:

```python
WAKE_THRESHOLD = 0.5
TOGGLE_COOLDOWN_SEC = 1.5
SILENCE_TIMEOUT_SEC = 8.0
SILENCE_AMPLITUDE_THRESHOLD = 300
MIN_SESSION_DURATION_SEC = 0.3
```

### Wake-Word Threshold

```python
WAKE_THRESHOLD = 0.5
```

Controls how confident `openWakeWord` needs to be before triggering.

### Silence Timeout

```python
SILENCE_TIMEOUT_SEC = 8.0
```

Controls how long the application waits without detecting significant audio before automatically ending the session.

### Minimum Session Duration

```python
MIN_SESSION_DURATION_SEC = 0.3
```

Very short recordings are discarded rather than sent for transcription.

---

## Tech Stack

| Component         | Purpose                              |
| ----------------- | ------------------------------------ |
| Python            | Application logic                    |
| Tkinter           | Desktop GUI                          |
| PyAudio           | Microphone/audio I/O                 |
| NumPy             | Audio processing and RMS calculation |
| openWakeWord      | Local wake-word detection            |
| SpeechRecognition | Speech recognition interface         |
| Google Web Speech | Cloud transcription                  |
| pynput            | Global keyboard hotkey               |
| webbrowser        | Opening search results               |

---

## Design Notes

The application intentionally keeps the architecture relatively small.

There is no server, database, account system, or custom backend.

The main components communicate through a queue and background threads:

```text
AudioWorker
     │
     ├── microphone capture
     ├── wake-word detection
     ├── recording
     ├── silence detection
     └── transcription
             │
             ▼
        UI Queue
             │
             ▼
          Tkinter
```

Tkinter GUI operations remain on the main thread while audio processing and transcription run in background threads.

---

## Known Limitations

This project is still under development.

Some known limitations include:

* Google Web Speech recognition requires an internet connection.
* Transcription quality depends on the speech-recognition service and microphone quality.
* Wake-word detection can produce false positives or false negatives.
* The mathematical conversion system is rule-based and does not understand arbitrary mathematical grammar.
* The current wake word is the pretrained `Alexa` model.
* Search destinations are currently configured directly in the Python source.
* Linux audio setup may require PortAudio system packages.
* Global hotkey behavior can vary depending on the desktop environment and operating system.
* There are currently limited automated tests.
* There may be bugs that I haven't discovered yet.

That last one is not a disclaimer.

It's a promise.

---

## Future Improvements

Some possible directions for the project:

* [ ] Local speech recognition using Vosk or another offline engine
* [ ] Additional wake words
* [ ] User-configurable wake word
* [ ] Configurable hotkeys
* [ ] Settings window
* [ ] Custom search destinations
* [ ] Better mathematical expression parsing
* [ ] More robust speech cleanup
* [ ] Search history
* [ ] Optional clipboard integration
* [ ] System tray support
* [ ] Better audio-device selection
* [ ] Windows/macOS/Linux packaging
* [ ] Automated tests
* [ ] CI workflow
* [ ] Configuration file instead of hard-coded settings

---

## Contributing

**Contributions are very welcome.**

I'm still learning Python and software development, so there is plenty of room for improvement.

If you know how to make something cleaner, safer, faster, more portable, or simply less ridiculous, please contribute.

### Good places to contribute

You can help with:

* bug fixes
* code cleanup
* performance improvements
* audio handling
* wake-word detection
* speech recognition
* mathematical parsing
* new search destinations
* GUI improvements
* documentation
* tests
* Linux/Windows/macOS compatibility
* packaging and distribution

### Getting Started

1. Fork the repository.
2. Clone your fork.
3. Create a branch:

```bash
git checkout -b feature/my-improvement
```

4. Make your changes.
5. Test the application.
6. Commit your changes:

```bash
git add .
git commit -m "Add my improvement"
```

7. Push the branch:

```bash
git push origin feature/my-improvement
```

8. Open a Pull Request.

For larger changes, opening an issue first is recommended so the approach can be discussed before implementation.

---

## Bug Reports

If you find a bug, please open an issue.

Include:

* Operating system
* Python version
* Microphone/audio setup
* Installation method
* Error message or traceback
* Steps to reproduce the problem

For example:

```text
OS: Arch Linux
Python: 3.11
Audio: USB microphone

Problem:
Wake word does not trigger.

Steps:
1. Start voice_search.py
2. Say "Alexa"
3. Nothing happens
```

Please don't upload private recordings or other sensitive information when reporting audio-related problems.

---

## Acknowledgements

This project uses:

* [openWakeWord](https://github.com/dscripka/openWakeWord) — local wake-word detection
* [SpeechRecognition](https://github.com/Uberi/speech_recognition) — speech-recognition interface
* [PyAudio](https://github.com/CristiFati/pyaudio) — audio input/output
* [pynput](https://github.com/moses-palmer/pynput) — global keyboard input

A big thanks to the developers and maintainers of these projects.

---

## Why This Project?

There are plenty of full-featured voice assistants.

This project takes a much smaller approach.

It is focused on one task:

> **Speak a query → review it → search.**

No assistant personality.

No account system.

No custom backend.

No attempt to replace your desktop assistant.

Just a small Python application that lets you use your voice to start a search.

And, apparently, a surprisingly large amount of code is required to make a microphone say "hello, I would like to Google this thing."

---

## Feedback

If you try the project and have feedback, please open an issue.

If you find a bug, report it.

If you know how to improve something, send a pull request.

If you just think the project is cool, that's also acceptable.

And if the code makes you question my programming abilities...

You are probably correct.

I'm learning.

⭐ If you find the project useful, consider giving it a star.
