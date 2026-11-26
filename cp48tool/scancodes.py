"""PS/2 scan-code set 2 tables as used by Genovation MacroMaster (CKD files).

A CKD macro is a flat byte stream:

* ``xx``            make code of a standard key
* ``E0 xx``         make code of an extended key (arrows, R-Ctrl, media keys, mouse buttons)
* ``F0 xx``         break (release) of ``xx``; for extended keys it is ``E0 F0 xx``
* ``E2 01 tt``      delay of ``tt`` * 4 ms (MacroMaster slider: 4..500 ms)
* ``E2 nn``         Genovation custom commands (LEDs, backlight)
* ``90``..``95 vv`` mouse moves / wheel with a 1-byte magnitude

Source: MacroMasterCPxx.pdf, "Appendix A: Scan Code Table".
"""

from __future__ import annotations

# name -> make code (non-extended)
STANDARD: dict[str, int] = {
    "F9": 0x01, "F5": 0x03, "F3": 0x04, "F1": 0x05, "F2": 0x06, "F12": 0x07,
    "F13": 0x08, "F10": 0x09, "F8": 0x0A, "F6": 0x0B, "F4": 0x0C, "Tab": 0x0D,
    "`": 0x0E, "KP=": 0x0F, "F14": 0x10, "LAlt": 0x11, "LShift": 0x12,
    "Intl2a": 0x13, "LCtrl": 0x14, "Q": 0x15, "1": 0x16, "F15": 0x18, "Z": 0x1A,
    "S": 0x1B, "A": 0x1C, "W": 0x1D, "2": 0x1E, "F16": 0x20, "C": 0x21, "X": 0x22,
    "D": 0x23, "E": 0x24, "4": 0x25, "3": 0x26, "Intl6": 0x27, "F17": 0x28,
    "Space": 0x29, "V": 0x2A, "F": 0x2B, "T": 0x2C, "R": 0x2D, "5": 0x2E,
    "F13old": 0x2F, "F18": 0x30, "N": 0x31, "B": 0x32, "H": 0x33, "G": 0x34,
    "Y": 0x35, "6": 0x36, "F14old": 0x37, "F19": 0x38, "M": 0x3A, "J": 0x3B,
    "U": 0x3C, "7": 0x3D, "8": 0x3E, "F15old": 0x3F, "F20": 0x40, ",": 0x41,
    "K": 0x42, "I": 0x43, "O": 0x44, "0": 0x45, "9": 0x46, "F21": 0x48, ".": 0x49,
    "/": 0x4A, "L": 0x4B, ";": 0x4C, "P": 0x4D, "-": 0x4E, "F22": 0x50,
    "Intl1": 0x51, "'": 0x52, "[": 0x54, "=": 0x55, "F23": 0x57, "CapsLock": 0x58,
    "RShift": 0x59, "Enter": 0x5A, "]": 0x5B, "\\": 0x5D, "F24": 0x5F,
    "Europe2": 0x61, "Lang4": 0x62, "Lang3": 0x63, "Intl4": 0x64,
    "Backspace": 0x66, "Intl5": 0x67, "KP1": 0x69, "Intl2b": 0x6A, "KP4": 0x6B,
    "KP7": 0x6C, "KP,": 0x6D, "KP0": 0x70, "KP.": 0x71, "KP2": 0x72, "KP5": 0x73,
    "KP6": 0x74, "KP8": 0x75, "Esc": 0x76, "NumLock": 0x77, "F11": 0x78,
    "KP+": 0x79, "KP3": 0x7A, "KP-": 0x7B, "KP*": 0x7C, "KP9": 0x7D,
    "ScrollLock": 0x7E, "F7": 0x83, "Pause": 0x85, "PrintScreen": 0x86,
}

# name -> second byte after E0
EXTENDED: dict[str, int] = {
    "RAlt": 0x11, "RCtrl": 0x14, "LWin": 0x1F, "RWin": 0x27, "App": 0x2F,
    "Power": 0x37, "KP/": 0x4A, "KPEnter": 0x5A, "Wake": 0x5E,
    "MouseLeft": 0x61, "MouseRight": 0x62, "MouseMiddle": 0x63,
    "MouseBack": 0x64, "MouseForward": 0x65,
    "End": 0x69, "Left": 0x6B, "Home": 0x6C, "Insert": 0x70, "Delete": 0x71,
    "Down": 0x72, "Right": 0x74, "Up": 0x75, "PageDown": 0x7A, "PageUp": 0x7D,
    # consumer / multimedia
    "WebSearch": 0x10, "PrevTrack": 0x15, "WebFavorites": 0x18, "Eject": 0x1A,
    "WebRefresh": 0x20, "VolumeDown": 0x21, "Mute": 0x23, "WebStop": 0x28,
    "Calculator": 0x2B, "WebForward": 0x30, "VolumeUp": 0x32, "PlayPause": 0x34,
    "WebBack": 0x38, "WebHome": 0x3A, "Stop": 0x3B, "MyComputer": 0x40,
    "BrightnessUp": 0x41, "BrightnessDown": 0x42, "Mail": 0x48,
    "NextTrack": 0x4D, "MediaSelect": 0x50,
}

# Genovation one-byte commands following E2 (Delay is E2 01 tt and handled separately)
CUSTOM: dict[str, int] = {
    "LED1Off": 0x04, "LED1On": 0x05, "LED1Flash": 0x06, "LED1Toggle": 0x07, "LED1ToggleFlash": 0x08,
    "LED2Off": 0x14, "LED2On": 0x15, "LED2Flash": 0x16, "LED2Toggle": 0x17, "LED2ToggleFlash": 0x18,
    "LED3Off": 0x24, "LED3On": 0x25, "LED3Flash": 0x26, "LED3Toggle": 0x27, "LED3ToggleFlash": 0x28,
    **{f"Backlight{i}": 0x30 + i for i in range(7)},
    "BacklightMute": 0x37, "BacklightUnmute": 0x38, "BacklightToggle": 0x39,
    "BacklightUp": 0x3A, "BacklightDown": 0x3B, "BacklightFlashOn": 0x3C, "BacklightFlashOff": 0x3D,
}
DELAY_CMD = 0x01

# Mouse moves: single byte opcode followed by a magnitude byte (no break code)
MOUSE_MOVE: dict[str, int] = {
    "MouseX+": 0x90, "MouseX-": 0x91, "MouseY+": 0x92, "MouseY-": 0x93,
    "Wheel+": 0x94, "Wheel-": 0x95,
}

MODIFIERS = {"LAlt", "LShift", "LCtrl", "RAlt", "RCtrl", "LWin", "RWin", "RShift"}

# Friendly aliases accepted by the parser (case-insensitive lookup)
ALIASES: dict[str, str] = {
    "ctrl": "LCtrl", "control": "LCtrl", "shift": "LShift", "alt": "LAlt",
    "win": "LWin", "meta": "LWin", "cmd": "LWin", "super": "LWin",
    "escape": "Esc", "return": "Enter", "del": "Delete", "ins": "Insert",
    "pgup": "PageUp", "pgdn": "PageDown", "bksp": "Backspace", "bs": "Backspace",
    "comma": ",", "period": ".", "dot": ".", "slash": "/", "backslash": "\\",
    "semicolon": ";", "quote": "'", "apostrophe": "'", "minus": "-", "equals": "=",
    "lbracket": "[", "rbracket": "]", "grave": "`", "backtick": "`", "tilde": "`",
    "spacebar": "Space", "caps": "CapsLock", "prtsc": "PrintScreen",
}

_STD_BY_CODE = {v: k for k, v in STANDARD.items()}
_EXT_BY_CODE: dict[int, str] = {}
for _k, _v in EXTENDED.items():
    _EXT_BY_CODE.setdefault(_v, _k)  # first name wins (E0 3B = Stop / Eject alias)
_CUSTOM_BY_CODE = {v: k for k, v in CUSTOM.items()}
_MOUSE_BY_CODE = {v: k for k, v in MOUSE_MOVE.items()}

_LOOKUP: dict[str, tuple[str, int]] = {}
for _k, _v in STANDARD.items():
    _LOOKUP[_k.lower()] = ("std", _v)
for _k, _v in EXTENDED.items():
    _LOOKUP[_k.lower()] = ("ext", _v)
for _k, _v in CUSTOM.items():
    _LOOKUP[_k.lower()] = ("custom", _v)
for _k, _v in MOUSE_MOVE.items():
    _LOOKUP[_k.lower()] = ("mouse", _v)
for _a, _k in ALIASES.items():
    _LOOKUP.setdefault(_a, _LOOKUP[_k.lower()])


def lookup(name: str) -> tuple[str, int] | None:
    """Resolve a key name (case-insensitive, aliases allowed) to (kind, code)."""
    return _LOOKUP.get(name.strip().lower())


def canonical_name(name: str) -> str | None:
    hit = lookup(name)
    if hit is None:
        return None
    kind, code = hit
    return {"std": _STD_BY_CODE, "ext": _EXT_BY_CODE,
            "custom": _CUSTOM_BY_CODE, "mouse": _MOUSE_BY_CODE}[kind][code]


def std_name(code: int) -> str | None:
    return _STD_BY_CODE.get(code)


def ext_name(code: int) -> str | None:
    return _EXT_BY_CODE.get(code)


def custom_name(code: int) -> str | None:
    return _CUSTOM_BY_CODE.get(code)


def mouse_name(code: int) -> str | None:
    return _MOUSE_BY_CODE.get(code)
