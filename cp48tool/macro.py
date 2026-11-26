"""Convert between CKD code strings (hex) and a readable macro text syntax.

CKD stores macros as lowercase hex, e.g. ``141142f011f014`` (Ctrl+Alt+K).

Text syntax (whitespace separated tokens)::

    Ctrl+Alt+K        chord: modifiers down, key, modifiers up (reverse order)
    K                 a single key make code (MacroMaster "tap")
    +LShift / -LShift explicit press / release of any key
    delay(200)        pause in ms (4 ms resolution, 4..1020)
    LED1On            Genovation custom command (see scancodes.CUSTOM)
    MouseX+(10)       mouse move / wheel with magnitude 1..255
    <e0 6b>           raw bytes, inserted verbatim

Chord shorthand modifier names: Ctrl, Shift, Alt, Win (left side) or the
explicit LCtrl/RCtrl/... names.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import scancodes as sc

E0, F0, E2 = 0xE0, 0xF0, 0xE2


class MacroError(ValueError):
    pass


# --------------------------------------------------------------------------- events

@dataclass(frozen=True)
class Event:
    kind: str            # 'make' | 'break' | 'delay' | 'custom' | 'mouse' | 'raw'
    ext: bool = False    # E0-prefixed key
    code: int = 0
    value: int = 0       # delay units / mouse magnitude

    def to_bytes(self) -> bytes:
        if self.kind == "make":
            return bytes([E0, self.code]) if self.ext else bytes([self.code])
        if self.kind == "break":
            return bytes([E0, F0, self.code]) if self.ext else bytes([F0, self.code])
        if self.kind == "delay":
            return bytes([E2, sc.DELAY_CMD, self.value])
        if self.kind == "custom":
            return bytes([E2, self.code])
        if self.kind == "mouse":
            return bytes([self.code, self.value])
        if self.kind == "raw":
            return bytes([self.code])
        raise AssertionError(self.kind)

    @property
    def key_name(self) -> str:
        n = sc.ext_name(self.code) if self.ext else sc.std_name(self.code)
        return n or (f"<e0 {self.code:02x}>" if self.ext else f"<{self.code:02x}>")


def parse_codes(data: bytes) -> list[Event]:
    """Tokenise a raw code stream (CKD semantics, F0 = break) into events."""
    ev: list[Event] = []
    i, n = 0, len(data)
    while i < n:
        b = data[i]
        if b == E0 and i + 1 < n:
            if data[i + 1] == F0 and i + 2 < n:
                ev.append(Event("break", True, data[i + 2])); i += 3; continue
            ev.append(Event("make", True, data[i + 1])); i += 2; continue
        if b == F0 and i + 1 < n:
            ev.append(Event("break", False, data[i + 1])); i += 2; continue
        if b == E2 and i + 1 < n:
            if data[i + 1] == sc.DELAY_CMD and i + 2 < n:
                ev.append(Event("delay", value=data[i + 2])); i += 3; continue
            ev.append(Event("custom", code=data[i + 1])); i += 2; continue
        if sc.mouse_name(b) and i + 1 < n:
            ev.append(Event("mouse", code=b, value=data[i + 1])); i += 2; continue
        if sc.std_name(b):
            ev.append(Event("make", False, b)); i += 1; continue
        ev.append(Event("raw", code=b)); i += 1
    return ev


def events_to_bytes(events: list[Event]) -> bytes:
    return b"".join(e.to_bytes() for e in events)


# --------------------------------------------------------------------------- hex <-> bytes

def hex_to_bytes(codes: str) -> bytes:
    s = codes.strip().replace(" ", "").lower()
    if len(s) % 2:
        raise MacroError(f"odd-length code string: {codes!r}")
    try:
        return bytes.fromhex(s)
    except ValueError as exc:
        raise MacroError(f"invalid hex in code string: {codes!r}") from exc


def bytes_to_hex(data: bytes) -> str:
    return data.hex()


# --------------------------------------------------------------------------- text rendering

_CHORD_MOD_DISPLAY = {"LCtrl": "Ctrl", "LShift": "Shift", "LAlt": "Alt", "LWin": "Win"}


def _is_modifier(e: Event) -> bool:
    return e.kind in ("make", "break") and e.key_name in sc.MODIFIERS


def _token(e: Event) -> str:
    if e.kind == "make":
        return e.key_name
    if e.kind == "break":
        return "-" + e.key_name
    if e.kind == "delay":
        return f"delay({e.value * 4})"
    if e.kind == "custom":
        return sc.custom_name(e.code) or f"<e2 {e.code:02x}>"
    if e.kind == "mouse":
        return f"{sc.mouse_name(e.code)}({e.value})"
    return f"<{e.code:02x}>"


def to_text(data: bytes) -> str:
    """Render a code stream as macro text, folding chords where possible."""
    ev = parse_codes(data)
    out: list[str] = []
    i = 0
    while i < len(ev):
        # chord: m1..mk make, one non-modifier make, mk..m1 break
        j = i
        while j < len(ev) and ev[j].kind == "make" and _is_modifier(ev[j]):
            j += 1
        k = j - i
        if k and j < len(ev) and ev[j].kind == "make" and not _is_modifier(ev[j]):
            tail = ev[j + 1 : j + 1 + k]
            mods = ev[i:j]
            if len(tail) == k and all(
                t.kind == "break" and t.ext == m.ext and t.code == m.code
                for t, m in zip(tail, reversed(mods))
            ):
                names = [_CHORD_MOD_DISPLAY.get(m.key_name, m.key_name) for m in mods]
                out.append("+".join(names + [ev[j].key_name]))
                i = j + 1 + k
                continue
        e = ev[i]
        out.append(("+" + e.key_name) if (e.kind == "make" and _is_modifier(e)) else _token(e))
        i += 1
    return " ".join(out)


# --------------------------------------------------------------------------- text parsing

_FUNC_RE = re.compile(r"^(?P<name>[A-Za-z0-9+\-]+)\((?P<arg>\d+)\)$")


def _key_event(name: str, kind: str) -> Event:
    hit = sc.lookup(name)
    if hit is None or hit[0] not in ("std", "ext"):
        raise MacroError(f"unknown key name: {name!r}")
    return Event(kind, hit[0] == "ext", hit[1])


def _parse_token(tok: str) -> list[Event]:
    if tok.startswith("<") and tok.endswith(">"):
        try:
            return [Event("raw", code=b) for b in bytes.fromhex(tok[1:-1])]
        except ValueError as exc:
            raise MacroError(f"bad raw bytes: {tok!r}") from exc

    m = _FUNC_RE.match(tok)
    if m:
        name, arg = m.group("name"), int(m.group("arg"))
        if name.lower() == "delay":
            if not 4 <= arg <= 1020:
                raise MacroError(f"delay must be 4..1020 ms, got {arg}")
            return [Event("delay", value=round(arg / 4))]
        hit = sc.lookup(name)
        if hit and hit[0] == "mouse":
            if not 1 <= arg <= 255:
                raise MacroError(f"mouse magnitude must be 1..255, got {arg}")
            return [Event("mouse", code=hit[1], value=arg)]
        raise MacroError(f"unknown function: {tok!r}")

    hit = sc.lookup(tok)
    if hit is not None:
        kind, code = hit
        if kind == "custom":
            return [Event("custom", code=code)]
        if kind == "mouse":
            raise MacroError(f"{tok} needs a magnitude, e.g. {tok}(10)")
        return [Event("make", kind == "ext", code)]

    if len(tok) > 1 and tok[0] in "+-" and sc.lookup(tok[1:]):
        return [_key_event(tok[1:], "make" if tok[0] == "+" else "break")]

    if "+" in tok.strip("+"):
        parts = tok.split("+")
        if all(parts):
            mods = [_key_event(p, "make") for p in parts[:-1]]
            key = _key_event(parts[-1], "make")
            for p, e in zip(parts[:-1], mods):
                if e.key_name not in sc.MODIFIERS:
                    raise MacroError(f"{p!r} in {tok!r} is not a modifier")
            breaks = [Event("break", e.ext, e.code) for e in reversed(mods)]
            return [*mods, key, *breaks]

    raise MacroError(f"cannot parse token: {tok!r}")


_TOKEN_RE = re.compile(r"<[^>]*>|\S+")


def from_text(text: str) -> bytes:
    events: list[Event] = []
    for tok in _TOKEN_RE.findall(text):
        events.extend(_parse_token(tok))
    return events_to_bytes(events)
