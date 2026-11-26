"""Read/write MacroMaster .CKD project files (INI, CRLF, latin-1).

The file is kept as an ordered list of sections/keys so that load -> save is
byte-identical for files written by MacroMaster, and unknown keys survive.
The typed :class:`Layout` view is built on top of that.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path

GLOBAL = "GLOBAL_PARAMETERS"
ENCODING = "latin-1"


class MacroMode(IntEnum):
    AUTO = 0          # MacroMaster "Auto-Sense"
    SEPARATE_UP = 1   # chording, held while key held
    MACRO = 2         # regular typing
    LITERAL = 3       # you supply every make and break
    FAST_UP = 4       # chording, all keys at once


class KeyType(IntEnum):
    NORMAL = 0
    LEVEL_SHIFT = 1
    LEVEL_TOGGLE = 2


class LedFunction(IntEnum):
    # Value = item index in MacroMaster's Properties panel combo box.
    NOT_USED = 0
    CAPS_LOCK = 1
    NUM_LOCK = 2
    LEVEL_INDICATOR = 3
    HOST_MACRO_CONTROL = 4
    POWER_INDICATOR = 5
    SCROLL_LOCK = 6


class UsbDeviceType(IntEnum):
    # Radio-button Tag values in MacroMaster's Properties panel.
    BASIC_KEYBOARD = 3
    MULTIMEDIA_KEYBOARD = 11
    MULTIMEDIA_KEYBOARD_MOUSE = 12


MODEL_KEYS = {"CP24": 24, "CP48": 48}


# --------------------------------------------------------------------------- ordered INI

@dataclass
class IniFile:
    sections: list[tuple[str, list[tuple[str, str]]]] = field(default_factory=list)
    newline: str = "\r\n"
    trailing_newline: bool = True

    @classmethod
    def parse(cls, text: str) -> "IniFile":
        newline = "\r\n" if "\r\n" in text else "\n"
        ini = cls(newline=newline, trailing_newline=text.endswith(("\n", "\r")))
        current: list[tuple[str, str]] | None = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current = []
                ini.sections.append((line[1:-1], current))
                continue
            if current is None or "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            current.append((k.strip(), v.strip()))
        return ini

    def render(self) -> str:
        lines: list[str] = []
        for name, items in self.sections:
            lines.append(f"[{name}]")
            lines.extend(f"{k}={v}" for k, v in items)
        out = self.newline.join(lines)
        return out + self.newline if self.trailing_newline else out

    def section(self, name: str, create: bool = False) -> list[tuple[str, str]] | None:
        for n, items in self.sections:
            if n.lower() == name.lower():
                return items
        if create:
            items: list[tuple[str, str]] = []
            self.sections.append((name, items))
            return items
        return None

    def get(self, sect: str, key: str, default: str | None = None) -> str | None:
        items = self.section(sect)
        if items:
            for k, v in items:
                if k.lower() == key.lower():
                    return v
        return default

    def set(self, sect: str, key: str, value: str) -> None:
        items = self.section(sect, create=True)
        assert items is not None
        for i, (k, _) in enumerate(items):
            if k.lower() == key.lower():
                items[i] = (k, value)
                return
        items.append((key, value))


# --------------------------------------------------------------------------- typed model

@dataclass
class Level:
    codes: bytes = b""
    name: str = ""
    auto_repeat: bool = False
    mode: MacroMode = MacroMode.AUTO


@dataclass
class Key:
    index: int
    key_type: KeyType = KeyType.NORMAL
    l1: Level = field(default_factory=Level)
    l2: Level = field(default_factory=Level)

    def level(self, n: int) -> Level:
        return self.l1 if n == 1 else self.l2


@dataclass
class Globals:
    model: str = "CP48"
    num_keys: int = 48
    key_rollover: int = 2
    led1: int = 1
    led2: int = 2
    led3: int = 4
    char_pacing: int = 4
    usb_device_type: int | None = None   # None = key absent from file


def _int(v: str | None, default: int) -> int:
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        return default


@dataclass
class Layout:
    globals: Globals
    keys: list[Key]
    ini: IniFile = field(default_factory=IniFile, repr=False)
    path: Path | None = None

    # ---- load ---------------------------------------------------------------
    @classmethod
    def from_text(cls, text: str, path: Path | None = None) -> "Layout":
        from .macro import hex_to_bytes

        ini = IniFile.parse(text)
        model = ini.get(GLOBAL, "Model_Number", "CP48") or "CP48"
        num = _int(ini.get(GLOBAL, "Number_Of_Keys"), MODEL_KEYS.get(model, 48))
        usb = ini.get(GLOBAL, "USB_Device_Type")
        g = Globals(
            model=model,
            num_keys=num,
            # Defaults are the ones MacroMasterCPxx / CPxxLoad use when a key is missing.
            key_rollover=_int(ini.get(GLOBAL, "Key_Roll_Over"), 2),
            led1=_int(ini.get(GLOBAL, "LED_Function"), 1),
            led2=_int(ini.get(GLOBAL, "LED2_Function"), 2),
            led3=_int(ini.get(GLOBAL, "LED3_Function"), 4),
            char_pacing=_int(ini.get(GLOBAL, "Character_Pacing"), 4),
            usb_device_type=None if usb in (None, "") else _int(usb, 0),
        )
        keys = []
        for i in range(num):
            s = f"KEY{i}"
            k = Key(i, KeyType(_int(ini.get(s, "KeyType"), 0)))
            for n, lv in ((1, k.l1), (2, k.l2)):
                lv.codes = hex_to_bytes(ini.get(s, f"Level_{n}_Codes", "") or "")
                lv.name = ini.get(s, f"Level_{n}_Name", "") or ""
                lv.auto_repeat = _int(ini.get(s, f"L{n}_AutoRepeat"), 0) != 0
                lv.mode = MacroMode(_int(ini.get(s, f"L{n}_MacroMode"), 0))
            keys.append(k)
        return cls(g, keys, ini, path)

    @classmethod
    def load(cls, path: str | Path) -> "Layout":
        p = Path(path)
        return cls.from_text(p.read_bytes().decode(ENCODING), p)

    @classmethod
    def new(cls, model: str = "CP48") -> "Layout":
        n = MODEL_KEYS[model]
        g = Globals(model=model, num_keys=n)
        lay = cls(g, [Key(i) for i in range(n)], IniFile())
        lay._sync_ini()
        return lay

    # ---- save ---------------------------------------------------------------
    def _sync_ini(self) -> None:
        """Push the typed model back into the ordered INI, keeping key order."""
        ini, g = self.ini, self.globals
        ini.set(GLOBAL, "Model_Number", g.model)
        ini.set(GLOBAL, "Number_Of_Keys", str(g.num_keys))
        ini.set(GLOBAL, "Key_Roll_Over", str(g.key_rollover))
        ini.set(GLOBAL, "LED_Function", str(g.led1))
        ini.set(GLOBAL, "LED2_Function", str(g.led2))
        ini.set(GLOBAL, "LED3_Function", str(g.led3))
        ini.set(GLOBAL, "Character_Pacing", str(g.char_pacing))
        if g.usb_device_type is not None:
            ini.set(GLOBAL, "USB_Device_Type", str(g.usb_device_type))
        for k in self.keys:
            s = f"KEY{k.index}"
            ini.set(s, "KeyType", str(int(k.key_type)))
            ini.set(s, "L1_AutoRepeat", str(int(k.l1.auto_repeat)))
            ini.set(s, "L2_AutoRepeat", str(int(k.l2.auto_repeat)))
            ini.set(s, "L1_MacroMode", str(int(k.l1.mode)))
            ini.set(s, "L2_MacroMode", str(int(k.l2.mode)))
            ini.set(s, "Level_1_Codes", k.l1.codes.hex())
            ini.set(s, "Level_2_Codes", k.l2.codes.hex())
            ini.set(s, "Level_1_Name", k.l1.name)
            ini.set(s, "Level_2_Name", k.l2.name)

    def to_text(self) -> str:
        self._sync_ini()
        return self.ini.render()

    def save(self, path: str | Path | None = None) -> Path:
        p = Path(path) if path else self.path
        if p is None:
            raise ValueError("no path to save to")
        data = self.to_text().encode(ENCODING)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)          # atomic on the same volume; never leaves a half-written CKD
        self.path = p
        return p
