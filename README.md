# Voice Search

A desktop application that enables voice-activated web searching.

## Screenshots

### Status Window (Off)
![Status Window Off](screenshots/status-window-off.png)

### Status Window (On)
![Status Window On](screenshots/status-window-on.png)

### Confirm Window
![Confirm Window](screenshots/confirm-window.png)

## Prerequisites

- Python 3.7 or higher
- pip (Python package installer)
- A working microphone

## Installation

1. Clone the repository:
   git clone https://github.com/CopyCode652/voice-search.git
   cd voice-search

2. Create and activate a virtual environment:
   python3 -m venv venv
   source venv/bin/activate
   (On Windows, use: venv\Scripts\activate)

3. Install dependencies:
   pip install -r requirements.txt

## Usage

Run the application using the provided shell script:
   ./run.sh

Alternatively, run the Python script directly:
   python voice_search.py

## Project Structure

.
├── README.md
├── requirements.txt
├── run.sh
├── screenshots/
│   ├── confirm-window.png
│   ├── status-window-off.png
│   └── status-window-on.png
└── voice_search.py