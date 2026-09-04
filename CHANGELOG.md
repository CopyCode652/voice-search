# Changelog

All notable changes to this project are documented in this file.

## V3

### Added

- **Massively expanded math dictation, tuned for EE/engineering use.** `MATH_SUBSTITUTIONS` more than doubled (90 → 200+ patterns) and gained several new phrase-level parsers on top of the flat symbol table:
  - Calculus: `limit as x approaches infinity of ...`, `limit of ... as x approaches 0`, `limit superior`/`limit inferior`, definite integrals with bounds (`integral from 0 to 1 of x squared dx` → `∫_{0}^{1} x² dx`), nth/partial derivatives (`third derivative of y with respect to t` → `d³y/dt³`).
  - Linear algebra: `eigenvalues of A`, `eigenvector of A`, `rank of A`, `norm of v` (→ `‖v‖`), `kernel of T`, `span of v`.
  - Complex numbers / phasors: `real part of z`, `imaginary part of z`, `complex conjugate of z`, `j omega` → `jω`.
  - Statistics/probability: `standard deviation of X`, `variance of X`, `expected value of X`, `probability of A`.
  - Number theory: `a mod b`, `gcd of a and b`, `lcm of a and b`, `a is congruent to b mod n`, `a divides b`.
  - Combinatorics: `n choose k`, `n permute k`.
  - Digital logic gates (core to EE): `A nand B`, `A nor B`, `A xor B`, `A xnor B` rendered as their proper symbols.
  - Vector notation (`x hat` → x̂, `vector v` / `v vector` → v⃗) and convolution shorthand (`convolution of x and h` → `conv(x, h)`, `x convolved with h` → `x * h`).
  - ~50 new capital Greek letters, set-theory symbols, extended logic operators, and EE units (siemens, tesla, weber, ms/µs/ns/ps, kbps/Mbps/Gbps, radians) plus signals/systems shorthand (`transfer function` → `H(s)`, `impulse response` → `h(t)`, `unit step function` → `u(t)`, `dirac delta`).
- **7 new sound themes** (12 total, up from 5), adding **triangle**, **sawtooth**, and **filtered-noise** waveforms alongside the existing sine/square/soft: Retro arcade, Deep pulse, Marimba chime, Alert siren, Typewriter click, Bell tone, Laser tap.
- **Volume control for tones**, adjustable from Settings → Audio & Tones as a 0–100% slider with a live readout. Applies immediately (no restart needed) and the Preview button plays at the currently-selected volume. Persisted as `tone_volume` in settings; fully backward-compatible with prior versions (defaults to the old hardcoded level).
- **`RoundedCard`** (in `theme.py`) — a true rounded-corner surface with a soft layered drop-shadow for borderless/floating windows, replacing the old flat 1px-border-frame approximation. Applied to the Confirm popup, which now visually reads as a floating card rather than a plain rectangle, in both dark and light themes.
- New design tokens (`accent_press`, `accent_soft`, `shadow_soft`) so pressed/selected states no longer reuse the hover color — buttons now have a distinct, slightly darker pressed color plus a small tactile "settle" inset on click instead of an instant flat color swap.

### Changed

- `PillButton` press feedback is now visually distinct from hover feedback (previously both states shared the same color).
- The Confirm popup grew slightly (260px → 300px tall) to accommodate the new rounded-card padding and shadow without clipping the button row.
- App background darkened slightly (`#15161a` → `#111217`) in dark mode to increase contrast against elevated cards now that cards have visible shadows.

## V2

### Added

- **Voice-launchable applications.** You can now say "open", "launch", "start", "run", or "fire up" followed by an app name to open a local application directly, instead of running a search. Supports a wide catalog of apps across development, design, office, engineering/EDA, communication, browsers, and system utilities.
- **`app_catalog.py`** — a new module holding the full catalog of voice-launchable applications: display names, categories, icons, spoken aliases, and the executable names/paths tried for each one.
- **`theme.py`** — a new shared design system used by every window in the application (colors, fonts, spacing, and reusable themed components), replacing the per-window, hand-picked colors used previously.
- **Redesigned confirmation window**, now styled as a compact command-palette-style popup with a visible destination pill, keyboard shortcuts (Enter to search, Shift+Enter for a newline, Escape to cancel), and animated feedback on the Copy button.
- **Redesigned settings window**, now organized with sidebar navigation (General, Behavior, Audio & Tones, Advanced, Voice Apps, Actions) instead of a single long scrolling list, with toggle switches and sliders with live value readouts.
- **New "Voice Apps" section in Settings**, listing every voice-launchable application grouped by category, so the available commands are discoverable from within the app.
- **Redesigned status window**, with a colored status indicator dot and a smoother, color-ramped audio level meter.
- **Redesigned history window**, with a live search/filter box for past queries.
- **Redesigned notifications (toasts)**, now with a fade-in/fade-out animation and a colored accent strip instead of a flat colored box.
- Filler-word handling for app commands — phrases like "open up obsidian" or "open the file manager" are now recognized correctly instead of falling through to a search.
- Cross-platform executable paths for several applications, so entries added for Windows and macOS can actually be found and launched, not just Linux binaries.

### Changed

- Switching the interface theme (dark/light) in Settings now updates every open window immediately — status bar, confirmation popup, settings window, history window, and toasts — instead of only the status bar.
- The settings window's hotkey recorder now always cleans up its key-capture state, including when the recording is cancelled via Escape or abandoned without pressing a valid combination.
- The post-deactivation state check in the audio worker now verifies a consistent snapshot of shared state taken while the associated lock is held, rather than reading that state just after releasing the lock.
- The confirmation window's Copy button now restores its themed appearance after use instead of resetting to a hardcoded color.

### Fixed

- Fixed app-launch voice commands silently failing to match when a filler word ("the", "a", "an", "my", "up") appeared between the trigger word and the app name.
- Fixed a settings window issue where starting to record a new hotkey and then clicking away (without completing the recording) could leave the window permanently capturing keystrokes.
- Fixed a missing display label for one of the previously supported applications, which would have shown its internal identifier instead of a proper name.
- Fixed the interface theme only partially applying across the application after being changed in Settings.

## V1

- Wake-word activation ("Alexa") using `openWakeWord`.
- Global hotkey activation using `pynput`.
- Local microphone capture using PyAudio.
- Speech transcription via Google Web Speech through `SpeechRecognition`.
- Editable transcription before searching.
- Silence timeout when no speech is detected.
- Audio level meter while recording.
- Activation and deactivation sounds.
- Multiple search destinations with natural-language destination aliases.
- Spoken mathematical notation conversion.
- Background transcription to keep the GUI responsive.
- Thread-safe recording state with explicit audio-boundary checks.
- Timestamped runtime logging.