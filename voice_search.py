"""
Voice-to-search launcher.

Activate/deactivate by saying "Alexa" OR pressing a global hotkey
(default Ctrl+Shift+`). Speak a query (optionally prefixed with a
destination keyword, default Google), review/edit the transcript in a
popup, click Go to search.

AUDIO BOUNDARY GUARANTEE: only audio captured between an ACTIVATE and the
following DEACTIVATE (spoken, hotkey, or silence-timeout) is ever buffered
or transcribed. `recorded_frames.append()` occurs in exactly one place
(AudioWorker.run, gated on is_active). Buffer is cleared before is_active
is set True on activate; is_active is set False before the buffer
reference is handed to the transcription thread on deactivate, so the
capture loop cannot append to a buffer already in flight. An explicit
runtime check (NOT a bare `assert`, which Python strips under `python -O`)
verifies both after every deactivate and raises if violated. Every
capture/hand-off/send is logged with a timestamp.

Two independent triggers (wake word and global hotkey) can call
activate/deactivate concurrently -- a lock serializes them so a race
between the two can't corrupt the recording buffer or the active flag.

Pipeline: openWakeWord (local, wake word) + pynput (local, hotkey) ->
speech_recognition/Google Web Speech (cloud, transcription only) -> Tkinter GUI.
"""

import time
import threading
import queue
import re
import webbrowser
import urllib.parse
import datetime

import numpy as np
import pyaudio
import speech_recognition as sr
import openwakeword
from openwakeword.model import Model as WakeWordModel
from pynput import keyboard as pynput_keyboard

import tkinter as tk

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1280
WAKE_THRESHOLD = 0.5
TOGGLE_COOLDOWN_SEC = 1.5
SAMPLE_WIDTH_BYTES = 2

SILENCE_TIMEOUT_SEC = 8.0
SILENCE_AMPLITUDE_THRESHOLD = 300
MIN_SESSION_DURATION_SEC = 0.3
RECOGNITION_MAX_RETRIES = 1
RECOGNITION_RETRY_DELAY_SEC = 1.0

HOTKEY_COMBO = "<ctrl>+<shift>+`"

WAKE_WORD_TAIL_PATTERNS = [
    r"\balexa\b", r"\ba lexa\b", r"\balex a\b", r"\baleksa\b",
]

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
    "stackoverflow": "https://stackoverflow.com/search?q={}",
    "octopart": "https://octopart.com/search?q={}",
    "allaboutcircuits": "https://www.allaboutcircuits.com/search/?q={}",
    "engineeringtoolbox": "https://www.engineeringtoolbox.com/search.php?q={}",
}

DESTINATION_ALIASES = {
    "google dot com": "google", "google.com": "google", "google": "google",
    "wikipedia dot org": "wikipedia", "wikipedia.org": "wikipedia",
    "wikipedia": "wikipedia", "wiki": "wikipedia",
    "youtube dot com": "youtube", "youtube.com": "youtube",
    "you tube": "youtube", "youtube": "youtube",
    "wolfram alpha dot com": "wolframalpha", "wolfram alpha": "wolframalpha",
    "wolframalpha": "wolframalpha", "wolfram": "wolframalpha", "alpha": "wolframalpha",
    "khan academy": "khanacademy", "khanacademy": "khanacademy", "khan": "khanacademy",
    "geeks for geeks": "geeksforgeeks", "geeksforgeeks": "geeksforgeeks", "geeks": "geeksforgeeks",
    "desmos dot com": "desmos", "desmos": "desmos", "graph": "desmos",
    "pauls notes": "paulsnotes", "paulsnotes": "paulsnotes", "pauls": "paulsnotes",
    "math stack exchange": "stackexchange", "stack exchange": "stackexchange",
    "stackexchange": "stackexchange", "stack": "stackexchange",
    "physics stack exchange": "physicsstackexchange",
    "electronics stack exchange": "electronicsstackexchange",
    "mit ocw": "mitocw", "mit open course ware": "mitocw", "mitocw": "mitocw",
    "mit": "mitocw", "ocw": "mitocw",
    "arxiv dot org": "arxiv", "arxiv": "arxiv",
    "symbolab dot com": "symbolab", "symbolab": "symbolab",
    "math world": "mathworld", "mathworld": "mathworld",
    "ieee explore": "ieee", "ieee": "ieee",
    "coursera dot org": "coursera", "coursera": "coursera",
    "github dot com": "github", "github": "github", "hub": "github",
    "stack overflow": "stackoverflow", "stackoverflow": "stackoverflow",
    "octopart": "octopart",
    "all about circuits": "allaboutcircuits", "allaboutcircuits": "allaboutcircuits",
    "engineering toolbox": "engineeringtoolbox", "engineeringtoolbox": "engineeringtoolbox",
}
_DESTINATION_KEYS_BY_LENGTH = sorted(DESTINATION_ALIASES.keys(), key=lambda k: -len(k.split()))
DEFAULT_DESTINATION = "google"


def log(msg):
    ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts}] {msg}")


def _make_tone(freq, duration, volume=0.4, sr_=RATE):
    t = np.linspace(0, duration, int(sr_ * duration), False)
    tone = np.sin(freq * t * 2 * np.pi)
    fade = int(sr_ * 0.005)
    tone[:fade] *= np.linspace(0, 1, fade)
    tone[-fade:] *= np.linspace(1, 0, fade)
    return (tone * volume * 32767).astype(np.int16)


ACTIVATE_BEEP = _make_tone(880, 0.12)
DEACTIVATE_BEEPS = np.concatenate([
    _make_tone(440, 0.08), np.zeros(int(RATE * 0.05), dtype=np.int16),
    _make_tone(440, 0.08), np.zeros(int(RATE * 0.05), dtype=np.int16),
    _make_tone(440, 0.08),
])
TIMEOUT_BEEPS = np.concatenate([
    _make_tone(300, 0.15), np.zeros(int(RATE * 0.08), dtype=np.int16),
    _make_tone(300, 0.15),
])


def play_tone_async(pa, tone_array):
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


def strip_trailing_wake_word(text):
    stripped = text.strip()
    for pattern in WAKE_WORD_TAIL_PATTERNS:
        new_text = re.sub(pattern + r"[\.\!\?,]*\s*$", "", stripped, flags=re.IGNORECASE)
        if new_text != stripped:
            log(f"Stripped trailing wake word: '{stripped}' -> '{new_text.strip()}'")
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
    """
    Spoken exponentiation, several phrasings:
      "x power five" / "x to the power five" / "x to the power of five"
      "x to the power 5" / "x to the fifth" / "x to the fifth power"
    "power to the x" (base after the word) is left unedited -- ambiguous,
    safer for the user to fix by hand than to guess.
    """
    num_group = rf"({_NUM_WORD_PATTERN}|\d+)"
    ordinal_group = rf"({_ORDINAL_PATTERN})"
    patterns = [
        (rf"(\w+)\s+to\s+the\s+power\s+of\s+{num_group}\b", 1),
        (rf"(\w+)\s+to\s+the\s+power\s+{num_group}\b", 1),
        (rf"(\w+)\s+power\s+of\s+{num_group}\b", 1),
        (rf"(\w+)\s+power\s+{num_group}\b", 1),
        (rf"(\w+)\s+to\s+the\s+{ordinal_group}\s+power\b", 1),
        (rf"(\w+)\s+to\s+the\s+{ordinal_group}\b", 1),
    ]

    def _sub(match):
        return f"{match.group(1)}^{_word_to_digit(match.group(2))}"

    result = text
    for pattern, _ in patterns:
        result = re.sub(pattern, _sub, result, flags=re.IGNORECASE)
    return result


def _replace_subscript_variants(text):
    """ "x sub i" / "x subscript i" / "a sub two" -> "x_i", "a_2" """
    pattern = r"(\w+)\s+sub(?:script)?\s+(\w+)\b"
    return re.sub(pattern, lambda m: f"{m.group(1)}_{_word_to_digit(m.group(2))}",
                  text, flags=re.IGNORECASE)


def _replace_fraction_variants(text):
    """ "a over b" -> "a/b" (only for simple single-token operands) """
    pattern = r"\b(\w+)\s+over\s+(\w+)\b"
    return re.sub(pattern, lambda m: f"{m.group(1)}/{m.group(2)}", text, flags=re.IGNORECASE)


MATH_SUBSTITUTIONS = [
    (r"\bdouble integral of\b", "\u222c"),
    (r"\btriple integral of\b", "\u222d"),
    (r"\bcontour integral of\b", "\u222e"),
    (r"\bline integral of\b", "\u222e"),
    (r"\bintegral of\b", "\u222b"),
    (r"\bindefinite integral of\b", "\u222b"),
    (r"\bsquare root of\b", "\u221a"),
    (r"\bcube root of\b", "\u221b"),
    (r"\bfourth root of\b", "\u221c"),
    (r"\bnth root of\b", "\u221c"),
    (r"\bsummation of\b", "\u03a3"),
    (r"\bsum of\b", "\u03a3"),
    (r"\bproduct of\b", "\u03a0"),
    (r"\bsecond partial derivative of\b", "\u2202\u00b2"),
    (r"\bpartial derivative of\b", "\u2202"),
    (r"\bderivative of\b", "d/dx"),
    (r"\bgradient of\b", "\u2207"),
    (r"\bdivergence of\b", "\u2207\u00b7"),
    (r"\bcurl of\b", "\u2207\u00d7"),
    (r"\blaplacian of\b", "\u2207\u00b2"),
    (r"\bnabla\b", "\u2207"),
    (r"\bpositive infinity\b", "+\u221e"),
    (r"\bnegative infinity\b", "\u2212\u221e"),
    (r"\binfinity\b", "\u221e"),
    (r"\bplus or minus\b", "\u00b1"),
    (r"\bminus or plus\b", "\u2213"),
    (r"\bnot equal to\b", "\u2260"),
    (r"\bapproximately equal to\b", "\u2248"),
    (r"\bapproximately\b", "\u2248"),
    (r"\bidentical to\b", "\u2261"),
    (r"\bproportional to\b", "\u221d"),
    (r"\bgreater than or equal to\b", "\u2265"),
    (r"\bat least\b", "\u2265"),
    (r"\bless than or equal to\b", "\u2264"),
    (r"\bat most\b", "\u2264"),
    (r"\bgreater than\b", ">"),
    (r"\bless than\b", "<"),
    (r"\bfor all\b", "\u2200"),
    (r"\bthere exists\b", "\u2203"),
    (r"\bdoes not exist\b", "\u2204"),
    (r"\belement of\b", "\u2208"),
    (r"\bnot an element of\b", "\u2209"),
    (r"\bsubset of\b", "\u2282"),
    (r"\bsuperset of\b", "\u2283"),
    (r"\bunion\b", "\u222a"),
    (r"\bintersection\b", "\u2229"),
    (r"\bempty set\b", "\u2205"),
    (r"\bfactorial\b", "!"),
    (r"\bpercent\b", "%"),
    (r"\bperpendicular to\b", "\u22a5"),
    (r"\bparallel to\b", "\u2225"),
    (r"\bcongruent to\b", "\u2245"),
    (r"\bsimilar to\b", "\u223c"),
    (r"\btherefore\b", "\u2234"),
    (r"\bbecause\b", "\u2235"),
    (r"\bplus\b", "+"),
    (r"\bminus\b", "\u2212"),
    (r"\btimes\b", "\u00d7"),
    (r"\bmultiplied by\b", "\u00d7"),
    (r"\bdivided by\b", "\u00f7"),
    (r"\bequals\b", "="),
    (r"\bis equal to\b", "="),
    (r"\bsquared\b", "\u00b2"),
    (r"\bcubed\b", "\u00b3"),
    (r"\bdegrees\b", "\u00b0"),
    (r"\bdegree\b", "\u00b0"),
    (r"\btheta\b", "\u03b8"), (r"\balpha\b", "\u03b1"), (r"\bbeta\b", "\u03b2"),
    (r"\bgamma\b", "\u03b3"), (r"\bdelta\b", "\u03b4"), (r"\bepsilon\b", "\u03b5"),
    (r"\bzeta\b", "\u03b6"), (r"\beta\b", "\u03b7"), (r"\biota\b", "\u03b9"),
    (r"\bkappa\b", "\u03ba"), (r"\blambda\b", "\u03bb"), (r"\bmu\b", "\u03bc"),
    (r"\bnu\b", "\u03bd"), (r"\bxi\b", "\u03be"), (r"\bpi\b", "\u03c0"),
    (r"\brho\b", "\u03c1"), (r"\bsigma\b", "\u03c3"), (r"\btau\b", "\u03c4"),
    (r"\bphi\b", "\u03c6"), (r"\bchi\b", "\u03c7"), (r"\bpsi\b", "\u03c8"),
    (r"\bomega\b", "\u03c9"),
    (r"\bohm\b", "\u03a9"), (r"\bohms\b", "\u03a9"),
]


def apply_math_substitutions(text):
    # Multi-word structural rules run first (power, subscript, fraction)
    # since they consume phrases that single-word rules below would
    # otherwise partially match and mangle.
    result = _replace_power_variants(text)
    result = _replace_subscript_variants(result)
    result = _replace_fraction_variants(result)
    for pattern, replacement in MATH_SUBSTITUTIONS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def parse_destination(text):
    stripped = text.strip()
    lowered = stripped.lower()
    for alias in _DESTINATION_KEYS_BY_LENGTH:
        pattern = r"^" + re.escape(alias) + r"[\s,]*"
        match = re.match(pattern, lowered)
        if match:
            remainder = stripped[match.end():].strip()
            return DESTINATION_ALIASES[alias], remainder
    return DEFAULT_DESTINATION, stripped


def open_search(destination, query):
    if not query:
        return
    url = SEARCH_URLS.get(destination, SEARCH_URLS[DEFAULT_DESTINATION]).format(
        urllib.parse.quote_plus(query))
    log(f"Opening: {destination} -> {url}")
    webbrowser.open(url)


class ConfirmWindow:
    def __init__(self, root, initial_text):
        self.top = tk.Toplevel(root)
        self.top.title("Confirm search")
        self.top.attributes("-topmost", True)
        self.top.geometry("500x280")
        self.top.protocol("WM_DELETE_WINDOW", self._on_cancel)

        destination, query = parse_destination(initial_text)
        query = apply_math_substitutions(query)
        self.destination = destination

        tk.Label(self.top, text=f"Query (edit if needed) -- searching: {destination}",
                 anchor="w", wraplength=480).pack(fill="x", padx=10, pady=(10, 2))

        self.text_box = tk.Text(self.top, height=7, wrap="word", undo=True)
        self.text_box.insert("1.0", query)
        self.text_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._bind_shortcuts()

        btn_row = tk.Frame(self.top)
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        tk.Button(btn_row, text="Cancel", command=self._on_cancel).pack(side="right", padx=(6, 0))
        tk.Button(btn_row, text="Go", bg="#2ecc71", command=self._on_go).pack(side="right")

        self.text_box.focus_set()
        self.text_box.mark_set("insert", "end")

    def _bind_shortcuts(self):
        widget = self.text_box

        def select_all(event=None):
            widget.tag_add("sel", "1.0", "end-1c")
            widget.mark_set("insert", "end-1c")
            return "break"

        def delete_word_before_cursor(event=None):
            widget.delete("insert-1c wordstart", "insert")
            return "break"

        def redo(event=None):
            try:
                widget.edit_redo()
            except tk.TclError:
                pass
            return "break"

        widget.bind("<Control-a>", select_all)
        widget.bind("<Control-A>", select_all)
        widget.bind("<Control-BackSpace>", delete_word_before_cursor)
        widget.bind("<Control-y>", redo)
        widget.bind("<Control-Shift-Key-Z>", redo)

    def _on_go(self):
        open_search(self.destination, self.text_box.get("1.0", "end").strip())
        self.top.destroy()

    def _on_cancel(self):
        log("Cancelled -- no search sent.")
        self.top.destroy()


class StatusWindow:
    METER_WIDTH = 280
    METER_HEIGHT = 28
    METER_BAR_COUNT = 24
    METER_MAX_RMS = 6000
    METER_DECAY = 0.75  # smoothing so the meter doesn't flicker frame-to-frame

    def __init__(self, root, on_quit):
        self.top = tk.Toplevel(root)
        self.top.title("Voice search")
        self.top.attributes("-topmost", True)
        self.top.geometry("320x210+40+40")
        self.top.configure(bg="#1e1e1e")
        self.top.protocol("WM_DELETE_WINDOW", on_quit)

        self.status_label = tk.Label(self.top, text="Idle -- say 'Alexa'",
                                      font=("Sans", 11, "bold"), fg="#ccc", bg="#1e1e1e")
        self.status_label.pack(pady=(14, 2))

        self.hotkey_label = tk.Label(self.top, text=f"or press {HOTKEY_COMBO}",
                                      font=("Sans", 8), fg="#777", bg="#1e1e1e")
        self.hotkey_label.pack(pady=(0, 10))

        self.meter_canvas = tk.Canvas(self.top, width=self.METER_WIDTH,
                                       height=self.METER_HEIGHT, bg="#1e1e1e",
                                       highlightthickness=0)
        self.meter_canvas.pack(pady=(0, 12))

        self._smoothed_frac = 0.0
        self._bar_ids = []
        bar_gap = 3
        bar_width = (self.METER_WIDTH - bar_gap * (self.METER_BAR_COUNT - 1)) / self.METER_BAR_COUNT
        for i in range(self.METER_BAR_COUNT):
            x0 = i * (bar_width + bar_gap)
            bar_id = self.meter_canvas.create_rectangle(
                x0, self.METER_HEIGHT, x0 + bar_width, self.METER_HEIGHT,
                fill="#2ecc71", width=0)
            self._bar_ids.append(bar_id)

        tk.Button(self.top, text="Quit", command=on_quit, bg="#e74c3c", fg="white",
                  relief="flat", padx=12, pady=4).pack(pady=(4, 12))

    def set_idle(self):
        self.status_label.config(text="Idle -- say 'Alexa'", fg="#ccc")
        self._smoothed_frac = 0.0
        self._redraw_meter(0.0)

    def set_listening(self):
        self.status_label.config(text="Listening... (say 'Alexa' or hotkey to stop)", fg="#2ecc71")

    def set_transcribing(self):
        self.status_label.config(text="Transcribing...", fg="#e67e22")
        self._smoothed_frac = 0.0
        self._redraw_meter(0.0)

    def set_timed_out(self):
        self.status_label.config(text="No speech detected -- stopped", fg="#e74c3c")
        self._smoothed_frac = 0.0
        self._redraw_meter(0.0)

    def set_meter(self, rms):
        target_frac = min(1.0, rms / self.METER_MAX_RMS)
        # Exponential smoothing: bars ease toward the new level instead of
        # jumping every 80ms chunk, which reads as jittery on a real mic.
        self._smoothed_frac = (self.METER_DECAY * self._smoothed_frac
                                + (1 - self.METER_DECAY) * target_frac)
        self._redraw_meter(self._smoothed_frac)

    def _redraw_meter(self, frac):
        lit_bars = round(frac * self.METER_BAR_COUNT)
        for i, bar_id in enumerate(self._bar_ids):
            if i < lit_bars:
                bar_frac = i / self.METER_BAR_COUNT
                if bar_frac < 0.6:
                    color = "#2ecc71"
                elif bar_frac < 0.85:
                    color = "#f1c40f"
                else:
                    color = "#e74c3c"
                height = self.METER_HEIGHT
            else:
                color = "#333"
                height = 4
            coords = self.meter_canvas.coords(bar_id)
            x0, x1 = coords[0], coords[2]
            y_top = self.METER_HEIGHT - height
            self.meter_canvas.coords(bar_id, x0, y_top, x1, self.METER_HEIGHT)
            self.meter_canvas.itemconfig(bar_id, fill=color)


class AudioWorker(threading.Thread):
    def __init__(self, ui_queue, pa):
        super().__init__(daemon=True)
        self.ui_queue = ui_queue
        self.pa = pa
        self.running = True

        # Guards is_active / recorded_frames / session bookkeeping against
        # concurrent activate/deactivate calls arriving from two different
        # threads: the capture loop (wake word) and pynput's own listener
        # thread (global hotkey).
        self._state_lock = threading.Lock()

        self.is_active = False
        self.last_toggle_time = 0.0
        self.last_sound_time = 0.0
        self.recorded_frames = []
        self.session_start_ts = None
        self.frames_captured_this_session = 0

        log("Loading wake word model...")
        alexa_path = openwakeword.get_pretrained_model_paths()[list(openwakeword.models.keys()).index("alexa")]
        self.oww_model = WakeWordModel(wakeword_model_paths=[alexa_path])
            
        self.stream = self.pa.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                    input=True, frames_per_buffer=CHUNK)
        self.recognizer = sr.Recognizer()

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
        play_tone_async(self.pa, ACTIVATE_BEEP)
        self.ui_queue.put(("listening_started", None))

    def _deactivate(self, source, timed_out=False):
        with self._state_lock:
            if not self.is_active:
                return
            self.is_active = False
            now = time.time()
            duration = now - self.session_start_ts if self.session_start_ts else 0.0
            frames = self.recorded_frames
            frame_count = self.frames_captured_this_session
            self.recorded_frames = []

        reason = "SILENCE TIMEOUT" if timed_out else f"DEACTIVATE (via {source})"
        log(f"{reason} -- duration={duration:.2f}s frames={frame_count} "
            f"bytes={sum(len(f) for f in frames)}")

        # Explicit checks, not `assert` -- asserts are removed entirely
        # when Python runs with -O, which would silently disable this
        # safety check. This must never be optimizable away.
        if self.is_active is not False:
            raise RuntimeError("AUDIO BOUNDARY VIOLATION: is_active still True after deactivate")
        if len(self.recorded_frames) != 0:
            raise RuntimeError("AUDIO BOUNDARY VIOLATION: buffer not cleared after deactivate")
        log("Invariant check passed (capture off, buffer cleared).")

        if timed_out:
            play_tone_async(self.pa, TIMEOUT_BEEPS)
            self.ui_queue.put(("timed_out", None))
            log("Session discarded (silence timeout) -- nothing sent.")
            return

        if duration < MIN_SESSION_DURATION_SEC:
            log(f"Session too short ({duration:.2f}s < {MIN_SESSION_DURATION_SEC}s) -- discarded, nothing sent.")
            play_tone_async(self.pa, DEACTIVATE_BEEPS)
            self.ui_queue.put(("listening_stopped", ""))
            return

        play_tone_async(self.pa, DEACTIVATE_BEEPS)
        self.ui_queue.put(("transcribing", None))
        threading.Thread(target=self._transcribe_and_report, args=(frames,), daemon=True).start()

    def toggle_from_hotkey(self):
        if not self.is_active:
            self._activate(source="hotkey")
        else:
            self._deactivate(source="hotkey")

    def _toggle_from_wake_word(self):
        now = time.time()
        if now - self.last_toggle_time < TOGGLE_COOLDOWN_SEC:
            log("Wake word inside cooldown -- ignored.")
            return
        self.last_toggle_time = now
        if not self.is_active:
            self._activate(source="wake word")
        else:
            self._deactivate(source="wake word")

    def _transcribe_and_report(self, frames):
        text = ""
        if not frames:
            log("No frames captured -- nothing sent.")
            self.ui_queue.put(("listening_stopped", text))
            return

        raw_audio = b"".join(frames)
        log(f"Sending {len(raw_audio)} bytes (~{len(raw_audio)/(RATE*SAMPLE_WIDTH_BYTES):.2f}s) to Google.")
        audio_data = sr.AudioData(raw_audio, RATE, SAMPLE_WIDTH_BYTES)

        attempt = 0
        while attempt <= RECOGNITION_MAX_RETRIES:
            try:
                text = self.recognizer.recognize_google(audio_data)
                log(f"Transcription received: '{text}'")
                text = strip_trailing_wake_word(text)
                break
            except sr.UnknownValueError:
                log("Google could not understand the audio.")
                text = ""
                break
            except sr.RequestError as e:
                attempt += 1
                if attempt > RECOGNITION_MAX_RETRIES:
                    log(f"Speech recognition service error, no retries left: {e}")
                    text = ""
                    break
                log(f"Speech recognition service error, retrying in {RECOGNITION_RETRY_DELAY_SEC}s: {e}")
                time.sleep(RECOGNITION_RETRY_DELAY_SEC)

        self.ui_queue.put(("listening_stopped", text))

    def run(self):
        try:
            while self.running:
                raw = self.stream.read(CHUNK, exception_on_overflow=False)
                samples = np.frombuffer(raw, dtype=np.int16)

                prediction = self.oww_model.predict(samples)
                if any(score > WAKE_THRESHOLD for score in prediction.values()):
                    self._toggle_from_wake_word()

                if self.is_active:
                    with self._state_lock:
                        # Re-check is_active inside the lock: a concurrent
                        # deactivate (from the hotkey thread) could have
                        # flipped it between the check above and here.
                        if self.is_active:
                            self.recorded_frames.append(raw)
                            self.frames_captured_this_session += 1

                    level = rms_amplitude(samples)
                    self.ui_queue.put(("meter", level))
                    if level > SILENCE_AMPLITUDE_THRESHOLD:
                        self.last_sound_time = time.time()
                    elif time.time() - self.last_sound_time > SILENCE_TIMEOUT_SEC:
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

        self.ui_queue = queue.Queue()
        self.pa = pyaudio.PyAudio()
        self.status_window = StatusWindow(self.root, on_quit=self.quit)

        self.worker = AudioWorker(self.ui_queue, self.pa)
        self.worker.start()

        self.hotkey_listener = pynput_keyboard.GlobalHotKeys({
            HOTKEY_COMBO: self.worker.toggle_from_hotkey,
        })
        self.hotkey_listener.start()
        log(f"Global hotkey active: {HOTKEY_COMBO}")

        self.root.after(self.POLL_MS, self.poll_queue)

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
                        ConfirmWindow(self.root, payload)
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
        log(f"Listening for 'Alexa' or {HOTKEY_COMBO}. Quit button or Ctrl+C to exit.")
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit()


if __name__ == "__main__":
    App().run()
