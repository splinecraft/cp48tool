"""Find the keypad's CONTROLPAD mass-storage volume and copy a .BIN image onto it.

This mirrors CPxxLoad's "Copy Bin for me": locate the removable volume labelled
CONTROLPAD, delete any old .BIN files on it (the flash is tiny), write the new
image, and make sure it is flushed before the user flips the rear switch back.
"""

from __future__ import annotations

import ctypes
import os
import string
import sys
from ctypes import wintypes
from pathlib import Path

VOLUME_LABEL = "CONTROLPAD"
DRIVE_REMOVABLE = 2


class DriveError(RuntimeError):
    pass


def _volume_label(root: str) -> str | None:
    buf = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    serial, maxlen, flags = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root), buf, len(buf), ctypes.byref(serial),
        ctypes.byref(maxlen), ctypes.byref(flags), fs, len(fs))
    return buf.value if ok else None


def is_controlpad_label(label: str | None) -> bool:
    # FAT pads labels to 11 chars with spaces; "CONTROLPAD" is 10, so some systems report
    # "CONTROLPAD " -- compare trimmed and case-insensitively.
    return (label or "").strip().upper() == VOLUME_LABEL


def scan_drives() -> list[tuple[Path, int, str | None]]:
    """(root, GetDriveType code, label) for every lettered volume. Windows only."""
    k32 = ctypes.windll.kernel32
    out = []
    old = k32.SetErrorMode(1)  # SEM_FAILCRITICALERRORS: no "insert a disk" popups
    try:
        mask = k32.GetLogicalDrives()
        for i, letter in enumerate(string.ascii_uppercase):
            if mask & (1 << i):
                root = f"{letter}:\\"
                out.append((Path(root), k32.GetDriveTypeW(ctypes.c_wchar_p(root)), _volume_label(root)))
    finally:
        k32.SetErrorMode(old)
    return out


def find_controlpad() -> Path | None:
    """Return the root of the CONTROLPAD volume, or None if the keypad isn't in drive mode."""
    if sys.platform == "win32":
        # Match on the label regardless of drive type: some USB stacks report the keypad as fixed.
        for root, _dtype, label in scan_drives():
            if is_controlpad_label(label):
                return root
        return None
    # macOS / Linux mount points (MacroMaster itself looks at /Volumes/CONTROLPAD/)
    for cand in (Path("/Volumes") / VOLUME_LABEL,
                 *Path("/media").glob(f"*/{VOLUME_LABEL}"),
                 *Path("/run/media").glob(f"*/{VOLUME_LABEL}")):
        if cand.is_dir():
            return cand
    return None


def list_bins(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_file() and p.suffix.lower() == ".bin")


def _short_name(name: str) -> str:
    """Make an 8.3-safe file name; the keypad's tiny FAT volume may not cope with LFNs."""
    stem = "".join(c for c in Path(name).stem.upper() if c.isalnum() or c in "_-")[:8] or "KEYPAD"
    return f"{stem}.BIN"


def copy_image(image: bytes, root: Path | None = None, name: str = "KEYPAD.BIN",
               delete_old: bool = True) -> Path:
    root = root or find_controlpad()
    if root is None:
        raise DriveError("CONTROLPAD drive not found. Move the keypad's rear switch to the "
                         "Flash Drive position, wait for the LED to turn solid red, and retry.")
    if delete_old:
        for old in list_bins(root):
            old.unlink()
    dest = root / _short_name(name)
    with open(dest, "wb") as fh:
        fh.write(image)
        fh.flush()
        os.fsync(fh.fileno())       # make sure it reached the device, not just the cache
    if dest.read_bytes() != image:
        raise DriveError(f"verification failed: {dest} does not match the image written")
    return dest
