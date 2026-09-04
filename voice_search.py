"""
Voice-to-search + app launcher (redesigned UI).

Activate/deactivate by saying "Alexa" OR pressing a global hotkey.
Speak a query, review/edit the transcript in a Spotlight-style popup,
press Go (or Enter) to search. Say "open <app name>" to launch a local
application instead of searching.

This is a UI/UX redesign of the original script: every window now shares
one design system (theme.py) instead of ad hoc colors per-widget, the app
catalog was expanded and organized by category (app_catalog.py), and a
handful of real bugs were fixed along the way (see CHANGELOG.md).
"""

import time
import threading
import queue
import re
import os
import shutil
import subprocess
import json
import csv
import webbrowser
import urllib.parse
import datetime
import collections

import numpy as np
import pyaudio
import speech_recognition as sr
import openwakeword
from openwakeword.model import Model as WakeWordModel
from pynput import keyboard as pynput_keyboard

import tkinter as tk
from tkinter import ttk, filedialog

from theme import (
    Theme, get_theme, style_ttk, apply_window_chrome,
    PillButton, toggle_switch, Card, RoundedCard, SectionLabel,
)
from app_catalog import APPS, app_labels, app_launchers, app_categories, app_icon, CATEGORIES, APP_ALIASES

try:
    import ctypes
    import ctypes.util
    alsa = ctypes.util.find_library('asound')
    if alsa:
        libasound = ctypes.CDLL(alsa)
        ERROR_HANDLER_FUNC = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p)
        def py_error_handler(filename, line, function, err, fmt):
            pass
        c_error_handler = ERROR_HANDLER_FUNC(py_error_handler)
        libasound.snd_lib_error_set_handler(c_error_handler)
except Exception:
    pass

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1280
SAMPLE_WIDTH_BYTES = 2

HOTKEY_COMBO_DEFAULT = "<ctrl>+<shift>+s"
REVEAL_HOTKEY_COMBO_DEFAULT = "<ctrl>+<shift>+v"

WAKE_WORD_TAIL_PATTERNS = [
    r"\balexa\b", r"\ba lexa\b", r"\balex a\b", r"\baleksa\b",
]

WAKE_WORD_LABELS = {
    "alexa": "Alexa",
    "hey_mycroft": "Hey Mycroft",
    "hey_jarvis": "Hey Jarvis",
    "hey_rhasspy": "Hey Rhasspy",
}
DEFAULT_WAKE_WORD = "alexa"

SETTINGS_DIR = os.path.join(os.path.expanduser("~"), ".voice_search_launcher")
SETTINGS_PATH = os.path.join(SETTINGS_DIR, "settings.json")
HISTORY_PATH = os.path.join(SETTINGS_DIR, "history.json")
MAX_HISTORY_ENTRIES_DEFAULT = 200

# (width, height, show_meter, show_hotkey, font_scale)
WINDOW_SIZES = {
    "Mini": (72, 72, False, False, 0.8),
    "Compact": (240, 108, False, False, 0.9),
    "Normal": (340, 220, True, True, 1.0),
    "Large": (440, 290, True, True, 1.25),
    "Hidden": (0, 0, False, False, 1.0),
}
DEFAULT_WINDOW_SIZE = "Normal"

TONE_THEMES = {
    "Classic beep": (880, [440, 440, 440], [300, 300], "sine"),
    "Soft chime": (1046, [784, 659], [220, 220], "soft"),
    "Click": (1800, [1200], [500, 500, 500], "square"),
    "Sci-fi blip": (1500, [1900, 1500, 1100], [260, 180], "square"),
    "Retro arcade": (1200, [900, 700, 500], [150, 400], "square"),
    "Deep pulse": (220, [180, 140], [90, 90], "triangle"),
    "Marimba chime": (1318, [988, 784, 659], [180, 180], "triangle"),
    "Alert siren": (1000, [1400, 900, 1400], [500, 500], "sawtooth"),
    "Typewriter click": (2200, [1600], [400, 400, 400, 400], "noise"),
    "Bell tone": (1568, [1174, 880], [260, 260], "sine"),
    "Laser tap": (2400, [2000, 1200], [140, 140], "sawtooth"),
    "Mute": (None, [], [], "sine"),
}
DEFAULT_TONE_THEME = "Classic beep"
DEFAULT_TONE_VOLUME = 0.4

UI_THEME_NAMES = ["Dark", "Light"]
DEFAULT_UI_THEME = "Dark"

SPEECH_LANGUAGES = {
    "English (US)": "en-US",
    "English (UK)": "en-GB",
    "English (India)": "en-IN",
    "Hindi": "hi-IN",
    "Spanish": "es-ES",
    "French": "fr-FR",
    "German": "de-DE",
}
DEFAULT_SPEECH_LANGUAGE = "en-US"

DEFAULT_SETTINGS = {
    "wake_word": DEFAULT_WAKE_WORD,
    "window_size": DEFAULT_WINDOW_SIZE,
    "tone_theme": DEFAULT_TONE_THEME,
    "tone_volume": DEFAULT_TONE_VOLUME,
    "default_destination": "google",
    "wake_threshold": 0.5,
    "silence_timeout_sec": 8.0,
    "silence_amplitude_threshold": 300,
    "hotkey_combo": HOTKEY_COMBO_DEFAULT,
    "reveal_hotkey_combo": REVEAL_HOTKEY_COMBO_DEFAULT,
    "ui_theme": DEFAULT_UI_THEME,
    "auto_search": False,
    "clipboard_auto_copy": False,
    "app_launch_enabled": True,
    "speech_language": DEFAULT_SPEECH_LANGUAGE,
    "mic_device_index": None,
    "max_history_entries": MAX_HISTORY_ENTRIES_DEFAULT,
}

SEARCH_URLS = {
    "google": "https://www.google.com/search?q={}",
    "wikipedia": "https://en.wikipedia.org/w/index.php?search={}",
    "youtube": "https://www.youtube.com/results?search_query={}",
    "wolframalpha": "https://www.wolframalpha.com/input?i={}",
    "khanacademy": "https://www.khanacademy.org/search?search_again=1&page_search_query={}",
    "geeksforgeeks": "https://www.geeksforgeeks.org/?s={}",
    "desmos": "https://www.desmos.com/calculator?graph={}",
    "paulsnotes": "https://tutorial.math.lamar.edu/search.aspx?q={}",
    "stackexchange": "https://math.stackexchange.com/search?q={}",
    "physicsstackexchange": "https://physics.stackexchange.com/search?q={}",
    "electronicsstackexchange": "https://electronics.stackexchange.com/search?q={}",
    "mitocw": "https://ocw.mit.edu/search/?q={}",
    "arxiv": "https://arxiv.org/abs?searchtype=all&query={}",
    "symbolab": "https://www.symbolab.com/solver/step-by-step/{}",
    "mathworld": "https://mathworld.wolfram.com/search/?query={}",
    "ieee": "https://ieeexplore.ieee.org/search/searchresult.jsp?queryText={}",
    "coursera": "https://www.coursera.org/search?query={}",
    "github": "https://github.com/search?q={}",
    "gitlab": "https://gitlab.com/search?search={}",
    "stackoverflow": "https://stackoverflow.com/search?q={}",
    "octopart": "https://octopart.com/search?q={}",
    "allaboutcircuits": "https://www.allaboutcircuits.com/search/?q={}",
    "engineeringtoolbox": "https://www.engineeringtoolbox.com/search.php?q={}",
    "reddit": "https://www.reddit.com/search/?q={}",
    "duckduckgo": "https://duckduckgo.com/?q={}",
    "bing": "https://www.bing.com/search?q={}",
    "amazon": "https://www.amazon.com/s?k={}",
    "maps": "https://www.google.com/maps/search/{}",
    "images": "https://www.google.com/search?tbm=isch&q={}",
    "news": "https://news.google.com/search?q={}",
    "translate": "https://translate.google.com/?text={}",
    "chatgpt": "https://chat.openai.com/?q={}",
    "claude": "https://claude.ai/new?q={}",
    "geogebra": "https://www.geogebra.org/search/{}",
    "paperswithcode": "https://paperswithcode.com/search?q_meta=&q_type=&q={}",
    "semanticscholar": "https://www.semanticscholar.org/search?q={}&sort=relevance",
    "googlescholar": "https://scholar.google.com/scholar?q={}",
    "npm": "https://www.npmjs.com/search?q={}",
    "pypi": "https://pypi.org/search/?q={}",
    "docs_python": "https://docs.python.org/3/search.html?q={}",
    "mdn": "https://developer.mozilla.org/en-US/search?q={}",
    "hackernews": "https://hn.algolia.com/?q={}",
    "leetcode": "https://leetcode.com/problemset/?search={}",
    "digikey": "https://www.digikey.com/en/products/result?keywords={}",
    "mouser": "https://www.mouser.com/c/?q={}",
    "lcsc": "https://www.lcsc.com/search?q={}",
    "jlcpcb": "https://jlcpcb.com/parts/componentSearch?searchTxt={}",
    "easyeda": "https://easyeda.com/search?keyword={}",
    "alldatasheet": "https://www.alldatasheet.com/view.jsp?Searchword={}",
    "datasheetcatalog": "https://www.datasheetcatalog.com/search/{}",
    "ti": "https://www.ti.com/sitesearch/en-us/docs/universalsearch.tsp?searchTerm={}",
    "analogdevices": "https://www.analog.com/en/search.html?q={}",
    "microchip": "https://www.microchip.com/en-us/search-results?indexCatalogue=allcontent&searchQuery={}",
    "stmicro": "https://www.st.com/content/st_com/en/search.html#q={}",
    "nxp": "https://www.nxp.com/search?keyword={}",
    "infineon": "https://www.infineon.com/cms/en/search.html#!term={}",
    "vishay": "https://www.vishay.com/search/?q={}",
    "eevblog": "https://www.eevblog.com/forum/index.php?action=search2&search={}",
    "element14": "https://www.element14.com/community/search.jspa?q={}",
    "rscomponents": "https://uk.rs-online.com/web/c/?searchTerm={}",
    "farnell": "https://www.farnell.com/search?st={}",
    "sparkfun": "https://www.sparkfun.com/search/results?term={}",
    "adafruit": "https://www.adafruit.com/search?q={}",
    "circuitlab": "https://www.circuitlab.com/search/?q={}",
    "falstad": "https://www.falstad.com/circuit/circuitjs.html?{}",
    "multisimlive": "https://www.multisim.com/search/?query={}",
    "pcbway": "https://www.pcbway.com/orderonline.aspx?searchword={}",
    "oshpark": "https://oshpark.com/search?q={}",
    "instructables": "https://www.instructables.com/howto/{}",
    "hackaday": "https://hackaday.com/?s={}",
    "electronicstutorials": "https://www.electronics-tutorials.ws/?s={}",
    "circuitdigest": "https://circuitdigest.com/search/node/{}",
    "researchgate": "https://www.researchgate.net/search?q={}",
    "overleaf": "https://www.overleaf.com/project?{}",
    "nptel": "https://nptel.ac.in/search?query={}",
    "edx": "https://www.edx.org/search?q={}",
    "kicaddocs": "https://docs.kicad.org/?q={}",
}

DESTINATION_ALIASES = {
    "google dot com": "google", "google.com": "google", "google": "google",
    "wikipedia dot org": "wikipedia", "wikipedia.org": "wikipedia", "wikipedia": "wikipedia", "wiki": "wikipedia",
    "youtube dot com": "youtube", "youtube.com": "youtube", "you tube": "youtube", "youtube": "youtube",
    "wolfram alpha dot com": "wolframalpha", "wolfram alpha": "wolframalpha", "wolframalpha": "wolframalpha", "wolfram": "wolframalpha", "alpha": "wolframalpha",
    "khan academy": "khanacademy", "khanacademy": "khanacademy", "khan": "khanacademy",
    "geeks for geeks": "geeksforgeeks", "geeksforgeeks": "geeksforgeeks", "geeks": "geeksforgeeks",
    "desmos dot com": "desmos", "desmos": "desmos", "graph": "desmos",
    "pauls notes": "paulsnotes", "paulsnotes": "paulsnotes", "pauls": "paulsnotes",
    "math stack exchange": "stackexchange", "stack exchange": "stackexchange", "stackexchange": "stackexchange", "stack": "stackexchange",
    "physics stack exchange": "physicsstackexchange",
    "electronics stack exchange": "electronicsstackexchange",
    "mit ocw": "mitocw", "mit open course ware": "mitocw", "mitocw": "mitocw", "mit": "mitocw", "ocw": "mitocw",
    "arxiv dot org": "arxiv", "arxiv": "arxiv",
    "symbolab dot com": "symbolab", "symbolab": "symbolab",
    "math world": "mathworld", "mathworld": "mathworld",
    "ieee explore": "ieee", "ieee": "ieee",
    "coursera dot org": "coursera", "coursera": "coursera",
    "github dot com": "github", "github": "github", "hub": "github",
    "gitlab dot com": "gitlab", "gitlab": "gitlab",
    "stack overflow": "stackoverflow", "stackoverflow": "stackoverflow",
    "octopart": "octopart",
    "all about circuits": "allaboutcircuits", "allaboutcircuits": "allaboutcircuits",
    "engineering toolbox": "engineeringtoolbox", "engineeringtoolbox": "engineeringtoolbox",
    "reddit dot com": "reddit", "reddit.com": "reddit", "reddit": "reddit",
    "duck duck go": "duckduckgo", "duckduckgo": "duckduckgo",
    "bing dot com": "bing", "bing.com": "bing", "bing": "bing",
    "amazon dot com": "amazon", "amazon.com": "amazon", "amazon": "amazon",
    "google maps": "maps", "maps": "maps",
    "google images": "images", "images": "images", "image search": "images",
    "google news": "news", "news": "news",
    "google translate": "translate", "translate": "translate",
    "chat gpt": "chatgpt", "chatgpt": "chatgpt", "open ai": "chatgpt",
    "claude dot ai": "claude", "claude.ai": "claude", "claude": "claude",
    "geo gebra": "geogebra", "geogebra": "geogebra",
    "papers with code": "paperswithcode", "paperswithcode": "paperswithcode",
    "semantic scholar": "semanticscholar", "semanticscholar": "semanticscholar",
    "google scholar": "googlescholar", "googlescholar": "googlescholar", "scholar": "googlescholar",
    "npm dot com": "npm", "npm": "npm", "npm js": "npm",
    "pypi dot org": "pypi", "pypi": "pypi", "pip": "pypi",
    "python docs": "docs_python", "python documentation": "docs_python",
    "mdn": "mdn", "mozilla docs": "mdn", "mozilla developer network": "mdn",
    "hacker news": "hackernews", "hackernews": "hackernews",
    "leet code": "leetcode", "leetcode": "leetcode",
    "digi key": "digikey", "digikey": "digikey", "digikey dot com": "digikey",
    "mouser electronics": "mouser", "mouser": "mouser", "mouser dot com": "mouser",
    "lcsc electronics": "lcsc", "lcsc": "lcsc",
    "j l c p c b": "jlcpcb", "jlcpcb": "jlcpcb", "jay el cee pee cee bee": "jlcpcb",
    "easy eda": "easyeda", "easyeda": "easyeda",
    "all datasheet": "alldatasheet", "alldatasheet": "alldatasheet",
    "datasheet catalog": "datasheetcatalog", "datasheetcatalog": "datasheetcatalog",
    "texas instruments": "ti", "ti dot com": "ti", "t i": "ti",
    "analog devices": "analogdevices", "analogdevices": "analogdevices",
    "microchip technology": "microchip", "microchip": "microchip",
    "st microelectronics": "stmicro", "stmicroelectronics": "stmicro", "st micro": "stmicro",
    "nxp semiconductors": "nxp", "nxp": "nxp",
    "infineon technologies": "infineon", "infineon": "infineon",
    "vishay intertechnology": "vishay", "vishay": "vishay",
    "e e v blog": "eevblog", "eevblog": "eevblog", "eev blog": "eevblog",
    "element fourteen": "element14", "element14": "element14",
    "r s components": "rscomponents", "rs components": "rscomponents",
    "farnell": "farnell",
    "sparkfun": "sparkfun", "spark fun": "sparkfun",
    "adafruit": "adafruit", "ada fruit": "adafruit",
    "circuit lab": "circuitlab", "circuitlab": "circuitlab",
    "falstad circuit simulator": "falstad", "falstad": "falstad", "circuit js": "falstad",
    "multisim live": "multisimlive", "multisim": "multisimlive",
    "pcb way": "pcbway", "pcbway": "pcbway",
    "osh park": "oshpark", "oshpark": "oshpark",
    "instructables": "instructables",
    "hackaday": "hackaday", "hack a day": "hackaday",
    "electronics tutorials": "electronicstutorials",
    "circuit digest": "circuitdigest", "circuitdigest": "circuitdigest",
    "research gate": "researchgate", "researchgate": "researchgate",
    "overleaf": "overleaf", "over leaf": "overleaf",
    "n p tel": "nptel", "nptel": "nptel",
    "edx dot org": "edx", "edx": "edx", "e d x": "edx",
    "kicad documentation": "kicaddocs", "kicad docs": "kicaddocs",
}
_DESTINATION_KEYS_BY_LENGTH = sorted(DESTINATION_ALIASES.keys(), key=lambda k: -len(k.split()))
DEFAULT_DESTINATION = "google"

APP_LABELS = app_labels()
APP_LAUNCHERS = app_launchers()
APP_CATEGORIES = app_categories()
_APP_ALIAS_KEYS_BY_LENGTH = sorted(APP_ALIASES.keys(), key=lambda k: -len(k.split()))
APP_TRIGGER_WORDS = ("open", "launch", "start", "run", "fire up")


def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def get_valid_hotkey(combo, fallback=HOTKEY_COMBO_DEFAULT):
    if not isinstance(combo, str):
        return fallback
    try:
        pynput_keyboard.HotKey.parse(combo)
        return combo
    except Exception:
        log(f"Warning: Invalid hotkey '{combo}' in settings. Falling back to '{fallback}'.")
        return fallback


def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            saved = json.load(f)
        for key in DEFAULT_SETTINGS:
            if key in saved:
                settings[key] = saved[key]
    except (FileNotFoundError, json.JSONDecodeError, OSError) as e:
        log(f"No usable settings file yet ({e}) -- using defaults.")
    return settings


def save_settings(settings):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except OSError as e:
        log(f"Failed to save settings: {e}")


def load_history(maxlen):
    try:
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return collections.deque(data, maxlen=maxlen)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return collections.deque(maxlen=maxlen)


def save_history(history_deque):
    try:
        os.makedirs(SETTINGS_DIR, exist_ok=True)
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(list(history_deque), f, indent=2)
    except OSError as e:
        log(f"Failed to save history: {e}")


def available_wake_words():
    try:
        found = list(openwakeword.models.keys())
    except Exception as e:
        log(f"Could not list openWakeWord pretrained models: {e}")
        found = [DEFAULT_WAKE_WORD]
    result = [name for name in WAKE_WORD_LABELS if name in found]
    return result or [DEFAULT_WAKE_WORD]


def list_input_devices(pa):
    devices = []
    try:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info.get("maxInputChannels", 0) > 0:
                devices.append((i, info.get("name", f"Device {i}")))
    except Exception as e:
        log(f"Could not enumerate input devices: {e}")
    return devices


def _make_tone(freq, duration, volume=0.4, sr_=RATE, waveform="sine"):
    n = int(sr_ * duration)
    t = np.linspace(0, duration, n, False)
    if waveform == "square":
        tone = np.sign(np.sin(freq * t * 2 * np.pi))
    elif waveform == "triangle":
        # Symmetric triangle wave via arcsin of a sine, normalized to [-1, 1].
        tone = (2.0 / np.pi) * np.arcsin(np.sin(freq * t * 2 * np.pi))
    elif waveform == "sawtooth":
        # Rising ramp from -1 to 1 each period.
        tone = 2.0 * (freq * t - np.floor(0.5 + freq * t))
    elif waveform == "noise":
        # Short filtered burst of noise for a mechanical "click"/typewriter feel.
        #
        # PERF: the original one-pole low-pass ran as a pure-Python
        # sample-by-sample for loop (n iterations of scalar float math per
        # tone). For a 16kHz signal that's thousands of interpreter-level
        # iterations on every preview/activation/deactivation, which is
        # measurably slower than the vectorized numpy path used by every
        # other waveform. A short moving-average via cumulative sum gives
        # the same "softened click" character (attenuates high-frequency
        # noise, keeps a percussive envelope) without a Python-level loop.
        rng = np.random.default_rng(int(freq) if freq else 1)
        raw = rng.uniform(-1.0, 1.0, n)
        window = max(1, int(sr_ * 0.001))  # ~1ms smoothing window
        cumsum = np.cumsum(np.insert(raw, 0, 0.0))
        smoothed = (cumsum[window:] - cumsum[:-window]) / window
        # Pad back to length n (the moving average shortens the array by
        # window-1 samples); repeat the first value rather than zero-pad,
        # so the fade-in envelope below still starts from a real sample.
        pad = np.full(n - len(smoothed), smoothed[0] if len(smoothed) else 0.0)
        tone = np.concatenate([pad, smoothed])
        peak = np.max(np.abs(tone)) or 1.0
        tone = tone / peak
    else:
        tone = np.sin(freq * t * 2 * np.pi)
    fade = int(sr_ * (0.02 if waveform in ("soft", "noise") else 0.005))
    fade = max(1, min(fade, len(tone) // 2))
    tone[:fade] *= np.linspace(0, 1, fade)
    tone[-fade:] *= np.linspace(1, 0, fade)
    vol = volume * 0.6 if waveform == "soft" else volume
    return (tone * vol * 32767).astype(np.int16)


def _make_tone_sequence(freqs, duration, gap_sec, waveform="sine", volume=0.4):
    if not freqs:
        return np.zeros(0, dtype=np.int16)
    gap = np.zeros(int(RATE * gap_sec), dtype=np.int16)
    parts = []
    for i, f in enumerate(freqs):
        parts.append(_make_tone(f, duration, volume=volume, waveform=waveform))
        if i != len(freqs) - 1:
            parts.append(gap)
    return np.concatenate(parts)


def build_tone_set(theme_name, volume=DEFAULT_TONE_VOLUME):
    """Synthesize the (activate, deactivate, timeout) tone arrays for a theme.

    `volume` is a 0.0-1.0 master gain applied on top of each theme's own
    per-waveform balancing, so users can turn all sounds up/down without
    changing which theme (waveform/frequencies) they're using.
    """
    activate_freq, deactivate_freqs, timeout_freqs, waveform = TONE_THEMES.get(
        theme_name, TONE_THEMES[DEFAULT_TONE_THEME])
    volume = max(0.0, min(1.0, volume))
    if activate_freq is None or volume == 0.0:
        activate = np.zeros(0, dtype=np.int16)
    else:
        activate = _make_tone(activate_freq, 0.12, volume=volume, waveform=waveform)
    if volume == 0.0:
        deactivate = np.zeros(0, dtype=np.int16)
        timeout = np.zeros(0, dtype=np.int16)
    else:
        deactivate = _make_tone_sequence(deactivate_freqs, 0.08, 0.05, waveform=waveform, volume=volume)
        timeout = _make_tone_sequence(timeout_freqs, 0.15, 0.08, waveform=waveform, volume=volume)
    return activate, deactivate, timeout


def play_tone_async(pa, tone_array):
    if tone_array is None or len(tone_array) == 0:
        return
    def _play():
        out = pa.open(format=pyaudio.paInt16, channels=1, rate=RATE, output=True)
        out.write(tone_array.tobytes())
        out.stop_stream()
        out.close()
    threading.Thread(target=_play, daemon=True).start()


def rms_amplitude(samples):
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))


def strip_trailing_wake_word(text, wake_word=DEFAULT_WAKE_WORD):
    if wake_word != "alexa":
        return text.strip()
    stripped = text.strip()
    for pattern in WAKE_WORD_TAIL_PATTERNS:
        new_text = re.sub(pattern + r"[\.\!\?,]*\s*$", "", stripped, flags=re.IGNORECASE)
        if new_text != stripped:
            return new_text.strip()
    return stripped


_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
    "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10",
    "eleven": "11", "twelve": "12", "thirteen": "13", "fourteen": "14",
    "fifteen": "15", "sixteen": "16", "seventeen": "17", "eighteen": "18",
    "nineteen": "19", "twenty": "20", "thirty": "30", "forty": "40", "fifty": "50",
    "sixty": "60", "seventy": "70", "eighty": "80", "ninety": "90", "hundred": "100",
}
_NUM_WORD_PATTERN = "|".join(sorted(_NUMBER_WORDS.keys(), key=len, reverse=True))
_ORDINAL_TO_CARDINAL = {
    "first": "1", "second": "2", "third": "3", "fourth": "4", "fifth": "5",
    "sixth": "6", "seventh": "7", "eighth": "8", "ninth": "9", "tenth": "10",
}
_ORDINAL_PATTERN = "|".join(_ORDINAL_TO_CARDINAL.keys())


def _word_to_digit(word):
    lw = word.lower()
    if lw in _NUMBER_WORDS:
        return _NUMBER_WORDS[lw]
    if lw in _ORDINAL_TO_CARDINAL:
        return _ORDINAL_TO_CARDINAL[lw]
    return word


def _replace_power_variants(text):
    num_group = rf"({_NUM_WORD_PATTERN}|\d+)"
    ordinal_group = rf"({_ORDINAL_PATTERN})"
    patterns = [
        rf"(\w+)\s+to\s+the\s+power\s+of\s+{num_group}\b",
        rf"(\w+)\s+to\s+the\s+power\s+{num_group}\b",
        rf"(\w+)\s+power\s+of\s+{num_group}\b",
        rf"(\w+)\s+power\s+{num_group}\b",
        rf"(\w+)\s+to\s+the\s+{ordinal_group}\s+power\b",
        rf"(\w+)\s+to\s+the\s+{ordinal_group}\b",
    ]
    def _sub(match):
        return f"{match.group(1)}^{_word_to_digit(match.group(2))}"
    result = text
    for pattern in patterns:
        result = re.sub(pattern, _sub, result, flags=re.IGNORECASE)
    return result


def _replace_subscript_variants(text):
    pattern = r"(\w+)\s+sub(?:script)?\s+(\w+)\b"
    return re.sub(pattern, lambda m: f"{m.group(1)}_{_word_to_digit(m.group(2))}", text, flags=re.IGNORECASE)


def _replace_fraction_variants(text):
    pattern = r"\b(\w+)\s+over\s+(\w+)\b"
    return re.sub(pattern, lambda m: f"{m.group(1)}/{m.group(2)}", text, flags=re.IGNORECASE)


def _replace_root_of_variants(text):
    pattern = r"\broot\s+(\w+)\s+of\s+(\w+)\b"
    return re.sub(pattern, lambda m: f"root({_word_to_digit(m.group(1))}, {m.group(2)})", text, flags=re.IGNORECASE)


def _replace_log_variants(text):
    base_pattern = r"\blog\s+base\s+(\w+)\s+of\s+(\w+)\b"
    text = re.sub(base_pattern, lambda m: f"log_{_word_to_digit(m.group(1))}({m.group(2)})", text, flags=re.IGNORECASE)
    simple_pattern = r"\b(log|ln)\s+of\s+(\w+)\b"
    text = re.sub(simple_pattern, lambda m: f"{m.group(1).lower()}({m.group(2)})", text, flags=re.IGNORECASE)
    return text


def _replace_limit_variants(text):
    # "limit as x approaches infinity of f(x)" / "limit of f(x) as x approaches 0"
    pattern_a = r"\blimit\s+as\s+(\w+)\s+(?:approaches|tends to|goes to)\s+([\w\u221e+\u2212-]+)\s+of\s+(.+?)(?=[.,;]|$)"
    text = re.sub(pattern_a, lambda m: f"lim_{{{m.group(1)}\u2192{_word_to_digit(m.group(2))}}} {m.group(3).strip()}",
                  text, flags=re.IGNORECASE)
    pattern_b = r"\blimit\s+of\s+(.+?)\s+as\s+(\w+)\s+(?:approaches|tends to|goes to)\s+([\w\u221e+\u2212-]+)"
    text = re.sub(pattern_b, lambda m: f"lim_{{{m.group(2)}\u2192{_word_to_digit(m.group(3))}}} {m.group(1).strip()}",
                  text, flags=re.IGNORECASE)
    text = re.sub(r"\blimit superior\b", "limsup", text, flags=re.IGNORECASE)
    text = re.sub(r"\blimit inferior\b", "liminf", text, flags=re.IGNORECASE)
    return text


def _replace_definite_integral_variants(text):
    # "integral from 0 to infinity of f(x) dx" / "definite integral from a to b of ..."
    pattern = (r"\b(?:definite\s+)?integral\s+from\s+([\w\u221e+\u2212-]+)\s+to\s+([\w\u221e+\u2212-]+)\s+of\s+(.+?)"
               r"(?=[.,;]|$)")
    def _sub(m):
        lo = _word_to_digit(m.group(1))
        hi = _word_to_digit(m.group(2))
        return f"\u222b_{{{lo}}}^{{{hi}}} {m.group(3).strip()}"
    return re.sub(pattern, _sub, text, flags=re.IGNORECASE)


def _replace_nth_derivative_variants(text):
    # "nth derivative of f" / "third derivative of f with respect to t" / "derivative of f with respect to t"
    ordinal_group = rf"({_ORDINAL_PATTERN}|nth)"
    pattern_a = rf"\b{ordinal_group}\s+derivative\s+of\s+(\w+)\s+with respect to\s+(\w+)\b"
    def _sub_a(m):
        order = "n" if m.group(1).lower() == "nth" else _word_to_digit(m.group(1))
        return f"d^{order}{m.group(2)}/d{m.group(3)}^{order}"
    text = re.sub(pattern_a, _sub_a, text, flags=re.IGNORECASE)

    pattern_b = rf"\b{ordinal_group}\s+derivative\s+of\s+(\w+)\b"
    def _sub_b(m):
        order = "n" if m.group(1).lower() == "nth" else _word_to_digit(m.group(1))
        return f"d^{order}{m.group(2)}/dx^{order}"
    text = re.sub(pattern_b, _sub_b, text, flags=re.IGNORECASE)

    pattern_c = r"\bderivative of\s+(\w+)\s+with respect to\s+(\w+)\b"
    text = re.sub(pattern_c, lambda m: f"d{m.group(1)}/d{m.group(2)}", text, flags=re.IGNORECASE)

    pattern_d = r"\bpartial derivative of\s+(\w+)\s+with respect to\s+(\w+)\b"
    text = re.sub(pattern_d, lambda m: f"\u2202{m.group(1)}/\u2202{m.group(2)}", text, flags=re.IGNORECASE)
    return text


def _replace_matrix_linear_algebra_variants(text):
    # "eigenvalue of A", "eigenvector of A", "rank of A", "norm of v", "kernel of T", "span of v", "trace of A"
    unary = {
        "eigenvalues of": "eig(", "eigenvalue of": "eig(",
        "eigenvectors of": "eigvec(", "eigenvector of": "eigvec(",
        "rank of": "rank(", "kernel of": "ker(", "null space of": "null(",
        "span of": "span(", "column space of": "col(", "row space of": "row(",
        "norm of": "\u2016", "magnitude of": "\u2016",
    }
    for spoken, repl in sorted(unary.items(), key=lambda kv: -len(kv[0])):
        pattern = rf"\b{re.escape(spoken)}\s+(\w+)\b"
        if repl == "\u2016":
            text = re.sub(pattern, lambda m: f"\u2016{m.group(1)}\u2016", text, flags=re.IGNORECASE)
        else:
            text = re.sub(pattern, lambda m, r=repl: f"{r}{m.group(1)})", text, flags=re.IGNORECASE)
    return text


def _replace_complex_number_variants(text):
    # EE-critical: phasors, real/imaginary part, complex conjugate, polar form
    unary = {
        "real part of": "Re(", "imaginary part of": "Im(",
        "magnitude of": "|", "argument of": "\u2220", "phase angle of": "\u2220",
    }
    text = re.sub(r"\breal part of\s+(\w+)\b", lambda m: f"Re({m.group(1)})", text, flags=re.IGNORECASE)
    text = re.sub(r"\bimaginary part of\s+(\w+)\b", lambda m: f"Im({m.group(1)})", text, flags=re.IGNORECASE)
    text = re.sub(r"\bcomplex conjugate of\s+(\w+)\b", lambda m: f"{m.group(1)}*", text, flags=re.IGNORECASE)
    # "5 angle 30 degrees" style phasor -> 5∠30°, handled after unit substitution runs on degrees separately;
    # here we handle the explicit "angle" word form directly.
    text = re.sub(r"\b(\w+)\s+at\s+angle\s+(\w+)\b", lambda m: f"{m.group(1)}\u2220{m.group(2)}", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\bj\s*omega\b", "j\u03c9", text, flags=re.IGNORECASE)
    text = re.sub(r"\bimaginary unit\b", "j", text, flags=re.IGNORECASE)
    return text


def _replace_statistics_variants(text):
    # "mean of X", "variance of X", "standard deviation of X", "expected value of X", "probability of A"
    unary = {
        "standard deviation of": "\u03c3(", "variance of": "Var(",
        "expected value of": "E[", "expectation of": "E[",
        "mean of": "\u03bc(", "average of": "\u03bc(",
        "probability of": "P(", "covariance of": "Cov(", "correlation of": "corr(",
    }
    for spoken, opener in sorted(unary.items(), key=lambda kv: -len(kv[0])):
        closer = "]" if opener == "E[" else ")"
        pattern = rf"\b{re.escape(spoken)}\s+(\w+)\b"
        text = re.sub(pattern, lambda m, o=opener, c=closer: f"{o}{m.group(1)}{c}", text, flags=re.IGNORECASE)
    return text


def _replace_number_theory_variants(text):
    # "a mod b", "a modulo b", "gcd of a and b", "lcm of a and b", "a divides b", "a is congruent to b mod n"
    text = re.sub(r"\b(\w+)\s+(?:is\s+)?congruent to\s+(\w+)\s+mod(?:ulo)?\s+(\w+)\b",
                  lambda m: f"{m.group(1)} \u2261 {m.group(2)} (mod {m.group(3)})", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+mod(?:ulo)?\s+(\w+)\b", lambda m: f"{m.group(1)} mod {m.group(2)}", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\b(?:the\s+)?gcd\s+of\s+(\w+)\s+and\s+(\w+)\b",
                  lambda m: f"gcd({m.group(1)}, {m.group(2)})", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(?:the\s+)?lcm\s+of\s+(\w+)\s+and\s+(\w+)\b",
                  lambda m: f"lcm({m.group(1)}, {m.group(2)})", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+divides\s+(\w+)\b", lambda m: f"{m.group(1)} | {m.group(2)}", text, flags=re.IGNORECASE)
    return text


def _replace_combinatorics_variants(text):
    # "n choose k", "n permute k" / "n permutations of k"
    text = re.sub(r"\b(\w+)\s+choose\s+(\w+)\b",
                  lambda m: f"C({_word_to_digit(m.group(1))}, {_word_to_digit(m.group(2))})", text,
                  flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+permute\s+(\w+)\b",
                  lambda m: f"P({_word_to_digit(m.group(1))}, {_word_to_digit(m.group(2))})", text,
                  flags=re.IGNORECASE)
    return text


def _replace_vector_notation_variants(text):
    # "x hat" -> x̂ (unit vector notation), "vector v" / "v vector" -> v⃗
    text = re.sub(r"\b(\w)\s+hat\b", lambda m: f"{m.group(1)}\u0302", text, flags=re.IGNORECASE)
    text = re.sub(r"\bunit vector\s+(\w)\b", lambda m: f"{m.group(1)}\u0302", text, flags=re.IGNORECASE)
    text = re.sub(r"\bvector\s+(\w+)\b", lambda m: f"{m.group(1)}\u20d7", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+vector\b", lambda m: f"{m.group(1)}\u20d7", text, flags=re.IGNORECASE)
    return text


def _replace_convolution_variants(text):
    # "convolution of x and h" -> conv(x, h); "x convolved with h" -> x * h
    text = re.sub(r"\bconvolution of\s+(\w+)\s+and\s+(\w+)\b",
                  lambda m: f"conv({m.group(1)}, {m.group(2)})", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+convolved with\s+(\w+)\b",
                  lambda m: f"{m.group(1)} * {m.group(2)}", text, flags=re.IGNORECASE)
    return text


def _replace_logic_gate_variants(text):
    # Digital logic, core to EE: NAND, NOR, XOR, XNOR, NOT
    text = re.sub(r"\b(\w+)\s+nand\s+(\w+)\b", lambda m: f"{m.group(1)} \u22bc {m.group(2)}", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+nor\s+(\w+)\b", lambda m: f"{m.group(1)} \u2193 {m.group(2)}", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+xnor\s+(\w+)\b", lambda m: f"{m.group(1)} \u2299 {m.group(2)}", text, flags=re.IGNORECASE)
    text = re.sub(r"\b(\w+)\s+xor\s+(\w+)\b", lambda m: f"{m.group(1)} \u2295 {m.group(2)}", text, flags=re.IGNORECASE)
    return text


def _replace_function_of_variants(text):
    names = {
        "sine": "sin", "sin": "sin", "cosine": "cos", "cos": "cos",
        "tangent": "tan", "tan": "tan", "cosecant": "csc", "secant": "sec",
        "cotangent": "cot", "arcsine": "arcsin", "arccosine": "arccos",
        "arctangent": "arctan", "hyperbolic sine": "sinh",
        "hyperbolic cosine": "cosh", "hyperbolic tangent": "tanh",
        "laplace transform": "L", "fourier transform": "F", "z transform": "Z",
        "magnitude": "abs", "determinant": "det", "trace": "tr",
    }
    for spoken, symbol in sorted(names.items(), key=lambda kv: -len(kv[0])):
        pattern = rf"\b{re.escape(spoken)}\s+of\s+(\w+)\b"
        if symbol == "abs":
            text = re.sub(pattern, lambda m: f"|{m.group(1)}|", text, flags=re.IGNORECASE)
        else:
            text = re.sub(pattern, lambda m, sym=symbol: f"{sym}({m.group(1)})", text, flags=re.IGNORECASE)
    return text


MATH_SUBSTITUTIONS = [
    # Capital Greek letters must be matched before the plain lowercase
    # letter patterns below (e.g. "capital sigma" before "sigma"), since
    # substitutions run in list order and lowercase "sigma" would otherwise
    # consume the word first and leave "capital" dangling.
    (r"\bcapital gamma\b", "\u0393"), (r"\bcapital delta\b", "\u0394"), (r"\bcapital theta\b", "\u0398"),
    (r"\bcapital lambda\b", "\u039b"), (r"\bcapital xi\b", "\u039e"), (r"\bcapital pi\b", "\u03a0"),
    (r"\bcapital sigma\b", "\u03a3"), (r"\bcapital phi\b", "\u03a6"), (r"\bcapital psi\b", "\u03a8"),
    (r"\bcapital omega\b", "\u03a9"), (r"\bcapital upsilon\b", "\u03a5"),

    (r"\bdouble integral of\b", "\u222c"), (r"\btriple integral of\b", "\u222d"),
    (r"\bcontour integral of\b", "\u222e"), (r"\bline integral of\b", "\u222e"),
    (r"\bintegral of\b", "\u222b"), (r"\bindefinite integral of\b", "\u222b"),
    (r"\bsquare root of\b", "\u221a"), (r"\bcube root of\b", "\u221b"),
    (r"\bfourth root of\b", "\u221c"), (r"\bnth root of\b", "\u221c"),
    (r"\bsummation of\b", "\u03a3"), (r"\bsum of\b", "\u03a3"), (r"\bproduct of\b", "\u03a0"),
    (r"\bsecond partial derivative of\b", "\u2202\u00b2"), (r"\bpartial derivative of\b", "\u2202"),
    (r"\bderivative of\b", "d/dx"), (r"\bgradient of\b", "\u2207"),
    (r"\bdivergence of\b", "\u2207\u00b7"), (r"\bcurl of\b", "\u2207\u00d7"),
    (r"\blaplacian of\b", "\u2207\u00b2"), (r"\bnabla\b", "\u2207"),
    (r"\bpositive infinity\b", "+\u221e"), (r"\bnegative infinity\b", "\u2212\u221e"),
    (r"\binfinity\b", "\u221e"), (r"\bplus or minus\b", "\u00b1"),
    (r"\bminus or plus\b", "\u2213"), (r"\bnot equal to\b", "\u2260"),
    (r"\bapproximately equal to\b", "\u2248"), (r"\bapproximately\b", "\u2248"),
    (r"\bidentical to\b", "\u2261"), (r"\bproportional to\b", "\u221d"),
    (r"\bgreater than or equal to\b", "\u2265"), (r"\bat least\b", "\u2265"),
    (r"\bless than or equal to\b", "\u2264"), (r"\bat most\b", "\u2264"),
    (r"\bgreater than\b", ">"), (r"\bless than\b", "<"),
    (r"\bfor all\b", "\u2200"), (r"\bthere exists\b", "\u2203"),
    (r"\bdoes not exist\b", "\u2204"), (r"\belement of\b", "\u2208"),
    (r"\bnot an element of\b", "\u2209"), (r"\bsubset of\b", "\u2282"),
    (r"\bsuperset of\b", "\u2283"), (r"\bunion\b", "\u222a"),
    (r"\bintersection\b", "\u2229"), (r"\bempty set\b", "\u2205"),
    (r"\bfactorial\b", "!"), (r"\bpercent\b", "%"),
    (r"\bperpendicular to\b", "\u22a5"), (r"\bparallel to\b", "\u2225"),
    (r"\bcongruent to\b", "\u2245"), (r"\bsimilar to\b", "\u223c"),
    (r"\btherefore\b", "\u2234"), (r"\bbecause\b", "\u2235"),
    (r"\bplus\b", "+"), (r"\bminus\b", "\u2212"), (r"\btimes\b", "\u00d7"),
    (r"\bmultiplied by\b", "\u00d7"), (r"\bdivided by\b", "\u00f7"),
    (r"\bequals\b", "="), (r"\bis equal to\b", "="),
    (r"\bsquared\b", "\u00b2"), (r"\bcubed\b", "\u00b3"),
    (r"\bdegrees\b", "\u00b0"), (r"\bdegree\b", "\u00b0"),
    (r"\btheta\b", "\u03b8"), (r"\balpha\b", "\u03b1"), (r"\bbeta\b", "\u03b2"),
    (r"\bgamma\b", "\u03b3"), (r"\bdelta\b", "\u03b4"), (r"\bepsilon\b", "\u03b5"),
    (r"\bzeta\b", "\u03b6"), (r"\beta\b", "\u03b7"), (r"\biota\b", "\u03b9"),
    (r"\bkappa\b", "\u03ba"), (r"\blambda\b", "\u03bb"), (r"\bmu\b", "\u03bc"),
    (r"\bnu\b", "\u03bd"), (r"\bxi\b", "\u03be"), (r"\bpi\b", "\u03c0"),
    (r"\brho\b", "\u03c1"), (r"\bsigma\b", "\u03c3"), (r"\btau\b", "\u03c4"),
    (r"\bphi\b", "\u03c6"), (r"\bchi\b", "\u03c7"), (r"\bpsi\b", "\u03c8"),
    (r"\bomega\b", "\u03c9"), (r"\bohm\b", "\u03a9"), (r"\bohms\b", "\u03a9"),
    (r"\bright arrow\b", "\u2192"), (r"\bimplies\b", "\u2192"),
    (r"\bapproaches\b", "\u2192"), (r"\btends to\b", "\u2192"), (r"\bconverges to\b", "\u2192"),
    (r"\bleft arrow\b", "\u2190"), (r"\bif and only if\b", "\u21d4"),
    (r"\biff\b", "\u21d4"), (r"\blogical and\b", "\u2227"),
    (r"\blogical or\b", "\u2228"), (r"\bnot\b", "\u00ac"),
    (r"\bmicro\b", "\u03bc"), (r"\bdot product\b", "\u00b7"),
    (r"\bcross product\b", "\u00d7"),
    (r"\btranspose of\b", "T "), (r"\binverse of\b", "\u207b\u00b9 "),
    (r"\bangle of\b", "\u2220"), (r"\bphase of\b", "\u2220"), (r"\bconjugate of\b", "*"),
    (r"\bgigahertz\b", "GHz"), (r"\bmegahertz\b", "MHz"), (r"\bkilohertz\b", "kHz"), (r"\bhertz\b", "Hz"),
    (r"\bmillivolts?\b", "mV"), (r"\bkilovolts?\b", "kV"), (r"\bvolts?\b", "V"),
    (r"\bmilliamps?\b", "mA"), (r"\bmilliamperes?\b", "mA"), (r"\bamperes?\b", "A"), (r"\bamps?\b", "A"),
    (r"\bkilowatts?\b", "kW"), (r"\bmilliwatts?\b", "mW"), (r"\bwatts?\b", "W"),
    (r"\bmicrofarads?\b", "\u00b5F"), (r"\bnanofarads?\b", "nF"), (r"\bpicofarads?\b", "pF"), (r"\bfarads?\b", "F"),
    (r"\bmillihenr(?:y|ies)\b", "mH"), (r"\bhenr(?:y|ies)\b", "H"),
    (r"\bkiloohms?\b", "k\u03a9"), (r"\bkilo ohms?\b", "k\u03a9"), (r"\bmegaohms?\b", "M\u03a9"), (r"\bmega ohms?\b", "M\u03a9"),
    (r"\bdecibels?\b", "dB"),

    # --- Extended set theory ---
    (r"\bsubset of or equal to\b", "\u2286"), (r"\bsuperset of or equal to\b", "\u2287"),
    (r"\bsymmetric difference\b", "\u2206"), (r"\bcardinality of\b", "|"),
    (r"\bset of natural numbers\b", "\u2115"), (r"\bset of integers\b", "\u2124"),
    (r"\bset of rational numbers\b", "\u211a"), (r"\bset of real numbers\b", "\u211d"),
    (r"\bset of complex numbers\b", "\u2102"),

    # --- Extended logic ---
    (r"\bexclusive or\b", "\u2295"), (r"\blogical not\b", "\u00ac"),
    (r"\bnand\b", "\u22bc"), (r"\bnor\b", "\u2193"),

    # --- Extended calculus / analysis ---
    (r"\bdefinite integral\b", "\u222b"), (r"\bsurface integral of\b", "\u222c"),
    (r"\bvolume integral of\b", "\u222d"), (r"\bpartial fraction\b", "partial fraction"),
    (r"\bwith respect to\b", "d/d"), (r"\bdel squared\b", "\u2207\u00b2"),

    # --- Statistics / probability extras ---
    (r"\bstandard normal distribution\b", "N(0, 1)"), (r"\bnormal distribution\b", "N"),
    (r"\bchi squared\b", "\u03c7\u00b2"), (r"\bp value\b", "p-value"),
    (r"\bconditional probability of\b", "P("),

    # --- Number theory / combinatorics glyphs ---
    (r"\bis prime\b", "is prime"), (r"\bcombinatorial coefficient\b", "C"),

    # --- Complex numbers / phasors (EE) ---
    (r"\bcomplex conjugate\b", "*"), (r"\bimaginary axis\b", "j-axis"),
    (r"\breal axis\b", "\u211d-axis"), (r"\bphasor\b", "phasor"), (r"\bangle\b", "\u2220"),

    # --- Vectors / linear algebra glyphs ---
    (r"\bdirect sum\b", "\u2295"), (r"\btensor product\b", "\u2297"),
    (r"\bidentity matrix\b", "I"), (r"\bzero matrix\b", "0"),

    # --- Radians / angles ---
    (r"\bradians?\b", "rad"), (r"\bpi radians\b", "\u03c0 rad"),

    # --- More EE units ---
    (r"\bsiemens\b", "S"), (r"\btesla\b", "T"), (r"\bweber\b", "Wb"),
    (r"\bcoulombs?\b", "C"), (r"\bjoules?\b", "J"), (r"\bnewtons?\b", "N"),
    (r"\bpascals?\b", "Pa"), (r"\bkelvin\b", "K"),
    (r"\bmilliseconds?\b", "ms"), (r"\bmicroseconds?\b", "\u00b5s"), (r"\bnanoseconds?\b", "ns"),
    (r"\bpicoseconds?\b", "ps"), (r"\bkilohms?\b", "k\u03a9"),
    (r"\bgigabits?\b", "Gb"), (r"\bmegabits?\b", "Mb"), (r"\bkilobits?\b", "kb"),
    (r"\bbits? per second\b", "bps"), (r"\bsamples per second\b", "Sa/s"),

    # --- Signals / systems (EE) ---
    (r"\bunit step function\b", "u(t)"), (r"\bunit impulse\b", "\u03b4(t)"),
    (r"\bdirac delta\b", "\u03b4"), (r"\bkronecker delta\b", "\u03b4"),
    (r"\btransfer function\b", "H(s)"), (r"\bimpulse response\b", "h(t)"),
    (r"\bfrequency response\b", "H(j\u03c9)"),
]


def apply_math_substitutions(text):
    # Order matters: multi-word / structural phrases first (they consume
    # surrounding context like "from a to b" or "as x approaches"), then
    # simpler unary "X of Y" forms, then the flat symbol/unit table last.
    result = _replace_definite_integral_variants(text)
    result = _replace_limit_variants(result)
    result = _replace_nth_derivative_variants(result)
    result = _replace_power_variants(result)
    result = _replace_subscript_variants(result)
    result = _replace_log_variants(result)
    result = _replace_function_of_variants(result)
    result = _replace_root_of_variants(result)
    result = _replace_fraction_variants(result)
    result = _replace_matrix_linear_algebra_variants(result)
    result = _replace_complex_number_variants(result)
    result = _replace_statistics_variants(result)
    result = _replace_number_theory_variants(result)
    result = _replace_combinatorics_variants(result)
    result = _replace_logic_gate_variants(result)
    result = _replace_convolution_variants(result)
    result = _replace_vector_notation_variants(result)
    for pattern, replacement in MATH_SUBSTITUTIONS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def parse_destination(text, default_destination=DEFAULT_DESTINATION):
    stripped = text.strip()
    lowered = stripped.lower()
    for alias in _DESTINATION_KEYS_BY_LENGTH:
        pattern = r"^" + re.escape(alias) + r"[\s,]*"
        match = re.match(pattern, lowered)
        if match:
            remainder = stripped[match.end():].strip()
            return DESTINATION_ALIASES[alias], remainder
    return default_destination, stripped


def open_search(destination, query):
    if not query:
        return
    url = SEARCH_URLS.get(destination, SEARCH_URLS[DEFAULT_DESTINATION]).format(
        urllib.parse.quote_plus(query))
    log(f"Opening: {destination} -> {url}")
    webbrowser.open(url)


# BUGFIX (from the original script): the old parse_app_command only matched
# when the app phrase immediately followed the trigger word ("open obsidian"),
# so anything with filler words ("open up obsidian", "open the file manager")
# silently failed to match and fell through to a web search instead. We now
# strip a small set of filler words after the trigger before alias-matching.
_APP_FILLER_WORDS = {"up", "the", "a", "an", "my"}


def parse_app_command(text):
    lowered = text.strip().lower()
    words = lowered.split()
    if not words:
        return None

    trigger_len = 0
    for trigger in sorted(APP_TRIGGER_WORDS, key=lambda t: -len(t.split())):
        trigger_words = trigger.split()
        if words[:len(trigger_words)] == trigger_words:
            trigger_len = len(trigger_words)
            break
    if trigger_len == 0:
        return None

    remainder_words = words[trigger_len:]
    while remainder_words and remainder_words[0] in _APP_FILLER_WORDS:
        remainder_words = remainder_words[1:]
    remainder = " ".join(remainder_words).strip().rstrip(",.")
    if not remainder:
        return None

    for alias in _APP_ALIAS_KEYS_BY_LENGTH:
        if remainder == alias or remainder.startswith(alias + " ") or remainder.startswith(alias + ","):
            return APP_ALIASES[alias]
    return None


def launch_app(app_id):
    label = APP_LABELS.get(app_id, app_id)
    for cmd in APP_LAUNCHERS.get(app_id, []):
        # BUGFIX: cmd.split() breaks any launcher entry whose path contains
        # spaces (e.g. "/Applications/Visual Studio Code.app" or
        # "C:\Program Files\...\Code.exe") into multiple bogus argv tokens,
        # so shutil.which(parts[0]) can never resolve them -- these entries
        # were silently unlaunchable. A path with no spaces still splits and
        # behaves exactly as before; only whole-path/bundle entries change.
        if os.path.isfile(cmd) or os.path.isdir(cmd) or shutil.which(cmd):
            parts = [cmd]
        else:
            parts = cmd.split()
        if not parts:
            continue
        exe = shutil.which(parts[0])
        if not exe and not os.path.isfile(parts[0]) and not os.path.isdir(parts[0]):
            continue
        try:
            if parts[0].endswith(".app") and os.path.isdir(parts[0]):
                # macOS application bundle -- exec'ing the .app directory
                # itself does nothing; it needs to go through `open`.
                subprocess.Popen(["open", parts[0]], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, start_new_session=True)
            else:
                subprocess.Popen(parts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            log(f"Launched {label} via '{cmd}'")
            return True, label
        except Exception as e:
            log(f"Failed to launch {label} via '{cmd}': {e}")
    log(f"Could not find an installed executable for {label}.")
    return False, label


# Voice command to open the Settings panel: wake word, then "open settings"
# or "open settings panel" (and a few natural variants). Mirrors
# parse_app_command's trigger + filler-word handling so "open up the
# settings panel" and similar phrasing also match.
_SETTINGS_TRIGGER_WORDS = ("open", "show", "launch")
_SETTINGS_TARGET_PHRASES = ("settings panel", "settings menu", "setting panel", "settings", "setting")


def is_open_settings_command(text):
    lowered = text.strip().lower().rstrip(",.!?")
    words = lowered.split()
    if not words:
        return False

    trigger_len = 0
    for trigger in sorted(_SETTINGS_TRIGGER_WORDS, key=lambda t: -len(t.split())):
        trigger_words = trigger.split()
        if words[:len(trigger_words)] == trigger_words:
            trigger_len = len(trigger_words)
            break
    if trigger_len == 0:
        return False

    remainder_words = words[trigger_len:]
    while remainder_words and remainder_words[0] in _APP_FILLER_WORDS:
        remainder_words = remainder_words[1:]
    remainder = " ".join(remainder_words).strip()

    return remainder in _SETTINGS_TARGET_PHRASES


# ============================================================================
# GUI -- every window below shares the Theme design system from theme.py.
# ============================================================================

class ToastWindow:
    """Small notification card, bottom-right, matching the app theme."""

    def __init__(self, root, theme, message, kind="success", duration_ms=2200, icon=None):
        self.top = tk.Toplevel(root)
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        try:
            self.top.attributes("-alpha", 0.0)
        except Exception:
            pass

        accent = {"success": theme.success, "danger": theme.danger, "info": theme.accent}.get(kind, theme.success)
        default_icon = {"success": "\u2713", "danger": "\u2715", "info": "\u2139"}.get(kind, "\u2713")
        icon = icon or default_icon

        card = tk.Frame(self.top, bg=theme.bg_elevated,
                         highlightbackground=theme.border, highlightthickness=1)
        card.pack()
        strip = tk.Frame(card, bg=accent, width=4)
        strip.pack(side="left", fill="y")
        inner = tk.Frame(card, bg=theme.bg_elevated)
        inner.pack(side="left", fill="both", expand=True, padx=(Theme.SPACE_MD, Theme.SPACE_LG), pady=Theme.SPACE_SM)
        row = tk.Frame(inner, bg=theme.bg_elevated)
        row.pack()
        tk.Label(row, text=icon, bg=theme.bg_elevated, fg=accent, font=theme.font(13, "bold")).pack(side="left", padx=(0, 8))
        tk.Label(row, text=message, bg=theme.bg_elevated, fg=theme.fg, font=theme.font_body(),
                 wraplength=280, justify="left").pack(side="left")

        self.top.update_idletasks()
        sw = self.top.winfo_screenwidth()
        sh = self.top.winfo_screenheight()
        w = self.top.winfo_width()
        h = self.top.winfo_height()
        self.top.geometry(f"+{sw - w - 24}+{sh - h - 70}")
        self._fade_in()
        self.top.after(duration_ms, self._fade_out)

    def _fade_in(self, step=0.0):
        try:
            step = min(1.0, step + 0.15)
            self.top.attributes("-alpha", step)
            if step < 1.0:
                self.top.after(15, lambda: self._fade_in(step))
        except Exception:
            pass

    def _fade_out(self, step=1.0):
        try:
            step = max(0.0, step - 0.15)
            self.top.attributes("-alpha", step)
            if step > 0.0:
                self.top.after(15, lambda: self._fade_out(step))
            else:
                self.top.destroy()
        except Exception:
            try:
                self.top.destroy()
            except Exception:
                pass


class ConfirmWindow:
    """Spotlight/Raycast-style command palette for reviewing a transcribed query.

    Redesign notes: the old version was a boxy fixed dialog with a plain
    Text box and three flat-colored buttons. This version centers a
    borderless rounded card near the top of the screen (like macOS
    Spotlight / Raycast / Alfred), shows which destination will be searched
    as a small pill instead of a plain label, and supports Enter-to-search /
    Escape-to-cancel for keyboard-first use.
    """

    def __init__(self, root, theme, initial_text, default_destination=DEFAULT_DESTINATION,
                 on_search_callback=None):
        self.theme = theme
        self.top = tk.Toplevel(root)
        self.top.title("Confirm search")
        self.top.overrideredirect(True)
        self.top.attributes("-topmost", True)
        apply_window_chrome(self.top, theme)

        destination, query = parse_destination(initial_text, default_destination)
        query = apply_math_substitutions(query)
        self.destination = destination
        self.initial_transcribed_text = initial_text
        self.on_search_callback = on_search_callback

        width, height = 560, 300
        sw = self.top.winfo_screenwidth()
        x = (sw - width) // 2
        y = int(self.top.winfo_screenheight() * 0.22)
        self.top.geometry(f"{width}x{height}+{x}+{y}")

        rc = RoundedCard(self.top, theme, radius=Theme.ROUND_LG)
        rc.pack(fill="both", expand=True, padx=Theme.SPACE_MD, pady=Theme.SPACE_MD)
        card = rc.body

        header = tk.Frame(card, bg=theme.bg_elevated)
        header.pack(fill="x", padx=Theme.SPACE_LG, pady=(Theme.SPACE_LG, Theme.SPACE_SM))

        tk.Label(header, text="\U0001f50d", bg=theme.bg_elevated, fg=theme.fg_muted,
                 font=theme.font(14)).pack(side="left", padx=(0, 8))
        tk.Label(header, text="Search query", bg=theme.bg_elevated, fg=theme.fg_muted,
                 font=theme.font_small_bold()).pack(side="left")

        self._dest_pill = self._make_pill(header, self._destination_display(destination))
        self._dest_pill.pack(side="right")

        text_wrap = tk.Frame(card, bg=theme.bg_elevated_2, highlightbackground=theme.border,
                              highlightthickness=1, bd=0)
        text_wrap.pack(fill="both", expand=True, padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_SM))

        self.text_box = tk.Text(text_wrap, height=5, wrap="word", undo=True,
                                 font=theme.font_body(), bg=theme.bg_elevated_2, fg=theme.fg,
                                 insertbackground=theme.fg, relief="flat", bd=0,
                                 padx=Theme.SPACE_MD, pady=Theme.SPACE_MD,
                                 selectbackground=theme.accent, selectforeground=theme.accent_fg)
        self.text_box.insert("1.0", query)
        self.text_box.pack(fill="both", expand=True)
        self._bind_shortcuts()

        hint = tk.Label(card, text="Enter to search \u00b7 Shift+Enter for newline \u00b7 Esc to cancel",
                         bg=theme.bg_elevated, fg=theme.fg_faint, font=theme.font_small(), anchor="w")
        hint.pack(fill="x", padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_SM))

        btn_row = tk.Frame(card, bg=theme.bg_elevated)
        btn_row.pack(fill="x", padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_LG))

        go_btn = PillButton(btn_row, theme, "Go", kind="primary", command=self._on_go, width=100)
        go_btn.pack(side="right")
        cancel_btn = PillButton(btn_row, theme, "Cancel", kind="ghost", command=self._on_cancel, width=90)
        cancel_btn.pack(side="right", padx=(0, Theme.SPACE_SM))
        self.copy_btn = PillButton(btn_row, theme, "Copy", kind="secondary", command=self._on_copy, width=90)
        self.copy_btn.pack(side="left")

        self.top.bind("<Escape>", lambda e: self._on_cancel())
        self.top.bind("<Return>", self._on_enter_key)
        self.top.bind("<FocusOut>", lambda e: None)

        self.text_box.focus_set()
        self.text_box.mark_set("insert", "end")

    def _destination_display(self, destination):
        return destination.replace("_", " ").title()

    def _make_pill(self, parent, text):
        theme = self.theme
        pill = tk.Frame(parent, bg=theme.bg_elevated_2, highlightbackground=theme.border_strong,
                         highlightthickness=1)
        tk.Label(pill, text=text, bg=theme.bg_elevated_2, fg=theme.accent,
                 font=theme.font_small_bold(), padx=Theme.SPACE_SM, pady=3).pack()
        return pill

    def _bind_shortcuts(self):
        widget = self.text_box
        widget.bind("<Control-a>", lambda e: (widget.tag_add("sel", "1.0", "end-1c"), "break"))
        widget.bind("<Control-A>", lambda e: (widget.tag_add("sel", "1.0", "end-1c"), "break"))
        widget.bind("<Control-BackSpace>", lambda e: (widget.delete("insert-1c wordstart", "insert"), "break"))
        widget.bind("<Control-y>", lambda e: (widget.edit_redo(), "break"))
        widget.bind("<Control-Shift-Key-Z>", lambda e: (widget.edit_redo(), "break"))
        widget.bind("<Shift-Return>", lambda e: None)  # allow newline
        widget.bind("<Return>", self._on_enter_key)

    def _on_enter_key(self, event):
        # Shift+Return should insert a newline rather than submit.
        if event.state & 0x0001:
            return None
        self._on_go()
        return "break"

    def _on_copy(self):
        text = self.text_box.get("1.0", "end").strip()
        self.top.clipboard_clear()
        self.top.clipboard_append(text)
        self.top.update()
        self.copy_btn.set_text("Copied!")
        self.copy_btn.set_kind("primary")
        self.top.after(1200, lambda: (self.copy_btn.set_text("Copy"), self.copy_btn.set_kind("secondary")))

    def _on_go(self):
        query = self.text_box.get("1.0", "end").strip()
        open_search(self.destination, query)
        if self.on_search_callback:
            self.on_search_callback(self.destination, self.initial_transcribed_text, query)
        self.top.destroy()

    def _on_cancel(self):
        log("Cancelled -- no search sent.")
        self.top.destroy()


class HistoryWindow:
    """Search history browser: themed data table with filtering, sorting,
    multi-select bulk actions, favorites/pins, and export.

    History entries are plain dicts (see App.add_to_history) with keys
    datetime/destination/transcribed/query, plus an optional "favorite"
    bool that older history.json files won't have -- every read of that
    key goes through entry.get("favorite", False) so old data loads fine.
    """

    COLUMNS = ("pin", "idx", "datetime", "destination", "transcribed", "query")

    def __init__(self, root, theme, history_deque, on_rerun, on_save):
        self.theme = theme
        self.top = tk.Toplevel(root)
        self.top.title("Search History")
        self.top.attributes("-topmost", True)
        self.top.geometry("880x520")
        self.top.minsize(680, 360)
        apply_window_chrome(self.top, theme)
        style_ttk(self.top, theme)

        self.history_deque = history_deque
        self.on_rerun = on_rerun
        self.on_save = on_save
        self._filter_text = tk.StringVar()
        self._dest_filter = tk.StringVar(value="All destinations")
        self._sort_key = "idx"
        self._sort_reverse = True  # newest first by default

        header = tk.Frame(self.top, bg=theme.bg)
        header.pack(fill="x", padx=Theme.SPACE_LG, pady=(Theme.SPACE_LG, Theme.SPACE_SM))
        tk.Label(header, text="Search History", bg=theme.bg, fg=theme.fg,
                 font=theme.font_title()).pack(side="left")

        search_wrap = tk.Frame(header, bg=theme.bg_elevated_2, highlightbackground=theme.border,
                                highlightthickness=1)
        search_wrap.pack(side="right")
        tk.Label(search_wrap, text="\U0001f50d", bg=theme.bg_elevated_2, fg=theme.fg_faint,
                 font=theme.font_small()).pack(side="left", padx=(8, 2))
        search_entry = tk.Entry(search_wrap, textvariable=self._filter_text, bg=theme.bg_elevated_2,
                                 fg=theme.fg, relief="flat", insertbackground=theme.fg,
                                 font=theme.font_body(), width=22)
        search_entry.pack(side="left", ipady=4, padx=(0, 8))
        self._filter_text.trace_add("write", lambda *a: self._populate_tree())

        # Destination filter dropdown, populated from whatever destinations
        # actually appear in history (not the full SEARCH_URLS catalog --
        # a dropdown listing 15 destinations you've never searched is just
        # noise, and it needs to update as history grows).
        self.dest_combo = ttk.Combobox(header, textvariable=self._dest_filter, state="readonly",
                                        width=16, font=theme.font_body())
        self.dest_combo.pack(side="right", padx=(0, Theme.SPACE_SM))
        self.dest_combo.bind("<<ComboboxSelected>>", lambda e: self._populate_tree())

        # Toolbar: bulk-action buttons, only enabled when rows are selected.
        toolbar = tk.Frame(self.top, bg=theme.bg)
        toolbar.pack(fill="x", padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_SM))
        tk.Label(toolbar, text="Click \u2605 to pin \u00b7 click a column header to sort \u00b7 double-click a row to re-run",
                 bg=theme.bg, fg=theme.fg_faint, font=theme.font_small()).pack(side="left")
        self.export_btn = PillButton(toolbar, theme, "Export\u2026", kind="secondary",
                                      command=self._export, width=100)
        self.export_btn.pack(side="right")

        table_card = tk.Frame(self.top, bg=theme.bg_elevated, highlightbackground=theme.border,
                               highlightthickness=1)
        table_card.pack(fill="both", expand=True, padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_SM))

        self.tree = ttk.Treeview(table_card, columns=self.COLUMNS, show="headings",
                                  selectmode="extended")
        self.tree.heading("pin", text="\u2605")
        self.tree.column("pin", width=28, anchor="center", stretch=False)
        self.tree.heading("idx", text="#", command=lambda: self._sort_by("idx"))
        self.tree.column("idx", width=40, anchor="center", stretch=False)
        self.tree.heading("datetime", text="Date & Time", command=lambda: self._sort_by("datetime"))
        self.tree.column("datetime", width=150, anchor="w")
        self.tree.heading("destination", text="Website", command=lambda: self._sort_by("destination"))
        self.tree.column("destination", width=110, anchor="w")
        self.tree.heading("transcribed", text="Transcribed Text", command=lambda: self._sort_by("transcribed"))
        self.tree.column("transcribed", width=220, anchor="w")
        self.tree.heading("query", text="Final Query", command=lambda: self._sort_by("query"))
        self.tree.column("query", width=220, anchor="w")

        tree_scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        tree_scroll.pack(side="right", fill="y", pady=1, padx=(0, 1))
        self.tree.bind("<Double-1>", self._on_row_double_click)
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_selection_state())
        self.tree.bind("<Delete>", lambda e: self._delete_selected())

        self._populate_tree()

        btn_row = tk.Frame(self.top, bg=theme.bg)
        btn_row.pack(fill="x", padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_LG))

        self.count_label = tk.Label(btn_row, text="", bg=theme.bg, fg=theme.fg_faint, font=theme.font_small())
        self.count_label.pack(side="left")

        PillButton(btn_row, theme, "Close", kind="ghost", command=self.top.destroy, width=90).pack(side="right")
        PillButton(btn_row, theme, "Clear All", kind="danger", command=self._on_clear_all, width=110).pack(side="right", padx=(0, Theme.SPACE_SM))
        self.delete_btn = PillButton(btn_row, theme, "Delete Selected", kind="danger",
                                      command=self._delete_selected, width=150)
        self.delete_btn.pack(side="right", padx=(0, Theme.SPACE_SM))
        self.rerun_btn = PillButton(btn_row, theme, "Re-run Selected", kind="primary",
                                     command=self._on_rerun, width=150)
        self.rerun_btn.pack(side="right", padx=(0, Theme.SPACE_SM))
        self._update_selection_state()

    # -- data helpers ---------------------------------------------------
    def _entries_with_index(self):
        """Return [(1-based index into history_deque, entry_dict), ...]."""
        return list(enumerate(list(self.history_deque), start=1))

    def _refresh_destination_choices(self):
        seen = sorted({e.get("destination", "") for _, e in self._entries_with_index() if e.get("destination")})
        values = ["All destinations"] + seen
        self.dest_combo.configure(values=values)
        if self._dest_filter.get() not in values:
            self._dest_filter.set("All destinations")

    def _sort_by(self, key):
        if self._sort_key == key:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_key = key
            self._sort_reverse = key in ("idx", "datetime")  # newest-first defaults for these
        self._populate_tree()

    def _populate_tree(self):
        self._refresh_destination_choices()
        for item in self.tree.get_children():
            self.tree.delete(item)

        needle = self._filter_text.get().strip().lower()
        dest_filter = self._dest_filter.get()
        rows = []
        for idx, entry in self._entries_with_index():
            transcribed = entry.get("transcribed", "")
            query = entry.get("query", "")
            destination = entry.get("destination", "")
            if needle and needle not in transcribed.lower() and needle not in query.lower() and needle not in destination.lower():
                continue
            if dest_filter != "All destinations" and destination != dest_filter:
                continue
            rows.append((idx, entry))

        total = len(list(self.history_deque))
        shown = len(rows)

        # Pinned entries always float to the top regardless of the active
        # sort column, then the chosen sort applies within each group --
        # this is what makes "pin" meaningfully different from just another
        # sortable column.
        def sort_key_fn(row):
            idx, entry = row
            pinned = entry.get("favorite", False)
            if self._sort_key == "idx":
                base = idx
            else:
                base = str(entry.get(self._sort_key, "")).lower()
            return (0 if pinned else 1, base)

        rows.sort(key=sort_key_fn, reverse=self._sort_reverse)
        # Re-sort so pinned-first ordering survives the reverse flag above
        # (reverse=True on a tuple would also flip the pin priority, which
        # we don't want -- pinned should always be first, sort direction
        # only affects order *within* the pinned/unpinned groups).
        rows.sort(key=lambda r: 0 if r[1].get("favorite", False) else 1)

        for idx, entry in rows:
            transcribed = entry.get("transcribed", "")
            query = entry.get("query", "")
            pin_mark = "\u2605" if entry.get("favorite", False) else "\u2606"
            self.tree.insert("", "end", iid=str(idx), values=(
                pin_mark,
                idx,
                entry.get("datetime", ""),
                entry.get("destination", ""),
                (transcribed[:35] + "...") if len(transcribed) > 35 else transcribed,
                (query[:40] + "...") if len(query) > 40 else query
            ))

        if hasattr(self, "count_label"):
            suffix = " (filtered)" if (needle or dest_filter != "All destinations") else ""
            self.count_label.config(text=f"{shown} of {total} entries{suffix}")

    def _on_row_double_click(self, event):
        # A click that landed on the pin column toggles the pin instead of
        # re-running the search -- otherwise pinning would require a
        # separate button and an extra click every time.
        region = self.tree.identify_region(event.x, event.y)
        col = self.tree.identify_column(event.x)
        row = self.tree.identify_row(event.y)
        if region == "cell" and col == "#1" and row:
            self._toggle_pin(int(row))
            return
        self._on_rerun()

    def _toggle_pin(self, idx):
        entries = list(self.history_deque)
        if not (1 <= idx <= len(entries)):
            return
        entry = entries[idx - 1]
        entry["favorite"] = not entry.get("favorite", False)
        self._commit(entries)
        self._populate_tree()

    def _update_selection_state(self):
        has_selection = bool(self.tree.selection())
        self.rerun_btn.set_enabled(len(self.tree.selection()) == 1)
        self.delete_btn.set_enabled(has_selection)

    def _on_rerun(self):
        selected = self.tree.selection()
        if len(selected) != 1:
            return
        idx = int(selected[0])
        entries = list(self.history_deque)
        if not (1 <= idx <= len(entries)):
            return
        entry = entries[idx - 1]
        self.on_rerun(entry.get("destination"), entry.get("query"))
        self.top.destroy()

    def _delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            return
        indices_to_remove = {int(i) for i in selected}
        entries = list(self.history_deque)
        kept = [e for i, e in enumerate(entries, start=1) if i not in indices_to_remove]
        self._commit(kept)
        self._populate_tree()
        self._update_selection_state()

    def _on_clear_all(self):
        self._commit([])
        self._populate_tree()
        self._update_selection_state()

    def _commit(self, new_entries_list):
        # Rebuild the deque in place (preserving its maxlen) rather than
        # reassigning self.history_deque, since App holds its own reference
        # to the same deque object and would otherwise go stale.
        self.history_deque.clear()
        self.history_deque.extend(new_entries_list)
        self.on_save()

    def _export(self):
        rows = [entry for _, entry in self._entries_with_index()]
        if not rows:
            log("No history entries to export.")
            return
        path = filedialog.asksaveasfilename(
            parent=self.top, title="Export search history",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("CSV", "*.csv")])
        if not path:
            return
        try:
            if path.lower().endswith(".csv"):
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=["datetime", "destination", "transcribed", "query", "favorite"])
                    writer.writeheader()
                    for entry in rows:
                        writer.writerow({
                            "datetime": entry.get("datetime", ""),
                            "destination": entry.get("destination", ""),
                            "transcribed": entry.get("transcribed", ""),
                            "query": entry.get("query", ""),
                            "favorite": entry.get("favorite", False),
                        })
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(rows, f, indent=2)
            log(f"Exported {len(rows)} history entries to {path}")
        except OSError as e:
            log(f"Failed to export history: {e}")


class StatusWindow:
    """Main floating status widget -- redesigned as a compact rounded card.

    Visual reference points: macOS Siri's small floating orb/status bar,
    and Raycast's compact bottom-bar indicator. The meter is drawn on a
    canvas with rounded bar caps and a soft color ramp instead of blocky
    flat-colored rectangles.
    """

    METER_BAR_COUNT = 28
    METER_MAX_RMS = 6000
    METER_DECAY = 0.75

    def __init__(self, root, on_quit, on_settings, wake_word, size_name, theme):
        self.theme = theme
        self.top = tk.Toplevel(root)
        self.top.title("Voice search")
        self.top.attributes("-topmost", True)
        self.top.protocol("WM_DELETE_WINDOW", on_quit)
        apply_window_chrome(self.top, theme)

        self.on_settings = on_settings
        self.wake_word = wake_word
        self._idle_text = None
        self._status_dot_color = theme.fg_muted

        self._build_widgets()
        self.apply_size(size_name)
        self.set_wake_word(wake_word)
        self.set_idle()

    def _build_widgets(self):
        theme = self.theme
        # Outer 1px border frame simulates a rounded-card look within Tk's limits.
        self.border = tk.Frame(self.top, bg=theme.border)
        self.border.pack(fill="both", expand=True, padx=1, pady=1)
        self.card = tk.Frame(self.border, bg=theme.bg_elevated)
        self.card.pack(fill="both", expand=True)

        self.top_row = tk.Frame(self.card, bg=theme.bg_elevated)
        self.top_row.pack(fill="x", padx=Theme.SPACE_MD, pady=(Theme.SPACE_MD, 0))

        self.status_dot = tk.Canvas(self.top_row, width=10, height=10, bg=theme.bg_elevated,
                                     highlightthickness=0)
        self.status_dot.pack(side="left", padx=(0, 8))
        self._draw_dot(theme.fg_muted)

        self.status_label = tk.Label(self.top_row, text="", font=theme.font_body_bold(),
                                      anchor="w", justify="left", bg=theme.bg_elevated, fg=theme.fg)
        self.status_label.pack(side="left", fill="x", expand=True)

        self.settings_btn = tk.Label(self.top_row, text="\u2699", bg=theme.bg_elevated, fg=theme.fg_muted,
                                      font=theme.font(14), cursor="hand2")
        self.settings_btn.pack(side="right")
        self.settings_btn.bind("<Button-1>", lambda e: self.on_settings())
        self.settings_btn.bind("<Enter>", lambda e: self.settings_btn.config(fg=theme.fg))
        self.settings_btn.bind("<Leave>", lambda e: self.settings_btn.config(fg=theme.fg_muted))

        self.hotkey_label = tk.Label(self.card, text=f"or press {HOTKEY_COMBO_DEFAULT}",
                                      font=theme.font_small(), bg=theme.bg_elevated, fg=theme.fg_faint)
        self.hotkey_label.pack(pady=(2, Theme.SPACE_SM))

        self.meter_canvas = tk.Canvas(self.card, highlightthickness=0, bg=theme.bg_elevated)
        self.meter_canvas.pack(pady=(0, Theme.SPACE_SM), padx=Theme.SPACE_MD, fill="x")
        self._smoothed_frac = 0.0
        self._bar_ids = []

        btn_row = tk.Frame(self.card, bg=theme.bg_elevated)
        btn_row.pack(pady=(0, Theme.SPACE_MD))
        self.quit_btn = PillButton(btn_row, self.theme, "Quit", kind="danger",
                                    command=self._quit_clicked, width=90, height=30)
        self.quit_btn.pack()
        self._quit_cb = None

    def _quit_clicked(self):
        if self._quit_cb:
            self._quit_cb()

    def _draw_dot(self, color):
        self.status_dot.delete("all")
        self.status_dot.create_oval(1, 1, 9, 9, fill=color, outline="")

    def apply_theme(self, theme):
        self.theme = theme
        # Rebuild widgets fully so every color token (including PillButton
        # canvases) picks up the new palette -- partial re-theming was a
        # source of stale colors in the original per-window approach.
        size_name = getattr(self, "size_name", DEFAULT_WINDOW_SIZE)
        wake_word = self.wake_word
        quit_cb = self._quit_cb
        for child in list(self.top.winfo_children()):
            child.destroy()
        apply_window_chrome(self.top, theme)
        self._build_widgets()
        self.set_quit_callback(quit_cb)
        self.apply_size(size_name)
        self.set_wake_word(wake_word)
        self.set_idle()

    def apply_size(self, size_name):
        if size_name == "Hidden":
            # Fully withdraw the window rather than shrinking it to 0x0 --
            # a 0-size Toplevel still exists in the taskbar/window list on
            # some window managers and can still steal focus on click.
            self.size_name = size_name
            self.top.withdraw()
            return
        if self.top.state() == "withdrawn":
            self.top.deiconify()

        width, height, show_meter, show_hotkey, font_scale = WINDOW_SIZES.get(
            size_name, WINDOW_SIZES[DEFAULT_WINDOW_SIZE])
        self.size_name = size_name

        pos = self.top.geometry().split("+", 1)
        offset = "+" + pos[1] if len(pos) > 1 else "+40+40"
        self.top.geometry(f"{width}x{height}{offset}")

        is_mini = size_name == "Mini"
        # Mini mode drops the status text and quit button entirely, leaving
        # only the status dot and a right-click menu (wired in App) to reach
        # settings/quit -- it's meant to be a small always-on-top indicator,
        # not a miniature version of the full status card.
        if is_mini:
            self.status_label.pack_forget()
            self.settings_btn.pack_forget()
            self.top_row.pack_configure(padx=0, pady=(Theme.SPACE_SM, 0))
            self.status_dot.pack_configure(padx=0)
            self.quit_btn.master.pack_forget()
        else:
            if not self.status_label.winfo_ismapped():
                self.status_label.pack(side="left", fill="x", expand=True)
            if not self.settings_btn.winfo_ismapped():
                self.settings_btn.pack(side="right")
            self.top_row.pack_configure(padx=Theme.SPACE_MD, pady=(Theme.SPACE_MD, 0))
            self.status_dot.pack_configure(padx=(0, 8))
            if not self.quit_btn.master.winfo_ismapped():
                self.quit_btn.master.pack(pady=(0, Theme.SPACE_MD))

        status_size = max(9, round(11 * font_scale))
        hotkey_size = max(7, round(8 * font_scale))
        self.status_label.config(font=self.theme.font(status_size, "bold"), wraplength=max(width - 70, 40))
        self.hotkey_label.config(font=self.theme.font(hotkey_size))

        if show_hotkey and not is_mini:
            self.hotkey_label.pack(pady=(2, Theme.SPACE_SM))
        else:
            self.hotkey_label.pack_forget()

        meter_height = max(16, round(30 * font_scale))
        self.meter_canvas.config(height=meter_height)
        if show_meter and not is_mini:
            self.meter_canvas.pack(pady=(0, Theme.SPACE_SM), padx=Theme.SPACE_MD, fill="x")
        else:
            self.meter_canvas.pack_forget()

        self.top.update_idletasks()
        self._rebuild_meter_bars()
        self._redraw_meter(self._smoothed_frac)

    def _rebuild_meter_bars(self):
        self.meter_canvas.delete("all")
        self._bar_ids = []
        width = self.meter_canvas.winfo_width() or 280
        height = int(self.meter_canvas.cget("height"))
        self._meter_height = height
        bar_gap = 3
        bar_width = max(2.0, (width - bar_gap * (self.METER_BAR_COUNT - 1)) / self.METER_BAR_COUNT)
        for i in range(self.METER_BAR_COUNT):
            x0 = i * (bar_width + bar_gap)
            bar_id = self.meter_canvas.create_rectangle(
                x0, height, x0 + bar_width, height, fill=self.theme.meter_off, width=0)
            self._bar_ids.append(bar_id)

    def set_wake_word(self, wake_word):
        self.wake_word = wake_word
        label = WAKE_WORD_LABELS.get(wake_word, wake_word)
        self._idle_text = f"Idle \u2014 say \u201c{label}\u201d"
        if self.status_label.cget("text").startswith("Idle"):
            self.status_label.config(text=self._idle_text)

    def set_hotkey_label(self, combo):
        self.hotkey_label.config(text=f"or press {combo}")

    def set_quit_callback(self, cb):
        self._quit_cb = cb

    def set_idle(self):
        self.status_label.config(text=self._idle_text, fg=self.theme.fg)
        self._draw_dot(self.theme.fg_muted)
        self._smoothed_frac = 0.0
        self._redraw_meter(0.0)

    def set_listening(self):
        label = WAKE_WORD_LABELS.get(self.wake_word, self.wake_word)
        self.status_label.config(text=f"Listening\u2026 say \u201c{label}\u201d or hotkey to stop", fg=self.theme.success)
        self._draw_dot(self.theme.success)

    def set_transcribing(self):
        self.status_label.config(text="Transcribing\u2026", fg=self.theme.warning)
        self._draw_dot(self.theme.warning)
        self._smoothed_frac = 0.0
        self._redraw_meter(0.0)

    def set_timed_out(self):
        self.status_label.config(text="No speech detected \u2014 stopped", fg=self.theme.danger)
        self._draw_dot(self.theme.danger)
        self._smoothed_frac = 0.0
        self._redraw_meter(0.0)

    def set_meter(self, rms):
        target_frac = min(1.0, rms / self.METER_MAX_RMS)
        self._smoothed_frac = (self.METER_DECAY * self._smoothed_frac
                                + (1 - self.METER_DECAY) * target_frac)
        self._redraw_meter(self._smoothed_frac)

    def _redraw_meter(self, frac):
        if not self._bar_ids:
            return
        height = self._meter_height
        lit_bars = round(frac * self.METER_BAR_COUNT)
        theme = self.theme
        for i, bar_id in enumerate(self._bar_ids):
            if i < lit_bars:
                bar_frac = i / self.METER_BAR_COUNT
                if bar_frac < 0.6:
                    color = theme.meter_low
                elif bar_frac < 0.85:
                    color = theme.meter_mid
                else:
                    color = theme.meter_high
                bar_h = height
            else:
                color = theme.meter_off
                bar_h = max(2, round(height * 0.16))
            coords = self.meter_canvas.coords(bar_id)
            x0, x1 = coords[0], coords[2]
            y_top = height - bar_h
            self.meter_canvas.coords(bar_id, x0, y_top, x1, height)
            self.meter_canvas.itemconfig(bar_id, fill=color)


class SettingsWindow:
    """Settings, redesigned with a sidebar (General / Behavior / Audio /
    Advanced / Apps / Actions) instead of one long scrolling column of
    LabelFrames. Each pane is built once and swapped via raise_/lower via a
    simple show/hide, similar to macOS System Settings or VS Code Settings.
    """

    SECTIONS = [
        ("general", "General", "\u2699"),
        ("behavior", "Behavior", "\U0001f39a"),
        ("audio", "Audio & Tones", "\U0001f50a"),
        ("advanced", "Advanced", "\U0001f9ea"),
        ("apps", "Voice Apps", "\U0001f4f1"),
        ("actions", "Actions", "\u2b50"),
    ]

    def __init__(self, root, theme, pa, settings, available_wake_word_ids, callbacks):
        self.root = root
        self.theme = theme
        self.pa = pa
        self.settings = settings
        self.available_wake_word_ids = available_wake_word_ids
        self.cb = callbacks
        self._active_key_recorder_widget = None
        self._recording_var_name = None
        self.tone_var = None
        self.tone_volume_var = None

        self.top = tk.Toplevel(root)
        self.top.title("Settings")
        self.top.attributes("-topmost", True)
        self.top.geometry("680x560")
        self.top.minsize(560, 420)
        apply_window_chrome(self.top, theme)
        style_ttk(self.top, theme)
        self.top.bind("<Destroy>", self._on_destroy)

        body = tk.Frame(self.top, bg=theme.bg)
        body.pack(fill="both", expand=True)

        # -- sidebar --
        sidebar = tk.Frame(body, bg=theme.bg_elevated_2, width=180)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        tk.Label(sidebar, text="Settings", bg=theme.bg_elevated_2, fg=theme.fg,
                 font=theme.font_title(), anchor="w").pack(fill="x", padx=Theme.SPACE_LG, pady=(Theme.SPACE_LG, Theme.SPACE_MD))

        self._nav_buttons = {}
        for key, label, icon in self.SECTIONS:
            row = tk.Frame(sidebar, bg=theme.bg_elevated_2, cursor="hand2")
            row.pack(fill="x", padx=Theme.SPACE_SM, pady=1)
            lbl = tk.Label(row, text=f"{icon}   {label}", bg=theme.bg_elevated_2, fg=theme.fg_muted,
                            font=theme.font_body(), anchor="w", padx=Theme.SPACE_SM, pady=8, cursor="hand2")
            lbl.pack(fill="x")
            for widget in (row, lbl):
                widget.bind("<Button-1>", lambda e, k=key: self._show_section(k))
            self._nav_buttons[key] = (row, lbl)

        # -- content area --
        content_outer = tk.Frame(body, bg=theme.bg)
        content_outer.pack(side="left", fill="both", expand=True)

        canvas = tk.Canvas(content_outer, bg=theme.bg, highlightthickness=0)
        vscroll = ttk.Scrollbar(content_outer, orient="vertical", command=canvas.yview)
        self.content = tk.Frame(canvas, bg=theme.bg)
        self._canvas = canvas

        self.content.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas_window = canvas.create_window((0, 0), window=self.content, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfig(canvas_window, width=e.width))
        canvas.configure(yscrollcommand=vscroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        vscroll.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self._unbind_wheel = lambda: canvas.unbind_all("<MouseWheel>")

        self._sections = {}
        self._build_general_section()
        self._build_behavior_section()
        self._build_audio_section()
        self._build_advanced_section()
        self._build_apps_section()
        self._build_actions_section()

        self._show_section("general")

    # -- layout helpers -----------------------------------------------------
    def _on_destroy(self, event):
        if event.widget is self.top:
            try:
                self._unbind_wheel()
            except Exception:
                pass

    def _show_section(self, key):
        for k, frame in self._sections.items():
            frame.pack_forget()
        self._sections[key].pack(fill="both", expand=True, padx=Theme.SPACE_XL, pady=Theme.SPACE_LG)
        for k, (row, lbl) in self._nav_buttons.items():
            active = (k == key)
            bg = self.theme.bg_hover if active else self.theme.bg_elevated_2
            fg = self.theme.fg if active else self.theme.fg_muted
            row.configure(bg=bg)
            lbl.configure(bg=bg, fg=fg, font=self.theme.font_body_bold() if active else self.theme.font_body())
        self._canvas.yview_moveto(0)

    def _new_section(self, key):
        frame = tk.Frame(self.content, bg=self.theme.bg)
        self._sections[key] = frame
        return frame

    def _section_title(self, parent, text, subtitle=None):
        tk.Label(parent, text=text, bg=self.theme.bg, fg=self.theme.fg,
                 font=self.theme.font_title(), anchor="w").pack(fill="x", pady=(0, 2))
        if subtitle:
            tk.Label(parent, text=subtitle, bg=self.theme.bg, fg=self.theme.fg_muted,
                     font=self.theme.font_body(), anchor="w", wraplength=420, justify="left").pack(fill="x", pady=(0, Theme.SPACE_LG))
        else:
            tk.Frame(parent, bg=self.theme.bg, height=Theme.SPACE_LG).pack()

    def _row_card(self, parent, label, control_builder, description=None):
        theme = self.theme
        card = tk.Frame(parent, bg=theme.bg_elevated, highlightbackground=theme.border, highlightthickness=1)
        card.pack(fill="x", pady=(0, Theme.SPACE_SM))
        inner = tk.Frame(card, bg=theme.bg_elevated)
        inner.pack(fill="x", padx=Theme.SPACE_MD, pady=Theme.SPACE_SM)

        left = tk.Frame(inner, bg=theme.bg_elevated)
        left.pack(side="left", fill="x", expand=True)
        tk.Label(left, text=label, bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(fill="x")
        if description:
            tk.Label(left, text=description, bg=theme.bg_elevated, fg=theme.fg_muted,
                     font=theme.font_small(), anchor="w", wraplength=280, justify="left").pack(fill="x")

        right = tk.Frame(inner, bg=theme.bg_elevated)
        right.pack(side="right")
        control_builder(right)
        return card

    def _combo(self, parent, values, current, on_change, width=20):
        var = tk.StringVar(value=current)
        menu = ttk.Combobox(parent, textvariable=var, values=values, state="readonly", width=width)
        menu.pack()
        menu.bind("<<ComboboxSelected>>", lambda e: on_change(var.get()))
        return var

    def _toggle(self, parent, current, on_change):
        return toggle_switch(parent, self.theme, current, on_change)

    # -- General --------------------------------------------------------
    def _build_general_section(self):
        frame = self._new_section("general")
        self._section_title(frame, "General", "Wake word, appearance, and default search engine.")

        wake_word_choices = [WAKE_WORD_LABELS.get(w, w) for w in self.available_wake_word_ids]
        self._wake_word_by_label = {WAKE_WORD_LABELS.get(w, w): w for w in self.available_wake_word_ids}
        current_label = WAKE_WORD_LABELS.get(self.settings["wake_word"], self.settings["wake_word"])
        self._row_card(frame, "Wake Word", lambda p: self._combo(
            p, wake_word_choices, current_label,
            lambda v: self.cb["on_wake_word_change"](self._wake_word_by_label.get(v))),
            description="The phrase that activates listening hands-free.")

        self._row_card(frame, "Window Size", lambda p: self._combo(
            p, list(WINDOW_SIZES.keys()), self.settings["window_size"], self.cb["on_size_change"]))

        self._row_card(frame, "Interface Theme", lambda p: self._combo(
            p, UI_THEME_NAMES, self.settings.get("ui_theme", DEFAULT_UI_THEME), self.cb["on_theme_change"]))

        self._row_card(frame, "Default Search Destination", lambda p: self._combo(
            p, sorted(SEARCH_URLS.keys()), self.settings["default_destination"],
            self.cb["on_destination_change"], width=22))

    # -- Behavior ---------------------------------------------------------
    def _build_behavior_section(self):
        frame = self._new_section("behavior")
        self._section_title(frame, "Behavior", "How the app reacts once it has your transcript.")

        self._row_card(frame, "Search immediately", lambda p: self._toggle(
            p, self.settings.get("auto_search", False), self.cb["on_auto_search_change"]).pack(),
            description="Skip the confirm popup and search right away.")

        self._row_card(frame, "Auto-copy transcript to clipboard", lambda p: self._toggle(
            p, self.settings.get("clipboard_auto_copy", False), self.cb["on_clipboard_change"]).pack())

        self._row_card(frame, "Allow 'open <app>' voice commands", lambda p: self._toggle(
            p, self.settings.get("app_launch_enabled", True), self.cb["on_app_launch_change"]).pack(),
            description="Say things like \u201copen VS Code\u201d to launch local apps instead of searching.")

        lang_labels = list(SPEECH_LANGUAGES.keys())
        current_lang_label = next((k for k, v in SPEECH_LANGUAGES.items()
                                    if v == self.settings.get("speech_language", DEFAULT_SPEECH_LANGUAGE)), lang_labels[0])
        self._row_card(frame, "Speech Recognition Language", lambda p: self._combo(
            p, lang_labels, current_lang_label,
            lambda v: self.cb["on_language_change"](SPEECH_LANGUAGES[v])))

        devices = list_input_devices(self.pa)
        device_labels = ["System default"] + [f"{i}: {name}" for i, name in devices]
        current_idx = self.settings.get("mic_device_index")
        current_device_label = "System default"
        if current_idx is not None:
            for i, name in devices:
                if i == current_idx:
                    current_device_label = f"{i}: {name}"
        self._row_card(frame, "Microphone", lambda p: self._combo(
            p, device_labels, current_device_label,
            lambda v: self.cb["on_mic_device_change"](None if v == "System default" else int(v.split(":")[0])),
            width=26), description="Restart the app for a new microphone to take effect.")

    # -- Audio ------------------------------------------------------------
    def _build_audio_section(self):
        theme = self.theme
        frame = self._new_section("audio")
        self._section_title(frame, "Audio & Tones", "Sounds played when listening starts, stops, or times out.")

        self.tone_var = None
        def build_tone_control(p):
            self.tone_var = self._combo(p, list(TONE_THEMES.keys()), self.settings["tone_theme"],
                                         self.cb["on_tone_change"], width=18)
        self._row_card(frame, "Sound Theme", build_tone_control,
                        description=f"{len(TONE_THEMES)} themes across sine, square, triangle, sawtooth, and noise waveforms.")

        # Volume slider — applies immediately and independently of the
        # Advanced-section batch sliders, since it's tied to its own
        # dedicated callback rather than the bundled parameter set.
        volume_card = Card(frame, theme)
        volume_card.pack(fill="x", pady=(0, Theme.SPACE_SM))
        vol_top = tk.Frame(volume_card.body, bg=theme.bg_elevated)
        vol_top.pack(fill="x")
        tk.Label(vol_top, text="Volume", bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(side="left")
        self.tone_volume_var = tk.DoubleVar(value=self.settings.get("tone_volume", DEFAULT_TONE_VOLUME))
        vol_value_label = tk.Label(vol_top, text=f"{int(round(self.tone_volume_var.get() * 100))}%",
                                    bg=theme.bg_elevated, fg=theme.accent, font=theme.font_body_bold())
        vol_value_label.pack(side="right")
        vol_scale = ttk.Scale(volume_card.body, from_=0.0, to=1.0, variable=self.tone_volume_var, orient="horizontal")
        vol_scale.pack(fill="x", pady=(Theme.SPACE_XS, 0))

        def _on_volume_move(_evt=None):
            vol_value_label.config(text=f"{int(round(self.tone_volume_var.get() * 100))}%")
        def _on_volume_release(_evt=None):
            _on_volume_move()
            self.cb["on_tone_volume_change"](round(self.tone_volume_var.get(), 2))
        vol_scale.bind("<Motion>", _on_volume_move)
        vol_scale.bind("<ButtonRelease-1>", _on_volume_release)

        preview_card = Card(frame, theme)
        preview_card.pack(fill="x", pady=(0, Theme.SPACE_SM))
        inner = tk.Frame(preview_card.body, bg=theme.bg_elevated)
        inner.pack(fill="x")
        prev_left = tk.Frame(inner, bg=theme.bg_elevated)
        prev_left.pack(side="left", fill="x", expand=True)
        tk.Label(prev_left, text="Preview the activation sound", bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(fill="x")
        tk.Label(prev_left, text="Plays the selected theme at the current volume.", bg=theme.bg_elevated,
                 fg=theme.fg_muted, font=theme.font_small(), anchor="w").pack(fill="x")
        PillButton(inner, theme, "\u25b6 Preview", kind="primary", command=self._preview_tone, width=110).pack(side="right")

    # -- Advanced ---------------------------------------------------------
    def _build_advanced_section(self):
        frame = self._new_section("advanced")
        self._section_title(frame, "Advanced Parameters", "Fine-tune detection sensitivity and timing.")

        self.wake_thresh_var = tk.DoubleVar(value=self.settings["wake_threshold"])
        self._build_slider(frame, "Wake Sensitivity", "0.1 (sensitive) \u2014 0.9 (strict)",
                            self.wake_thresh_var, 0.1, 0.9, 0.05)

        self.silence_timeout_var = tk.DoubleVar(value=self.settings["silence_timeout_sec"])
        self._build_slider(frame, "Silence Timeout", "2.0 \u2014 15.0 seconds",
                            self.silence_timeout_var, 2.0, 15.0, 0.5)

        self.mic_thresh_var = tk.DoubleVar(value=self.settings["silence_amplitude_threshold"])
        self._build_slider(frame, "Mic Amplitude Threshold", "100 \u2014 1000",
                            self.mic_thresh_var, 100, 1000, 50)

        self.max_history_var = tk.DoubleVar(value=self.settings.get("max_history_entries", MAX_HISTORY_ENTRIES_DEFAULT))
        self._build_slider(frame, "Max History Entries", "20 \u2014 1000",
                            self.max_history_var, 20, 1000, 10, is_int=True)

        self._build_hotkey_row(frame)

    def _build_slider(self, parent, label_text, range_text, var, from_, to, resolution, is_int=False):
        theme = self.theme
        card = tk.Frame(parent, bg=theme.bg_elevated, highlightbackground=theme.border, highlightthickness=1)
        card.pack(fill="x", pady=(0, Theme.SPACE_SM))
        inner = tk.Frame(card, bg=theme.bg_elevated)
        inner.pack(fill="x", padx=Theme.SPACE_MD, pady=Theme.SPACE_SM)

        top_row = tk.Frame(inner, bg=theme.bg_elevated)
        top_row.pack(fill="x")
        tk.Label(top_row, text=label_text, bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(side="left")

        value_fmt = (lambda v: str(int(round(v)))) if is_int else (lambda v: f"{v:.2f}")
        value_label = tk.Label(top_row, text=value_fmt(var.get()), bg=theme.bg_elevated, fg=theme.accent,
                                font=theme.font_body_bold())
        value_label.pack(side="right")

        tk.Label(inner, text=range_text, bg=theme.bg_elevated, fg=theme.fg_faint,
                 font=theme.font_small(), anchor="w").pack(fill="x")

        scale = ttk.Scale(inner, from_=from_, to=to, variable=var, orient="horizontal")
        scale.pack(fill="x", pady=(Theme.SPACE_XS, 0))

        def _on_move(_evt=None):
            value_label.config(text=value_fmt(var.get()))
        scale.bind("<Motion>", _on_move)
        scale.bind("<ButtonRelease-1>", lambda e: (_on_move(), self._on_param_change()))

    def _build_hotkey_row(self, parent):
        theme = self.theme
        card = tk.Frame(parent, bg=theme.bg_elevated, highlightbackground=theme.border, highlightthickness=1)
        card.pack(fill="x", pady=(0, Theme.SPACE_SM))
        inner = tk.Frame(card, bg=theme.bg_elevated)
        inner.pack(fill="x", padx=Theme.SPACE_MD, pady=Theme.SPACE_SM)

        self.hotkey_var = tk.StringVar(value=self.settings["hotkey_combo"])
        self.hotkey_record_btn = self._build_single_hotkey_control(
            inner, "Activation Hotkey", self.hotkey_var, "hotkey_var", top_pad=False)

        divider = tk.Frame(inner, bg=theme.border, height=1)
        divider.pack(fill="x", pady=Theme.SPACE_SM)

        self.reveal_hotkey_var = tk.StringVar(value=self.settings.get("reveal_hotkey_combo", REVEAL_HOTKEY_COMBO_DEFAULT))
        self.reveal_hotkey_record_btn = self._build_single_hotkey_control(
            inner, "Reveal Window Hotkey (works even in Hidden mode)", self.reveal_hotkey_var,
            "reveal_hotkey_var", top_pad=True)

    def _build_single_hotkey_control(self, parent, label_text, string_var, var_attr_name, top_pad):
        theme = self.theme
        tk.Label(parent, text=label_text, bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(fill="x", pady=(Theme.SPACE_SM if top_pad else 0, 0))

        row = tk.Frame(parent, bg=theme.bg_elevated)
        row.pack(fill="x", pady=(Theme.SPACE_XS, 0))

        entry = tk.Entry(row, textvariable=string_var, state="readonly", font=theme.font_mono(10),
                          bg=theme.bg_elevated_2, fg=theme.fg, relief="flat",
                          readonlybackground=theme.bg_elevated_2, justify="center")
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, Theme.SPACE_SM))

        record_btn = PillButton(row, theme, "Record", kind="secondary",
                                 command=lambda: self._start_recording_hotkey(var_attr_name), width=100)
        record_btn.pack(side="right")
        return record_btn

    def _active_record_button(self):
        return {"hotkey_var": self.hotkey_record_btn,
                "reveal_hotkey_var": self.reveal_hotkey_record_btn}.get(self._recording_var_name)

    # -- Voice Apps (new section) -------------------------------------------
    def _build_apps_section(self):
        theme = self.theme
        frame = self._new_section("apps")
        self._section_title(
            frame, "Voice-Launchable Apps",
            f"Say \u201copen <app name>\u201d to launch any of these {len(APPS)} apps. "
            "Grouped by category; the app must already be installed on this machine.")

        for cat_key, cat_label, cat_icon in CATEGORIES:
            app_ids = [aid for aid, cat in APP_CATEGORIES.items() if cat == cat_key]
            if not app_ids:
                continue
            tk.Label(frame, text=f"{cat_icon}  {cat_label}", bg=theme.bg, fg=theme.fg_muted,
                     font=theme.font_small_bold(), anchor="w").pack(fill="x", pady=(Theme.SPACE_SM, 4))

            chip_wrap = tk.Frame(frame, bg=theme.bg)
            chip_wrap.pack(fill="x", pady=(0, Theme.SPACE_SM))
            row = tk.Frame(chip_wrap, bg=theme.bg)
            row.pack(fill="x")
            col_count = 0
            max_cols = 3
            current_row = row
            for aid in sorted(app_ids, key=lambda a: APP_LABELS[a]):
                if col_count == max_cols:
                    current_row = tk.Frame(chip_wrap, bg=theme.bg)
                    current_row.pack(fill="x", pady=(4, 0))
                    col_count = 0
                chip = tk.Frame(current_row, bg=theme.bg_elevated_2, highlightbackground=theme.border,
                                 highlightthickness=1)
                chip.pack(side="left", padx=(0, 6))
                icon = app_icon(aid)
                tk.Label(chip, text=f"{icon}  {APP_LABELS[aid]}", bg=theme.bg_elevated_2, fg=theme.fg,
                         font=theme.font_small(), padx=8, pady=4).pack()
                col_count += 1

    # -- Actions ----------------------------------------------------------
    def _build_actions_section(self):
        theme = self.theme
        frame = self._new_section("actions")
        self._section_title(frame, "Actions", None)

        card = tk.Frame(frame, bg=theme.bg_elevated, highlightbackground=theme.border, highlightthickness=1)
        card.pack(fill="x", pady=(0, Theme.SPACE_MD))
        inner = tk.Frame(card, bg=theme.bg_elevated)
        inner.pack(fill="x", padx=Theme.SPACE_MD, pady=Theme.SPACE_MD)
        tk.Label(inner, text="Search History", bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(side="left")
        PillButton(inner, theme, "View History", kind="secondary",
                   command=self.cb["on_open_history"], width=140).pack(side="right")

        danger_card = tk.Frame(frame, bg=theme.bg_elevated, highlightbackground=theme.danger, highlightthickness=1)
        danger_card.pack(fill="x")
        inner2 = tk.Frame(danger_card, bg=theme.bg_elevated)
        inner2.pack(fill="x", padx=Theme.SPACE_MD, pady=Theme.SPACE_MD)
        tk.Label(inner2, text="Quit Program", bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(side="left")
        PillButton(inner2, theme, "Quit", kind="danger", command=self.cb["on_quit"], width=100).pack(side="right")

    # -- shared handlers ----------------------------------------------------
    def _on_param_change(self):
        self.cb["on_parameters_change"]({
            "wake_threshold": round(self.wake_thresh_var.get(), 2),
            "silence_timeout_sec": round(self.silence_timeout_var.get(), 1),
            "silence_amplitude_threshold": int(self.mic_thresh_var.get()),
            "hotkey_combo": self.hotkey_var.get(),
            "reveal_hotkey_combo": self.reveal_hotkey_var.get(),
            "max_history_entries": int(self.max_history_var.get()),
        })

    def _start_recording_hotkey(self, var_attr_name="hotkey_var"):
        # BUGFIX (from the original script): the old version bound <KeyPress>
        # globally on the settings window and never unbound it if the user
        # pressed only a modifier key or clicked away, leaving a permanent
        # dangling key-capture. We now bind narrowly, always clean up via
        # <Escape> and <FocusOut>, and never leave the window in "recording"
        # state if the user abandons the action.
        self._recording_var_name = var_attr_name
        btn = self._active_record_button()
        if btn is not None:
            btn.set_text("Press keys\u2026")
            btn.set_enabled(False)
        self._active_key_recorder_widget = self.top
        self.top.bind("<KeyPress>", self._on_key_press_record)
        self.top.bind("<Escape>", self._cancel_recording_hotkey, add="+")
        self.top.focus_force()

    def _cancel_recording_hotkey(self, event=None):
        if self._active_key_recorder_widget is None:
            return
        self.top.unbind("<KeyPress>")
        btn = self._active_record_button()
        if btn is not None:
            btn.set_text("Record")
            btn.set_enabled(True)
        self._active_key_recorder_widget = None
        self._recording_var_name = None

    def _on_key_press_record(self, event):
        key = event.keysym.lower()
        if key in ["shift_l", "shift_r", "control_l", "control_r", "alt_l", "alt_r",
                   "meta_l", "meta_r", "shift", "control", "alt", "meta", "mode_switch"]:
            return

        mods = []
        if event.state & 0x0004: mods.append("ctrl")
        if event.state & 0x0001: mods.append("shift")
        if event.state & 0x0008 or event.state & 0x20000: mods.append("alt")

        if key == "space": key = "space"
        elif key == "return": key = "return"
        elif key == "escape":
            self._cancel_recording_hotkey()
            return

        combo = "+".join(mods + [key])
        formatted_combo = f"<{combo}>"

        target_var_name = self._recording_var_name
        try:
            pynput_keyboard.HotKey.parse(formatted_combo)
            target_var = getattr(self, target_var_name)
            other_var_name = "reveal_hotkey_var" if target_var_name == "hotkey_var" else "hotkey_var"
            other_var = getattr(self, other_var_name)
            if formatted_combo == other_var.get():
                log(f"'{formatted_combo}' is already used by the other hotkey -- pick a different combination.")
                self._cancel_recording_hotkey()
                return
            target_var.set(formatted_combo)
            self._cancel_recording_hotkey()
            self._on_param_change()
        except Exception:
            log(f"Invalid key combination: '{formatted_combo}'. Please try a standard key (e.g., letters, numbers, space).")
            self._cancel_recording_hotkey()

    def _preview_tone(self):
        volume = self.tone_volume_var.get() if self.tone_volume_var is not None else DEFAULT_TONE_VOLUME
        activate, _, _ = build_tone_set(self.tone_var.get(), volume)
        if len(activate) == 0:
            return
        play_tone_async(self.pa, activate)


class AudioWorker(threading.Thread):
    def __init__(self, ui_queue, pa, wake_word=DEFAULT_WAKE_WORD, tone_theme=DEFAULT_TONE_THEME, settings=None):
        super().__init__(daemon=True)
        self.ui_queue = ui_queue
        self.pa = pa
        self.running = True

        self._state_lock = threading.Lock()
        self._model_lock = threading.Lock()

        self.is_active = False
        self.last_toggle_time = 0.0
        self.last_sound_time = 0.0
        self.recorded_frames = []
        self.session_start_ts = None
        self.frames_captured_this_session = 0

        self.wake_word = wake_word
        settings = settings or {}
        self.tone_volume = settings.get("tone_volume", DEFAULT_TONE_VOLUME)
        self._current_tone_theme = tone_theme
        self.activate_tone, self.deactivate_tone, self.timeout_tone = build_tone_set(tone_theme, self.tone_volume)

        self.wake_threshold = settings.get("wake_threshold", 0.5)
        self.silence_timeout_sec = settings.get("silence_timeout_sec", 8.0)
        self.silence_amplitude_threshold = settings.get("silence_amplitude_threshold", 300)
        self.speech_language = settings.get("speech_language", DEFAULT_SPEECH_LANGUAGE)
        self.mic_device_index = settings.get("mic_device_index")

        self.oww_model = None
        self._load_wake_word_model(wake_word)

        self.stream = self.pa.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True,
                                    frames_per_buffer=CHUNK, input_device_index=self.mic_device_index)
        self.recognizer = sr.Recognizer()

    def _load_wake_word_model(self, wake_word):
        log(f"Loading wake word model '{wake_word}'...")
        try:
            model_paths = openwakeword.get_pretrained_model_paths()
            model_keys = list(openwakeword.models.keys())
            if wake_word in model_keys:
                idx = model_keys.index(wake_word)
                new_model = WakeWordModel(wakeword_model_paths=[model_paths[idx]])
            else:
                raise ValueError("Model not found")
        except Exception as e:
            log(f"Failed to load wake word '{wake_word}' ({e}); falling back to default.")
            try:
                model_paths = openwakeword.get_pretrained_model_paths()
                model_keys = list(openwakeword.models.keys())
                idx = model_keys.index(DEFAULT_WAKE_WORD)
                new_model = WakeWordModel(wakeword_model_paths=[model_paths[idx]])
                wake_word = DEFAULT_WAKE_WORD
            except Exception:
                log("Critical: Could not load any wake word model.")
                return
        with self._model_lock:
            self.oww_model = new_model
            self.wake_word = wake_word
        log(f"Wake word model '{wake_word}' loaded.")

    def set_wake_word(self, wake_word):
        if wake_word == self.wake_word:
            return
        threading.Thread(target=self._load_wake_word_model, args=(wake_word,), daemon=True).start()

    def set_tone_theme(self, theme_name):
        self._current_tone_theme = theme_name
        self.activate_tone, self.deactivate_tone, self.timeout_tone = build_tone_set(theme_name, self.tone_volume)

    def set_tone_volume(self, volume):
        self.tone_volume = max(0.0, min(1.0, volume))
        self.activate_tone, self.deactivate_tone, self.timeout_tone = build_tone_set(
            self._current_tone_theme, self.tone_volume)

    def update_parameters(self, settings):
        with self._state_lock:
            self.wake_threshold = settings.get("wake_threshold", self.wake_threshold)
            self.silence_timeout_sec = settings.get("silence_timeout_sec", self.silence_timeout_sec)
            self.silence_amplitude_threshold = settings.get("silence_amplitude_threshold", self.silence_amplitude_threshold)
            self.speech_language = settings.get("speech_language", self.speech_language)

    def _activate(self, source):
        with self._state_lock:
            if self.is_active:
                return
            self.recorded_frames = []
            self.frames_captured_this_session = 0
            self.session_start_ts = time.time()
            self.last_sound_time = self.session_start_ts
            self.is_active = True
        log(f"ACTIVATE (via {source}) -- buffer cleared, capture starting.")
        play_tone_async(self.pa, self.activate_tone)
        self.ui_queue.put(("listening_started", None))

    def _deactivate(self, source, timed_out=False):
        # BUGFIX (from the original script): the post-deactivate invariant
        # check read self.is_active / self.recorded_frames *outside* the
        # state lock, right after releasing it -- a benign-looking but
        # technically unsafe read of shared state.
        #
        # BUGFIX (this pass): the previous fix for the above introduced a
        # new bug -- it captured buffer_snapshot = self.recorded_frames
        # *after* self.recorded_frames had already been reassigned to [],
        # so buffer_snapshot was always the fresh empty list and the check
        # `len(buffer_snapshot) != 0` could never fail regardless of what
        # actually happened. It verified nothing. Snapshots are now taken
        # in the correct order, all while still holding the lock.
        with self._state_lock:
            if not self.is_active:
                return
            is_active_snapshot = self.is_active   # True, about to be cleared below
            buffer_snapshot = self.recorded_frames  # reference to the pre-clear list
            self.is_active = False
            now = time.time()
            duration = now - self.session_start_ts if self.session_start_ts else 0.0
            frames = self.recorded_frames
            frame_count = self.frames_captured_this_session
            self.recorded_frames = []
            # Re-read is_active after clearing, for the actual post-state check.
            is_active_after = self.is_active

        reason = "SILENCE TIMEOUT" if timed_out else f"DEACTIVATE (via {source})"
        log(f"{reason} -- duration={duration:.2f}s frames={frame_count} bytes={sum(len(f) for f in frames)}")

        if is_active_after is not False:
            raise RuntimeError("AUDIO BOUNDARY VIOLATION: is_active still True after deactivate")
        if self.recorded_frames is buffer_snapshot:
            raise RuntimeError("AUDIO BOUNDARY VIOLATION: buffer not replaced after deactivate")
        log("Invariant check passed (capture off, buffer cleared).")

        if timed_out:
            play_tone_async(self.pa, self.timeout_tone)
            self.ui_queue.put(("timed_out", None))
            return

        if duration < 0.3:
            log(f"Session too short ({duration:.2f}s) -- discarded.")
            play_tone_async(self.pa, self.deactivate_tone)
            self.ui_queue.put(("listening_stopped", ""))
            return

        play_tone_async(self.pa, self.deactivate_tone)
        self.ui_queue.put(("transcribing", None))
        threading.Thread(target=self._transcribe_and_report, args=(frames,), daemon=True).start()

    def toggle_from_hotkey(self):
        # BUGFIX: this read self.is_active with no lock and then called
        # _activate/_deactivate based on possibly-stale state -- a narrow
        # race with a near-simultaneous wake-word toggle or timeout could
        # silently drop the hotkey press (both branches internally re-check
        # under the lock and no-op if already in that state, so the failure
        # mode was "nothing happens," not a crash, but the read should be
        # consistent with every other state check in this class).
        with self._state_lock:
            active = self.is_active
        if not active:
            self._activate(source="hotkey")
        else:
            self._deactivate(source="hotkey")

    def _toggle_from_wake_word(self):
        now = time.time()
        if now - self.last_toggle_time < 1.5:
            return
        self.last_toggle_time = now
        if not self.is_active:
            self._activate(source="wake word")
        else:
            self._deactivate(source="wake word")

    def _transcribe_and_report(self, frames):
        text = ""
        if not frames:
            self.ui_queue.put(("listening_stopped", text))
            return

        raw_audio = b"".join(frames)
        audio_data = sr.AudioData(raw_audio, RATE, SAMPLE_WIDTH_BYTES)

        try:
            text = self.recognizer.recognize_google(audio_data, language=self.speech_language)
            log(f"Transcription received: '{text}'")
            text = strip_trailing_wake_word(text, wake_word=self.wake_word)
        except sr.UnknownValueError:
            log("Google could not understand the audio.")
        except sr.RequestError as e:
            log(f"Speech recognition service error: {e}")

        self.ui_queue.put(("listening_stopped", text))

    def run(self):
        try:
            while self.running:
                raw = self.stream.read(CHUNK, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.int16)

                with self._model_lock:
                    model = self.oww_model

                if model is not None:
                    prediction = model.predict(samples)
                    if any(score > self.wake_threshold for score in prediction.values()):
                        self._toggle_from_wake_word()

                if self.is_active:
                    with self._state_lock:
                        if self.is_active:
                            self.recorded_frames.append(raw)
                            self.frames_captured_this_session += 1

                    level = rms_amplitude(samples)
                    self.ui_queue.put(("meter", level))
                    if level > self.silence_amplitude_threshold:
                        self.last_sound_time = time.time()
                    elif time.time() - self.last_sound_time > self.silence_timeout_sec:
                        self._deactivate(source="silence timeout", timed_out=True)
        finally:
            self.stream.stop_stream()
            self.stream.close()

    def stop(self):
        self.running = False


class App:
    POLL_MS = 100

    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()

        self.settings = load_settings()

        safe_hotkey = get_valid_hotkey(self.settings.get("hotkey_combo"), fallback=HOTKEY_COMBO_DEFAULT)
        if safe_hotkey != self.settings.get("hotkey_combo"):
            self.settings["hotkey_combo"] = safe_hotkey
            save_settings(self.settings)

        safe_reveal_hotkey = get_valid_hotkey(self.settings.get("reveal_hotkey_combo"),
                                               fallback=REVEAL_HOTKEY_COMBO_DEFAULT)
        if safe_reveal_hotkey != self.settings.get("reveal_hotkey_combo"):
            self.settings["reveal_hotkey_combo"] = safe_reveal_hotkey
            save_settings(self.settings)
        # Two combos can't be identical, or GlobalHotKeys silently drops one
        # of them -- if the user's saved settings ever collide (e.g. hand-
        # edited settings.json, or a future settings UI bug), fall back the
        # reveal hotkey to its default rather than registering a broken pair.
        if safe_reveal_hotkey == safe_hotkey:
            safe_reveal_hotkey = REVEAL_HOTKEY_COMBO_DEFAULT
            self.settings["reveal_hotkey_combo"] = safe_reveal_hotkey
            save_settings(self.settings)

        self.history = load_history(self.settings.get("max_history_entries", MAX_HISTORY_ENTRIES_DEFAULT))
        self.available_wake_words = available_wake_words()

        if self.settings["wake_word"] not in self.available_wake_words:
            self.settings["wake_word"] = self.available_wake_words[0]

        self.theme = get_theme(self.root, self.settings.get("ui_theme", DEFAULT_UI_THEME))
        style_ttk(self.root, self.theme)

        self.ui_queue = queue.Queue()
        self.pa = pyaudio.PyAudio()

        self.status_window = StatusWindow(
            self.root, on_quit=self.quit, on_settings=self.open_settings,
            wake_word=self.settings["wake_word"], size_name=self.settings["window_size"],
            theme=self.theme)
        self.status_window.set_hotkey_label(self.settings["hotkey_combo"])
        self.status_window.set_quit_callback(self.quit)

        self.worker = AudioWorker(
            self.ui_queue, self.pa,
            wake_word=self.settings["wake_word"],
            tone_theme=self.settings["tone_theme"],
            settings=self.settings
        )
        self.worker.start()

        self.hotkey_listener = pynput_keyboard.GlobalHotKeys({
            safe_hotkey: self.worker.toggle_from_hotkey,
            safe_reveal_hotkey: self.reveal_window,
        })
        self.hotkey_listener.start()
        log(f"Global hotkey active: {safe_hotkey} (toggle listening), {safe_reveal_hotkey} (reveal window)")

        self.settings_window = None
        self.history_window = None
        self.root.after(self.POLL_MS, self.poll_queue)

    def reveal_window(self):
        # Bring the status window back to a visible size regardless of
        # whether it's currently Hidden or just buried behind other windows
        # -- this is the escape hatch for Hidden mode, reachable even when
        # the window has no visible surface to click on.
        if self.status_window.size_name == "Hidden":
            self.change_window_size(DEFAULT_WINDOW_SIZE)
        self.status_window.top.deiconify()
        self.status_window.top.lift()
        self.status_window.top.attributes("-topmost", True)

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.top.winfo_exists():
            self.settings_window.top.lift()
            return
        callbacks = {
            "on_wake_word_change": self.change_wake_word,
            "on_size_change": self.change_window_size,
            "on_theme_change": self.change_ui_theme,
            "on_tone_change": self.change_tone_theme,
            "on_tone_volume_change": self.change_tone_volume,
            "on_destination_change": self.change_default_destination,
            "on_auto_search_change": self.change_auto_search,
            "on_clipboard_change": self.change_clipboard_auto_copy,
            "on_app_launch_change": self.change_app_launch_enabled,
            "on_language_change": self.change_speech_language,
            "on_mic_device_change": self.change_mic_device,
            "on_parameters_change": self.change_parameters,
            "on_open_history": self.open_history,
            "on_quit": self.quit,
        }
        self.settings_window = SettingsWindow(
            self.root, self.theme, self.pa, self.settings, self.available_wake_words, callbacks)

    def open_history(self):
        if self.history_window is not None and self.history_window.top.winfo_exists():
            self.history_window.top.lift()
            return
        self.history_window = HistoryWindow(
            self.root, self.theme, self.history,
            on_rerun=lambda dest, query: open_search(dest, query),
            on_save=self.save_history_now
        )

    def save_history_now(self):
        save_history(self.history)

    def change_wake_word(self, wake_word):
        self.settings["wake_word"] = wake_word
        save_settings(self.settings)
        self.worker.set_wake_word(wake_word)
        self.status_window.set_wake_word(wake_word)

    def change_window_size(self, size_name):
        self.settings["window_size"] = size_name
        save_settings(self.settings)
        self.status_window.apply_size(size_name)

    def change_ui_theme(self, theme_name):
        # BUGFIX (from the original script): previously only the status bar
        # re-themed live; the confirm popup, history table, settings window,
        # and toasts were stuck rendering with default Tk colors regardless
        # of the chosen theme until restart. Now the resolved Theme object
        # is refreshed and reused by every window created from this point
        # on, and the already-open status bar is repainted immediately.
        self.settings["ui_theme"] = theme_name
        save_settings(self.settings)
        self.theme = get_theme(self.root, theme_name)
        style_ttk(self.root, self.theme)
        self.status_window.apply_theme(self.theme)
        if self.settings_window is not None and self.settings_window.top.winfo_exists():
            self.settings_window.top.destroy()
            self.open_settings()
        if self.history_window is not None and self.history_window.top.winfo_exists():
            self.history_window.top.destroy()
            self.open_history()

    def change_tone_theme(self, theme_name):
        self.settings["tone_theme"] = theme_name
        save_settings(self.settings)
        self.worker.set_tone_theme(theme_name)

    def change_tone_volume(self, volume):
        self.settings["tone_volume"] = float(volume)
        save_settings(self.settings)
        self.worker.set_tone_volume(float(volume))

    def change_default_destination(self, destination):
        self.settings["default_destination"] = destination
        save_settings(self.settings)

    def change_auto_search(self, value):
        self.settings["auto_search"] = bool(value)
        save_settings(self.settings)

    def change_clipboard_auto_copy(self, value):
        self.settings["clipboard_auto_copy"] = bool(value)
        save_settings(self.settings)

    def change_app_launch_enabled(self, value):
        self.settings["app_launch_enabled"] = bool(value)
        save_settings(self.settings)

    def change_speech_language(self, lang_code):
        self.settings["speech_language"] = lang_code
        save_settings(self.settings)
        self.worker.update_parameters(self.settings)

    def change_mic_device(self, device_index):
        self.settings["mic_device_index"] = device_index
        save_settings(self.settings)
        log("Microphone selection saved. Restart the app for it to take effect.")

    def change_parameters(self, params):
        for key, val in params.items():
            self.settings[key] = val

        # Validate both hotkeys and guard against collisions here too --
        # this is the only other place combos can change (the Settings UI),
        # so it needs the same safety checks as the startup path.
        safe_hotkey = get_valid_hotkey(self.settings.get("hotkey_combo"), fallback=HOTKEY_COMBO_DEFAULT)
        safe_reveal_hotkey = get_valid_hotkey(self.settings.get("reveal_hotkey_combo"),
                                               fallback=REVEAL_HOTKEY_COMBO_DEFAULT)
        if safe_reveal_hotkey == safe_hotkey:
            safe_reveal_hotkey = REVEAL_HOTKEY_COMBO_DEFAULT
        self.settings["hotkey_combo"] = safe_hotkey
        self.settings["reveal_hotkey_combo"] = safe_reveal_hotkey

        save_settings(self.settings)
        self.worker.update_parameters(self.settings)
        self.status_window.set_hotkey_label(self.settings["hotkey_combo"])

        new_max = self.settings.get("max_history_entries", MAX_HISTORY_ENTRIES_DEFAULT)
        if new_max != self.history.maxlen:
            self.history = collections.deque(self.history, maxlen=new_max)

        self.hotkey_listener.stop()
        self.hotkey_listener = pynput_keyboard.GlobalHotKeys({
            safe_hotkey: self.worker.toggle_from_hotkey,
            safe_reveal_hotkey: self.reveal_window,
        })
        self.hotkey_listener.start()
        log(f"Hotkeys updated: {safe_hotkey} (toggle listening), {safe_reveal_hotkey} (reveal window)")

    def add_to_history(self, destination, transcribed, final_query):
        entry = {
            "datetime": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "destination": destination,
            "transcribed": transcribed,
            "query": final_query
        }
        self.history.append(entry)
        save_history(self.history)

    def _handle_transcript(self, payload):
        if self.settings.get("clipboard_auto_copy"):
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(payload)
                self.root.update()
            except Exception as e:
                log(f"Clipboard copy failed: {e}")

        if is_open_settings_command(payload):
            self.open_settings()
            ToastWindow(self.root, self.theme, "Opening settings", kind="success", icon="\u2699")
            return

        if self.settings.get("app_launch_enabled", True):
            app_id = parse_app_command(payload)
            if app_id:
                ok, label = launch_app(app_id)
                icon = app_icon(app_id) if ok else "\u26a0"
                ToastWindow(self.root, self.theme,
                            f"Launched {label}" if ok else f"{label} not found on this system",
                            kind="success" if ok else "danger", icon=icon)
                return

        if self.settings.get("auto_search"):
            destination, query = parse_destination(payload, self.settings["default_destination"])
            query = apply_math_substitutions(query)
            open_search(destination, query)
            self.add_to_history(destination, payload, query)
            ToastWindow(self.root, self.theme, f"Searched \u201c{query}\u201d on {destination}", kind="success")
            return

        ConfirmWindow(
            self.root, self.theme, payload,
            default_destination=self.settings["default_destination"],
            on_search_callback=self.add_to_history
        )

    def poll_queue(self):
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "listening_started":
                    self.status_window.set_listening()
                elif kind == "meter":
                    self.status_window.set_meter(payload)
                elif kind == "transcribing":
                    self.status_window.set_transcribing()
                elif kind == "timed_out":
                    self.status_window.set_timed_out()
                    self.root.after(2000, self.status_window.set_idle)
                elif kind == "listening_stopped":
                    self.status_window.set_idle()
                    if payload:
                        self._handle_transcript(payload)
        except queue.Empty:
            pass
        self.root.after(self.POLL_MS, self.poll_queue)

    def quit(self):
        log("Quit requested.")
        self.worker.stop()
        self.hotkey_listener.stop()
        self.root.after(150, self._finish_quit)

    def _finish_quit(self):
        try:
            self.pa.terminate()
        except Exception as e:
            log(f"Error during shutdown: {e}")
        self.root.destroy()

    def run(self):
        label = WAKE_WORD_LABELS.get(self.settings["wake_word"], self.settings["wake_word"])
        log(f"Listening for '{label}' or {self.settings['hotkey_combo']}. Quit button or Ctrl+C to exit.")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()


if __name__ == "__main__":
    App().run()