"""Compile a :class:`~cp48tool.ckd.Layout` to the keypad's .BIN image, and decode .BIN files.

Format (recovered from CPxxLoad.exe / MacroMasterCPxx.exe, and checked byte for byte
against .BIN files MacroMaster wrote)::

    header  E4 01 0C  E0 70  T1 T2 S1 S2  KRO USB PACE LED1 LED2 LED3
              T1,T2 = indexes of level-toggle keys, S1,S2 = level-shift keys (0x80 = none)
              E0/70 = per-level capacity in bytes (224 single level / 112 for level 2)
    per key E4 02 kk  F2 F1 kk  L1 <L1 bytes>  L2 <L2 bytes>
              F1/F2  level-1 / level-2 flags:
                     0x01 has data, 0x02 auto-repeat,
                     mode bits 0x00 macro, 0x08 separate-up, 0x04 literal, 0x0C fast-up
              Ln     data length incl. trailing 00 (0 = empty level)
              data   CKD codes with every F0 (break prefix) rewritten as E3, then 00
    trailer E5
"""

from __future__ import annotations

from dataclasses import dataclass

from .ckd import Key, KeyType, Layout, Level, MacroMode

REC_HDR, REC_KEY, END = 0xE4, 0xE5, 0xE5
BREAK_CKD, BREAK_BIN = 0xF0, 0xE3
NO_KEY = 0x80
L1_MAX, L2_MAX = 0xE0, 0x70          # 224 / 112 bytes (manual: "220 / 110")

F_DATA, F_REPEAT = 0x01, 0x02
MODE_BITS = {
    MacroMode.AUTO: 0x00,       # resolved below
    MacroMode.SEPARATE_UP: 0x08,
    MacroMode.MACRO: 0x00,
    MacroMode.LITERAL: 0x04,
    MacroMode.FAST_UP: 0x0C,
}

# Auto-sense special cases: a macro consisting only of a modifier tap is stored as the
# bare make code in separate-up mode (so the keypad holds the modifier like a real key).
SPECIAL = {
    bytes.fromhex(k): bytes.fromhex(v)
    for k, v in {
        "12f012": "12", "14f014": "14", "e01fe0f01f": "e01f", "11f011": "11",
        "e011e0f011": "e011", "e027e0f027": "e027", "e014e0f014": "e014",
        "59f059": "59", "e011": "e011", "e014": "e014", "e01f": "e01f", "e027": "e027",
    }.items()
}


class CompileError(ValueError):
    pass


def _encode_codes(codes: bytes, limit: int, where: str) -> bytes:
    out = bytearray()
    for b in codes:
        if b == 0x00:
            break  # the original parser stops at the first 00
        if b == BREAK_CKD:
            b = BREAK_BIN
        elif b > 0xE4:
            raise CompileError(f"{where}: invalid code {b:02X} (codes above E4 are reserved)")
        out.append(b)
    if len(out) >= limit:
        raise CompileError(f"{where}: macro is {len(out)} bytes, limit is {limit - 1}")
    return bytes(out)


def _level(lv: Level, limit: int, where: str) -> tuple[int, bytes]:
    flags = MODE_BITS[lv.mode] | (F_REPEAT if lv.auto_repeat else 0)
    if not lv.codes:
        return flags, b""
    flags |= F_DATA
    if lv.mode == MacroMode.AUTO:
        special = SPECIAL.get(lv.codes)
        if special is not None:
            return flags | 0x08, special
        data = _encode_codes(lv.codes, limit, where)
        if len(data) == 1:
            flags |= 0x08         # single key -> separate up codes
        return flags, data
    return flags, _encode_codes(lv.codes, limit, where)


@dataclass
class CompileOptions:
    # MacroMaster versions that wrote the existing (known good) .BIN files left the USB
    # device type byte at 00 when the CKD had no USB_Device_Type entry. Newer versions
    # default it to 0x0B. Keep 00 unless the CKD says otherwise.
    default_usb_device_type: int = 0x00


def compile_layout(layout: Layout, opts: CompileOptions | None = None) -> bytes:
    opts = opts or CompileOptions()
    g = layout.globals
    toggles: list[int] = []
    shifts: list[int] = []
    for k in layout.keys:
        if k.key_type == KeyType.LEVEL_TOGGLE:
            toggles.append(k.index)
        elif k.key_type == KeyType.LEVEL_SHIFT:
            shifts.append(k.index)
    if len(toggles) > 2 or len(shifts) > 2:
        raise CompileError("at most two level-shift and two level-toggle keys are allowed")
    t = (toggles + [NO_KEY, NO_KEY])[:2]
    s = (shifts + [NO_KEY, NO_KEY])[:2]
    usb = g.usb_device_type if g.usb_device_type is not None else opts.default_usb_device_type
    for name, v in (("Key_Roll_Over", g.key_rollover), ("Character_Pacing", g.char_pacing),
                    ("LED_Function", g.led1), ("LED2_Function", g.led2),
                    ("LED3_Function", g.led3), ("USB_Device_Type", usb)):
        if not 0 <= v <= 0xFF:
            raise CompileError(f"{name}={v} out of range")

    out = bytearray([REC_HDR, 0x01, 0x0C, L1_MAX, L2_MAX, *t, *s,
                     g.key_rollover, usb, g.char_pacing, g.led1, g.led2, g.led3])
    for k in layout.keys:
        out += _key_record(k)
    out.append(END)
    return bytes(out)


def _key_record(k: Key) -> bytes:
    l1_limit = L1_MAX if not k.l2.codes else L2_MAX
    f1, d1 = _level(k.l1, l1_limit, f"KEY{k.index} level 1")
    f2, d2 = _level(k.l2, L2_MAX, f"KEY{k.index} level 2")
    rec = bytearray([REC_HDR, 0x02, k.index, f2, f1, k.index])
    rec += bytes([len(d1) + 1]) + d1 + b"\x00" if d1 else b"\x00"
    rec += bytes([len(d2) + 1]) + d2 + b"\x00" if d2 else b"\x00"
    return bytes(rec)


# --------------------------------------------------------------------------- decode

@dataclass
class DecodedLevel:
    flags: int
    codes: bytes           # converted back to CKD form (E3 -> F0)

    @property
    def mode(self) -> str:
        if not self.flags & F_DATA:
            return "-"
        return {0x00: "macro", 0x08: "separate-up", 0x04: "literal", 0x0C: "fast-up"}[self.flags & 0x0C]

    @property
    def auto_repeat(self) -> bool:
        return bool(self.flags & F_REPEAT)


@dataclass
class DecodedKey:
    index: int
    l1: DecodedLevel
    l2: DecodedLevel


@dataclass
class DecodedImage:
    toggle_keys: list[int]
    shift_keys: list[int]
    key_rollover: int
    usb_device_type: int
    char_pacing: int
    leds: tuple[int, int, int]
    keys: list[DecodedKey]


class DecodeError(ValueError):
    pass


def decode_image(data: bytes) -> DecodedImage:
    if len(data) < 16 or data[0] != REC_HDR or data[1] != 0x01:
        raise DecodeError("not a CPxx .BIN image (bad header)")
    hlen = data[2]
    h = data[3 : 3 + hlen]
    if hlen != 0x0C:
        raise DecodeError(f"unexpected header length {hlen}")
    pos = 3 + hlen
    keys: list[DecodedKey] = []
    while pos < len(data) and data[pos] != END:
        if data[pos] != REC_HDR or data[pos + 1] != 0x02:
            raise DecodeError(f"bad key record at offset {pos:#x}")
        idx, f2, f1 = data[pos + 2], data[pos + 3], data[pos + 4]
        pos += 6
        levels = []
        for flags in (f1, f2):
            n = data[pos]
            pos += 1
            body = data[pos : pos + n]
            pos += n
            if n and body[-1] != 0:
                raise DecodeError(f"KEY{idx}: level data not 00-terminated")
            levels.append(DecodedLevel(flags, bytes(BREAK_CKD if b == BREAK_BIN else b for b in body[:-1])))
        keys.append(DecodedKey(idx, levels[0], levels[1]))
    if pos >= len(data):
        raise DecodeError("missing E5 trailer")
    pick = lambda a, b: [x for x in (a, b) if x != NO_KEY]
    return DecodedImage(pick(h[2], h[3]), pick(h[4], h[5]), h[6], h[7], h[8], (h[9], h[10], h[11]), keys)
