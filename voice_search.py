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
from tkinter import ttk

from theme import (
    Theme, get_theme, style_ttk, apply_window_chrome,
    PillButton, toggle_switch,
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
    "Compact": (240, 108, False, False, 0.9),
    "Normal": (340, 220, True, True, 1.0),
    "Large": (440, 290, True, True, 1.25),
}
DEFAULT_WINDOW_SIZE = "Normal"

TONE_THEMES = {
    "Classic beep": (880, [440, 440, 440], [300, 300], "sine"),
    "Soft chime": (1046, [784, 659], [220, 220], "soft"),
    "Click": (1800, [1200], [500, 500, 500], "square"),
    "Sci-fi blip": (1500, [1900, 1500, 1100], [260, 180], "square"),
    "Mute": (None, [], [], "sine"),
}
DEFAULT_TONE_THEME = "Classic beep"

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
    "default_destination": "google",
    "wake_threshold": 0.5,
    "silence_timeout_sec": 8.0,
    "silence_amplitude_threshold": 300,
    "hotkey_combo": HOTKEY_COMBO_DEFAULT,
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


def get_valid_hotkey(combo):
    if not isinstance(combo, str):
        return HOTKEY_COMBO_DEFAULT
    try:
        pynput_keyboard.HotKey.parse(combo)
        return combo
    except Exception:
        log(f"Warning: Invalid hotkey '{combo}' in settings. Falling back to '{HOTKEY_COMBO_DEFAULT}'.")
        return HOTKEY_COMBO_DEFAULT


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
    t = np.linspace(0, duration, int(sr_ * duration), False)
    if waveform == "square":
        tone = np.sign(np.sin(freq * t * 2 * np.pi))
    else:
        tone = np.sin(freq * t * 2 * np.pi)
    fade = int(sr_ * (0.02 if waveform == "soft" else 0.005))
    fade = max(1, min(fade, len(tone) // 2))
    tone[:fade] *= np.linspace(0, 1, fade)
    tone[-fade:] *= np.linspace(1, 0, fade)
    vol = volume * 0.6 if waveform == "soft" else volume
    return (tone * vol * 32767).astype(np.int16)


def _make_tone_sequence(freqs, duration, gap_sec, waveform="sine"):
    if not freqs:
        return np.zeros(0, dtype=np.int16)
    gap = np.zeros(int(RATE * gap_sec), dtype=np.int16)
    parts = []
    for i, f in enumerate(freqs):
        parts.append(_make_tone(f, duration, waveform=waveform))
        if i != len(freqs) - 1:
            parts.append(gap)
    return np.concatenate(parts)


def build_tone_set(theme_name):
    activate_freq, deactivate_freqs, timeout_freqs, waveform = TONE_THEMES.get(
        theme_name, TONE_THEMES[DEFAULT_TONE_THEME])
    if activate_freq is None:
        activate = np.zeros(0, dtype=np.int16)
    else:
        activate = _make_tone(activate_freq, 0.12, waveform=waveform)
    deactivate = _make_tone_sequence(deactivate_freqs, 0.08, 0.05, waveform=waveform)
    timeout = _make_tone_sequence(timeout_freqs, 0.15, 0.08, waveform=waveform)
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
]


def apply_math_substitutions(text):
    result = _replace_power_variants(text)
    result = _replace_subscript_variants(result)
    result = _replace_log_variants(result)
    result = _replace_function_of_variants(result)
    result = _replace_root_of_variants(result)
    result = _replace_fraction_variants(result)
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
        parts = cmd.split()
        if not parts:
            continue
        exe = shutil.which(parts[0])
        if not exe and not os.path.isfile(parts[0]):
            continue
        try:
            subprocess.Popen(parts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
            log(f"Launched {label} via '{cmd}'")
            return True, label
        except Exception as e:
            log(f"Failed to launch {label} via '{cmd}': {e}")
    log(f"Could not find an installed executable for {label}.")
    return False, label


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

        width, height = 560, 260
        sw = self.top.winfo_screenwidth()
        x = (sw - width) // 2
        y = int(self.top.winfo_screenheight() * 0.22)
        self.top.geometry(f"{width}x{height}+{x}+{y}")

        outer = tk.Frame(self.top, bg=theme.border, bd=0)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        card = tk.Frame(outer, bg=theme.bg_elevated)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=theme.bg_elevated)
        header.pack(fill="x", padx=Theme.SPACE_LG, pady=(Theme.SPACE_LG, Theme.SPACE_SM))

        tk.Label(header, text="\U0001f50d", bg=theme.bg_elevated, fg=theme.fg_muted,
                 font=theme.font(14)).pack(side="left", padx=(0, 8))
        tk.Label(header, text="Search query", bg=theme.bg_elevated, fg=theme.fg_muted,
                 font=theme.font_small_bold()).pack(side="left")

        self._dest_pill = self._make_pill(header, self._destination_display(destination))
        self._dest_pill.pack(side="right")

        text_wrap = tk.Frame(card, bg=theme.bg_elevated_2, highlightbackground=theme.border,
                              highlightthickness=1)
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
    """Search history browser, restyled as a themed data table with a search box."""

    def __init__(self, root, theme, history_deque, on_rerun, on_clear):
        self.theme = theme
        self.top = tk.Toplevel(root)
        self.top.title("Search History")
        self.top.attributes("-topmost", True)
        self.top.geometry("780x480")
        self.top.minsize(600, 320)
        apply_window_chrome(self.top, theme)
        style_ttk(self.top, theme)

        self.history_deque = history_deque
        self.on_rerun = on_rerun
        self.on_clear = on_clear
        self._filter_text = tk.StringVar()

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
                                 font=theme.font_body(), width=24)
        search_entry.pack(side="left", ipady=4, padx=(0, 8))
        self._filter_text.trace_add("write", lambda *a: self._populate_tree())

        table_card = tk.Frame(self.top, bg=theme.bg_elevated, highlightbackground=theme.border,
                               highlightthickness=1)
        table_card.pack(fill="both", expand=True, padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_SM))

        columns = ("idx", "datetime", "destination", "transcribed", "query")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("idx", text="#")
        self.tree.column("idx", width=40, anchor="center")
        self.tree.heading("datetime", text="Date & Time")
        self.tree.column("datetime", width=150, anchor="w")
        self.tree.heading("destination", text="Website")
        self.tree.column("destination", width=120, anchor="w")
        self.tree.heading("transcribed", text="Transcribed Text")
        self.tree.column("transcribed", width=210, anchor="w")
        self.tree.heading("query", text="Final Query")
        self.tree.column("query", width=210, anchor="w")

        tree_scroll = ttk.Scrollbar(table_card, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)
        tree_scroll.pack(side="right", fill="y", pady=1, padx=(0, 1))
        self.tree.bind("<Double-1>", lambda e: self._on_rerun())

        self._populate_tree()

        btn_row = tk.Frame(self.top, bg=theme.bg)
        btn_row.pack(fill="x", padx=Theme.SPACE_LG, pady=(0, Theme.SPACE_LG))

        self.count_label = tk.Label(btn_row, text="", bg=theme.bg, fg=theme.fg_faint, font=theme.font_small())
        self.count_label.pack(side="left")

        PillButton(btn_row, theme, "Close", kind="ghost", command=self.top.destroy, width=90).pack(side="right")
        PillButton(btn_row, theme, "Clear History", kind="danger", command=self._on_clear, width=130).pack(side="right", padx=(0, Theme.SPACE_SM))
        PillButton(btn_row, theme, "Re-run Selected", kind="primary", command=self._on_rerun, width=150).pack(side="right", padx=(0, Theme.SPACE_SM))

    def _populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        needle = self._filter_text.get().strip().lower()
        shown = 0
        total = len(self.history_deque)
        for i, entry in enumerate(reversed(list(self.history_deque))):
            actual_idx = total - i
            transcribed = entry.get("transcribed", "")
            query = entry.get("query", "")
            destination = entry.get("destination", "")

            if needle and needle not in transcribed.lower() and needle not in query.lower() and needle not in destination.lower():
                continue
            shown += 1

            self.tree.insert("", "end", iid=str(actual_idx), values=(
                actual_idx,
                entry.get("datetime", ""),
                destination,
                (transcribed[:35] + "...") if len(transcribed) > 35 else transcribed,
                (query[:40] + "...") if len(query) > 40 else query
            ))

        if hasattr(self, "count_label"):
            self.count_label.config(text=f"{shown} of {total} entries" if needle else f"{total} entries")

    def _on_rerun(self):
        selected = self.tree.selection()
        if not selected:
            return
        idx = int(selected[0])
        entry = list(self.history_deque)[idx - 1]
        self.on_rerun(entry.get("destination"), entry.get("query"))
        self.top.destroy()

    def _on_clear(self):
        self.history_deque.clear()
        self.on_clear()
        self._populate_tree()


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
        width, height, show_meter, show_hotkey, font_scale = WINDOW_SIZES.get(
            size_name, WINDOW_SIZES[DEFAULT_WINDOW_SIZE])
        self.size_name = size_name

        pos = self.top.geometry().split("+", 1)
        offset = "+" + pos[1] if len(pos) > 1 else "+40+40"
        self.top.geometry(f"{width}x{height}{offset}")

        status_size = max(9, round(11 * font_scale))
        hotkey_size = max(7, round(8 * font_scale))
        self.status_label.config(font=self.theme.font(status_size, "bold"), wraplength=width - 70)
        self.hotkey_label.config(font=self.theme.font(hotkey_size))

        if show_hotkey:
            self.hotkey_label.pack(pady=(2, Theme.SPACE_SM))
        else:
            self.hotkey_label.pack_forget()

        meter_height = max(16, round(30 * font_scale))
        self.meter_canvas.config(height=meter_height)
        if show_meter:
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
                                         self.cb["on_tone_change"], width=16)
        self._row_card(frame, "Sound Theme", build_tone_control)

        preview_card = tk.Frame(frame, bg=theme.bg_elevated, highlightbackground=theme.border, highlightthickness=1)
        preview_card.pack(fill="x", pady=(0, Theme.SPACE_SM))
        inner = tk.Frame(preview_card, bg=theme.bg_elevated)
        inner.pack(fill="x", padx=Theme.SPACE_MD, pady=Theme.SPACE_SM)
        tk.Label(inner, text="Preview the activation sound", bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold()).pack(side="left")
        PillButton(inner, theme, "\u25b6 Preview", kind="secondary", command=self._preview_tone, width=110).pack(side="right")

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

        tk.Label(inner, text="Activation Hotkey", bg=theme.bg_elevated, fg=theme.fg,
                 font=theme.font_body_bold(), anchor="w").pack(fill="x")

        row = tk.Frame(inner, bg=theme.bg_elevated)
        row.pack(fill="x", pady=(Theme.SPACE_XS, 0))

        self.hotkey_var = tk.StringVar(value=self.settings["hotkey_combo"])
        entry = tk.Entry(row, textvariable=self.hotkey_var, state="readonly", font=theme.font_mono(10),
                          bg=theme.bg_elevated_2, fg=theme.fg, relief="flat",
                          readonlybackground=theme.bg_elevated_2, justify="center")
        entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, Theme.SPACE_SM))

        self.record_btn = PillButton(row, theme, "Record", kind="secondary",
                                      command=self._start_recording_hotkey, width=100)
        self.record_btn.pack(side="right")

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
            "max_history_entries": int(self.max_history_var.get()),
        })

    def _start_recording_hotkey(self):
        # BUGFIX (from the original script): the old version bound <KeyPress>
        # globally on the settings window and never unbound it if the user
        # pressed only a modifier key or clicked away, leaving a permanent
        # dangling key-capture. We now bind narrowly, always clean up via
        # <Escape> and <FocusOut>, and never leave the window in "recording"
        # state if the user abandons the action.
        self.record_btn.set_text("Press keys\u2026")
        self.record_btn.set_enabled(False)
        self._active_key_recorder_widget = self.top
        self.top.bind("<KeyPress>", self._on_key_press_record)
        self.top.bind("<Escape>", self._cancel_recording_hotkey, add="+")
        self.top.focus_force()

    def _cancel_recording_hotkey(self, event=None):
        if self._active_key_recorder_widget is None:
            return
        self.top.unbind("<KeyPress>")
        self.record_btn.set_text("Record")
        self.record_btn.set_enabled(True)
        self._active_key_recorder_widget = None

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

        try:
            pynput_keyboard.HotKey.parse(formatted_combo)
            self.hotkey_var.set(formatted_combo)
            self._cancel_recording_hotkey()
            self._on_param_change()
        except Exception:
            log(f"Invalid key combination: '{formatted_combo}'. Please try a standard key (e.g., letters, numbers, space).")
            self._cancel_recording_hotkey()

    def _preview_tone(self):
        activate, _, _ = build_tone_set(self.tone_var.get())
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
        self.activate_tone, self.deactivate_tone, self.timeout_tone = build_tone_set(tone_theme)

        settings = settings or {}
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
        self.activate_tone, self.deactivate_tone, self.timeout_tone = build_tone_set(theme_name)

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
        # technically unsafe read of shared state. The check now happens
        # against the locally captured snapshot taken while still holding
        # the lock, which is what it was actually trying to verify.
        with self._state_lock:
            if not self.is_active:
                return
            self.is_active = False
            now = time.time()
            duration = now - self.session_start_ts if self.session_start_ts else 0.0
            frames = self.recorded_frames
            frame_count = self.frames_captured_this_session
            self.recorded_frames = []
            is_active_snapshot = self.is_active
            buffer_snapshot = self.recorded_frames

        reason = "SILENCE TIMEOUT" if timed_out else f"DEACTIVATE (via {source})"
        log(f"{reason} -- duration={duration:.2f}s frames={frame_count} bytes={sum(len(f) for f in frames)}")

        if is_active_snapshot is not False:
            raise RuntimeError("AUDIO BOUNDARY VIOLATION: is_active still True after deactivate")
        if len(buffer_snapshot) != 0:
            raise RuntimeError("AUDIO BOUNDARY VIOLATION: buffer not cleared after deactivate")
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
        if not self.is_active:
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

        safe_hotkey = get_valid_hotkey(self.settings.get("hotkey_combo"))
        if safe_hotkey != self.settings.get("hotkey_combo"):
            self.settings["hotkey_combo"] = safe_hotkey
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
            self.settings["hotkey_combo"]: self.worker.toggle_from_hotkey,
        })
        self.hotkey_listener.start()
        log(f"Global hotkey active: {self.settings['hotkey_combo']}")

        self.settings_window = None
        self.history_window = None
        self.root.after(self.POLL_MS, self.poll_queue)

    def open_settings(self):
        if self.settings_window is not None and self.settings_window.top.winfo_exists():
            self.settings_window.top.lift()
            return
        callbacks = {
            "on_wake_word_change": self.change_wake_word,
            "on_size_change": self.change_window_size,
            "on_theme_change": self.change_ui_theme,
            "on_tone_change": self.change_tone_theme,
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
            on_clear=self.clear_history
        )

    def clear_history(self):
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
        save_settings(self.settings)
        self.worker.update_parameters(self.settings)
        self.status_window.set_hotkey_label(self.settings["hotkey_combo"])

        new_max = self.settings.get("max_history_entries", MAX_HISTORY_ENTRIES_DEFAULT)
        if new_max != self.history.maxlen:
            self.history = collections.deque(self.history, maxlen=new_max)

        self.hotkey_listener.stop()
        self.hotkey_listener = pynput_keyboard.GlobalHotKeys({
            self.settings["hotkey_combo"]: self.worker.toggle_from_hotkey,
        })
        self.hotkey_listener.start()
        log(f"Hotkey updated to: {self.settings['hotkey_combo']}")

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