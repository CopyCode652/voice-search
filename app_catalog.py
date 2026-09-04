"""
Catalog of locally launchable applications for the "open <app>" voice command.

Expanded from the original ~35 apps to a much broader set covering code
editors, browsers, office suites, media, comms, EDA/engineering tools,
system utilities, and cross-platform fallbacks (Windows/macOS executable
names alongside Linux binary names, since APP_LAUNCHERS previously only
had Linux binaries).
"""
 
import collections

AppEntry = collections.namedtuple("AppEntry", ["label", "category", "icon", "launchers"])

# category -> display order / icon, used to group the Settings/app list UI
CATEGORIES = [
    ("code", "Development", "\U0001f4bb"),
    ("design", "Design & Media", "\U0001f3a8"),
    ("office", "Office & Notes", "\U0001f4dd"),
    ("engineering", "Engineering & EDA", "\U0001f50c"),
    ("comms", "Communication", "\U0001f4ac"),
    ("browser", "Browsers", "\U0001f310"),
    ("system", "System & Utilities", "\u2699"),
    ("science", "Science & Math", "\U0001f9ee"),
]

APPS = {
    # ---- Development -------------------------------------------------
    "vscode": AppEntry("VS Code", "code", "\U0001f4bb",
                        ["code", "code-insiders", "vscodium",
                         "C:\\Program Files\\Microsoft VS Code\\Code.exe",
                         "/Applications/Visual Studio Code.app"]),
    "sublimetext": AppEntry("Sublime Text", "code", "\U0001f4bb",
                             ["subl", "sublime_text",
                              "C:\\Program Files\\Sublime Text\\sublime_text.exe",
                              "/Applications/Sublime Text.app"]),
    "atom": AppEntry("Atom", "code", "\U0001f4bb", ["atom"]),
    "vim": AppEntry("Vim", "code", "\U0001f4bb", ["vim", "gvim"]),
    "neovim": AppEntry("Neovim", "code", "\U0001f4bb", ["nvim"]),
    "emacs": AppEntry("Emacs", "code", "\U0001f4bb", ["emacs"]),
    "jupyter": AppEntry("Jupyter Notebook", "code", "\U0001f4d3", ["jupyter-notebook", "jupyter-lab", "jupyter"]),
    "spyder": AppEntry("Spyder", "code", "\U0001f40d", ["spyder", "spyder3"]),
    "pycharm": AppEntry("PyCharm", "code", "\U0001f40d",
                         ["pycharm", "pycharm.sh",
                          "/Applications/PyCharm.app"]),
    "intellij": AppEntry("IntelliJ IDEA", "code", "\u2615", ["idea", "idea.sh"]),
    "androidstudio": AppEntry("Android Studio", "code", "\U0001f4f1", ["studio", "studio.sh"]),
    "docker": AppEntry("Docker Desktop", "code", "\U0001f433",
                        ["docker-desktop",
                         "C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe",
                         "/Applications/Docker.app"]),
    "postman": AppEntry("Postman", "code", "\U0001f4ee", ["postman"]),
    "github_desktop": AppEntry("GitHub Desktop", "code", "\U0001f419", ["github-desktop", "GitHubDesktop"]),
    "gitkraken": AppEntry("GitKraken", "code", "\U0001f419", ["gitkraken"]),
    "arduino": AppEntry("Arduino IDE", "code", "\U0001f527", ["arduino", "arduino-ide"]),
    "platformio": AppEntry("PlatformIO", "code", "\U0001f527", ["platformio", "pio"]),
    "wireshark": AppEntry("Wireshark", "code", "\U0001f50d", ["wireshark"]),
    "terminal": AppEntry("Terminal", "code", "\u2328",
                          ["konsole", "alacritty", "kitty", "gnome-terminal", "xterm", "wt", "cmd"]),
    "windowsterminal": AppEntry("Windows Terminal", "code", "\u2328", ["wt"]),

    # ---- Design & Media ------------------------------------------------
    "gimp": AppEntry("GIMP", "design", "\U0001f5bc", ["gimp"]),
    "inkscape": AppEntry("Inkscape", "design", "\u270f", ["inkscape"]),
    "blender": AppEntry("Blender", "design", "\U0001f9ca", ["blender"]),
    "krita": AppEntry("Krita", "design", "\U0001f3a8", ["krita"]),
    "figma": AppEntry("Figma", "design", "\U0001f3a8", ["figma", "figma-linux"]),
    "audacity": AppEntry("Audacity", "design", "\U0001f3a4", ["audacity"]),
    "obs": AppEntry("OBS Studio", "design", "\U0001f3a5", ["obs"]),
    "davinciresolve": AppEntry("DaVinci Resolve", "design", "\U0001f3ac", ["resolve"]),
    "vlc": AppEntry("VLC", "design", "\U0001f3ac", ["vlc"]),
    "spotify": AppEntry("Spotify", "design", "\U0001f3b5", ["spotify"]),

    # ---- Office & Notes --------------------------------------------------
    "obsidian": AppEntry("Obsidian", "office", "\U0001f5c2", ["obsidian"]),
    "notion": AppEntry("Notion", "office", "\U0001f5c2", ["notion", "notion-app"]),
    "koodoreader": AppEntry("Koodo Reader", "office", "\U0001f4d6", ["koodo-reader", "koodoreader"]),
    "anki": AppEntry("Anki", "office", "\U0001f9e0", ["anki"]),
    "zathura": AppEntry("Zathura", "office", "\U0001f4c4", ["zathura"]),
    "okular": AppEntry("Okular", "office", "\U0001f4c4", ["okular"]),
    "xournalpp": AppEntry("Xournal++", "office", "\u270d", ["xournalpp", "xournal++"]),
    "texstudio": AppEntry("TeXstudio", "office", "\U0001f4dc", ["texstudio"]),
    "overleaf": AppEntry("Overleaf (browser)", "office", "\U0001f4dc", []),
    "libreoffice_writer": AppEntry("LibreOffice Writer", "office", "\U0001f4dd", ["libreoffice --writer", "soffice --writer"]),
    "libreoffice_calc": AppEntry("LibreOffice Calc", "office", "\U0001f4ca", ["libreoffice --calc", "soffice --calc"]),
    "libreoffice_impress": AppEntry("LibreOffice Impress", "office", "\U0001f4fd", ["libreoffice --impress", "soffice --impress"]),
    "word": AppEntry("Microsoft Word", "office", "\U0001f4dd",
                      ["winword", "C:\\Program Files\\Microsoft Office\\root\\Office16\\WINWORD.EXE"]),
    "excel": AppEntry("Microsoft Excel", "office", "\U0001f4ca",
                       ["excel", "C:\\Program Files\\Microsoft Office\\root\\Office16\\EXCEL.EXE"]),
    "powerpoint": AppEntry("Microsoft PowerPoint", "office", "\U0001f4fd",
                            ["powerpnt", "C:\\Program Files\\Microsoft Office\\root\\Office16\\POWERPNT.EXE"]),
    "onenote": AppEntry("OneNote", "office", "\U0001f5c2", ["onenote"]),
    "calculator": AppEntry("Calculator", "office", "\U0001f9ee", ["qalculate-gtk", "gnome-calculator", "kcalc", "calc"]),
    "files": AppEntry("File Manager", "office", "\U0001f4c1", ["nautilus", "thunar", "dolphin", "pcmanfm", "explorer"]),

    # ---- Engineering & EDA ------------------------------------------------
    "kicad": AppEntry("KiCad", "engineering", "\U0001f50c", ["kicad"]),
    "ltspice": AppEntry("LTspice", "engineering", "\u26a1", ["ltspice"]),
    "ngspice": AppEntry("ngspice", "engineering", "\u26a1", ["ngspice"]),
    "gtkwave": AppEntry("GTKWave", "engineering", "\U0001f4c8", ["gtkwave"]),
    "freecad": AppEntry("FreeCAD", "engineering", "\U0001f4d0", ["freecad", "FreeCAD"]),
    "fritzing": AppEntry("Fritzing", "engineering", "\U0001f50c", ["fritzing"]),
    "qucs": AppEntry("Qucs-S", "engineering", "\u26a1", ["qucs-s", "qucs"]),
    "gnuradio": AppEntry("GNU Radio Companion", "engineering", "\U0001f4e1", ["gnuradio-companion"]),
    "solidworks": AppEntry("SolidWorks", "engineering", "\U0001f4d0", ["sldworks", "SLDWORKS.exe"]),
    "autocad": AppEntry("AutoCAD", "engineering", "\U0001f4d0", ["acad", "AutoCAD.exe"]),
    "matlab": AppEntry("MATLAB", "engineering", "\U0001f4d0", ["matlab"]),
    "octave": AppEntry("GNU Octave", "engineering", "\U0001f522", ["octave", "octave-cli"]),

    # ---- Communication ---------------------------------------------------
    "thunderbird": AppEntry("Thunderbird", "comms", "\U0001f4e7", ["thunderbird"]),
    "outlook": AppEntry("Outlook", "comms", "\U0001f4e7",
                         ["outlook", "C:\\Program Files\\Microsoft Office\\root\\Office16\\OUTLOOK.EXE"]),
    "discord": AppEntry("Discord", "comms", "\U0001f3ae", ["discord", "discord-canary"]),
    "slack": AppEntry("Slack", "comms", "\U0001f4ac", ["slack"]),
    "telegram": AppEntry("Telegram", "comms", "\u2708", ["telegram-desktop", "telegram"]),
    "whatsapp": AppEntry("WhatsApp", "comms", "\U0001f4f1", ["whatsapp-for-linux", "whatsapp"]),
    "zoom": AppEntry("Zoom", "comms", "\U0001f4f9", ["zoom"]),
    "teams": AppEntry("Microsoft Teams", "comms", "\U0001f4f9", ["teams"]),
    "signal": AppEntry("Signal", "comms", "\U0001f512", ["signal-desktop"]),

    # ---- Browsers ----------------------------------------------------
    "firefox": AppEntry("Firefox", "browser", "\U0001f98a", ["firefox"]),
    "chromium": AppEntry("Chromium / Chrome", "browser", "\U0001f310",
                          ["google-chrome", "chromium", "chromium-browser", "chrome"]),
    "brave": AppEntry("Brave", "browser", "\U0001f981", ["brave-browser", "brave"]),
    "edge": AppEntry("Microsoft Edge", "browser", "\U0001f310", ["msedge", "microsoft-edge"]),
    "opera": AppEntry("Opera", "browser", "\U0001f310", ["opera"]),

    # ---- System & Utilities ----------------------------------------------
    "virtualbox": AppEntry("VirtualBox", "system", "\U0001f5a5", ["virtualbox"]),
    "settings": AppEntry("System Settings", "system", "\u2699",
                          ["gnome-control-center", "systemsettings", "ms-settings:"]),
    "taskmanager": AppEntry("Task Manager", "system", "\U0001f4ca", ["gnome-system-monitor", "ksysguard", "taskmgr"]),
    "screenshot": AppEntry("Screenshot Tool", "system", "\U0001f4f7", ["gnome-screenshot", "spectacle", "flameshot"]),

    # ---- Science & Math ---------------------------------------------------
    "geogebra": AppEntry("GeoGebra", "science", "\U0001f4d0", ["geogebra"]),
}


def app_labels():
    return {k: v.label for k, v in APPS.items()}


def app_launchers():
    return {k: v.launchers for k, v in APPS.items()}


def app_categories():
    return {k: v.category for k, v in APPS.items()}


def app_icon(app_id):
    entry = APPS.get(app_id)
    return entry.icon if entry else "\u2699"


# Spoken aliases -> app id. Longest-phrase-first matching is applied by the caller.
APP_ALIASES = {
    # code
    "vs code": "vscode", "visual studio code": "vscode", "vscode": "vscode", "code editor": "vscode",
    "sublime text": "sublimetext", "sublime": "sublimetext",
    "atom editor": "atom", "atom": "atom",
    "vim": "vim", "vi editor": "vim",
    "neovim": "neovim", "n vim": "neovim",
    "emacs": "emacs",
    "jupyter": "jupyter", "jupyter notebook": "jupyter", "jupyter lab": "jupyter",
    "spyder": "spyder", "python ide": "spyder",
    "pycharm": "pycharm", "py charm": "pycharm",
    "intellij": "intellij", "intellij idea": "intellij",
    "android studio": "androidstudio",
    "docker": "docker", "docker desktop": "docker",
    "postman": "postman",
    "github desktop": "github_desktop", "git hub desktop": "github_desktop",
    "gitkraken": "gitkraken", "git kraken": "gitkraken",
    "arduino ide": "arduino", "arduino": "arduino",
    "platformio": "platformio", "platform io": "platformio",
    "wireshark": "wireshark", "packet sniffer": "wireshark",
    "terminal": "terminal", "command line": "terminal", "console": "terminal",
    "windows terminal": "windowsterminal",

    # design & media
    "gimp": "gimp", "image editor": "gimp",
    "inkscape": "inkscape", "vector editor": "inkscape",
    "blender": "blender", "3d modeling": "blender",
    "krita": "krita",
    "figma": "figma",
    "audacity": "audacity", "audio editor": "audacity",
    "obs": "obs", "obs studio": "obs", "screen recorder": "obs",
    "davinci resolve": "davinciresolve", "resolve": "davinciresolve", "video editor": "davinciresolve",
    "vlc": "vlc", "media player": "vlc", "video player": "vlc",
    "spotify": "spotify", "music player": "spotify",

    # office & notes
    "obsidian": "obsidian", "obsidian notes": "obsidian", "note taking app": "obsidian", "obsidean": "obsidian",
    "notion": "notion",
    "koodo reader": "koodoreader", "koodoreader": "koodoreader", "e book reader": "koodoreader", "ebook reader": "koodoreader",
    "anki": "anki", "flashcards": "anki", "flash cards": "anki",
    "zathura": "zathura", "pdf viewer": "zathura",
    "okular": "okular",
    "xournal": "xournalpp", "xournal plus plus": "xournalpp", "xournal++": "xournalpp", "pdf annotator": "xournalpp",
    "texstudio": "texstudio", "latex editor": "texstudio", "tex studio": "texstudio",
    "overleaf": "overleaf", "over leaf": "overleaf",
    "libreoffice writer": "libreoffice_writer", "word processor": "libreoffice_writer",
    "libreoffice calc": "libreoffice_calc", "spreadsheet": "libreoffice_calc",
    "libreoffice impress": "libreoffice_impress", "presentation software": "libreoffice_impress",
    "microsoft word": "word", "word": "word",
    "microsoft excel": "excel", "excel": "excel",
    "microsoft powerpoint": "powerpoint", "powerpoint": "powerpoint",
    "one note": "onenote", "onenote": "onenote",
    "calculator": "calculator",
    "file manager": "files", "files": "files", "file explorer": "files",

    # engineering & eda
    "kicad": "kicad", "kai cad": "kicad", "pcb designer": "kicad", "schematic editor": "kicad", "pcb design tool": "kicad",
    "ltspice": "ltspice", "l t spice": "ltspice", "spice simulator": "ltspice",
    "ngspice": "ngspice", "ng spice": "ngspice",
    "gtkwave": "gtkwave", "gtk wave": "gtkwave", "waveform viewer": "gtkwave",
    "freecad": "freecad", "free cad": "freecad",
    "fritzing": "fritzing",
    "qucs": "qucs", "qucs s": "qucs", "circuit simulator": "qucs",
    "gnuradio": "gnuradio", "gnu radio": "gnuradio", "gnu radio companion": "gnuradio",
    "solidworks": "solidworks", "solid works": "solidworks",
    "autocad": "autocad", "auto cad": "autocad",
    "matlab": "matlab",
    "octave": "octave", "gnu octave": "octave",

    # communication
    "thunderbird": "thunderbird", "email client": "thunderbird", "mail app": "thunderbird",
    "outlook": "outlook",
    "discord": "discord",
    "slack": "slack",
    "telegram": "telegram",
    "whatsapp": "whatsapp", "whats app": "whatsapp",
    "zoom": "zoom",
    "microsoft teams": "teams", "teams": "teams",
    "signal": "signal",

    # browsers
    "firefox": "firefox", "web browser": "firefox",
    "chrome": "chromium", "google chrome": "chromium", "chromium": "chromium",
    "brave": "brave", "brave browser": "brave",
    "edge": "edge", "microsoft edge": "edge",
    "opera": "opera",

    # system
    "virtualbox": "virtualbox", "virtual box": "virtualbox",
    "settings": "settings", "system settings": "settings", "control panel": "settings",
    "task manager": "taskmanager", "system monitor": "taskmanager",
    "screenshot tool": "screenshot", "take a screenshot": "screenshot",

    # science
    "geo gebra": "geogebra", "geogebra": "geogebra",
}