"""Command-line interface: ``python -m cp48tool <command> ...``"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import drive
from .ckd import Layout
from .compiler import CompileError, CompileOptions, compile_layout, decode_image
from .macro import to_text


def _load_image(path: Path) -> bytes:
    if path.suffix.lower() == ".ckd":
        return compile_layout(Layout.load(path))
    return path.read_bytes()


def cmd_show(args) -> int:
    lay = Layout.load(args.ckd)
    g = lay.globals
    print(f"{lay.path.name}: {g.model}, {g.num_keys} keys, rollover={g.key_rollover}, "
          f"pacing={g.char_pacing}, LEDs={g.led1}/{g.led2}/{g.led3}, usb={g.usb_device_type}")
    for k in lay.keys:
        for n in (1, 2):
            lv = k.level(n)
            if lv.codes or lv.name:
                extra = []
                if k.key_type:
                    extra.append(k.key_type.name.lower())
                if lv.mode:
                    extra.append(lv.mode.name.lower())
                if lv.auto_repeat:
                    extra.append("repeat")
                print(f"  KEY{k.index:<2} L{n}  {to_text(lv.codes):<34} {lv.name}"
                      + (f"  [{', '.join(extra)}]" if extra else ""))
    return 0


def cmd_compile(args) -> int:
    lay = Layout.load(args.ckd)
    img = compile_layout(lay, CompileOptions(default_usb_device_type=args.usb_default))
    out = Path(args.output) if args.output else lay.path.with_suffix(".bin")
    out.write_bytes(img)
    print(f"wrote {out} ({len(img)} bytes)")
    return 0


def cmd_decode(args) -> int:
    img = decode_image(Path(args.bin).read_bytes())
    print(f"rollover={img.key_rollover} pacing={img.char_pacing} usb={img.usb_device_type} "
          f"LEDs={img.leds} toggle={img.toggle_keys} shift={img.shift_keys}")
    for k in img.keys:
        for n, lv in ((1, k.l1), (2, k.l2)):
            if lv.codes:
                print(f"  KEY{k.index:<2} L{n} {lv.mode:<11}{' repeat' if lv.auto_repeat else '':7} "
                      f"{to_text(lv.codes)}")
    return 0


def cmd_verify(args) -> int:
    ours = compile_layout(Layout.load(args.ckd))
    theirs = Path(args.bin).read_bytes()
    if ours == theirs:
        print("identical")
        return 0
    n = next((i for i, (a, b) in enumerate(zip(ours, theirs)) if a != b), min(len(ours), len(theirs)))
    print(f"DIFFERENT at offset {n:#x} (ours {len(ours)} bytes, theirs {len(theirs)} bytes)")
    print("  ours  :", ours[max(0, n - 8): n + 8].hex(" "))
    print("  theirs:", theirs[max(0, n - 8): n + 8].hex(" "))
    return 1


_DRIVE_TYPES = {2: "removable", 3: "fixed", 4: "network", 5: "cd-rom", 6: "ramdisk"}


def _resolve_drive(arg: str | None) -> Path | None:
    """--drive F / F: / F:\\ overrides auto-detection."""
    if not arg:
        return drive.find_controlpad()
    root = Path(arg.rstrip(":\\/") + ":\\") if len(arg.rstrip(":\\/")) == 1 else Path(arg)
    if not root.is_dir():
        raise drive.DriveError(f"{root} is not accessible")
    return root


def cmd_status(args) -> int:
    root = _resolve_drive(args.drive)
    if root is None:
        print("Keypad not in Flash Drive mode (no CONTROLPAD volume found).")
        if sys.platform == "win32":
            print("Volumes Windows reports:")
            for r, dtype, label in drive.scan_drives():
                print(f"  {str(r):5} {_DRIVE_TYPES.get(dtype, dtype)!s:10} label={label!r}")
            print("If the keypad is one of these, pass it explicitly, e.g.  --drive F")
        return 1
    print(f"CONTROLPAD drive at {root}")
    for p in drive.list_bins(root):
        print(f"  {p.name}  {p.stat().st_size} bytes")
    return 0


def cmd_flash(args) -> int:
    src = Path(args.file)
    img = _load_image(src)
    decode_image(img)  # sanity check before touching the keypad
    root = _resolve_drive(args.drive)
    if root is not None and args.drive and sys.platform == "win32":
        label = next((lbl for r, _, lbl in drive.scan_drives() if r == root), None)
        if not drive.is_controlpad_label(label):
            print(f"warning: {root} is labelled {label!r}, not CONTROLPAD. Old .BIN files on it "
                  "would be deleted. Make sure this really is the keypad.")
    if root is None:
        print("CONTROLPAD drive not found.\n"
              "  1. Move the switch on the back of the keypad to the Flash Drive position.\n"
              "  2. Wait for the LED to turn solid red and the CONTROLPAD drive to appear.\n"
              "  3. Run this command again.")
        return 1
    old = drive.list_bins(root)
    print(f"CONTROLPAD at {root}; will write {len(img)} bytes from {src.name}"
          + (f", replacing {', '.join(p.name for p in old)}" if old else ""))
    if not args.yes and input("Proceed? [y/N] ").strip().lower() != "y":
        print("aborted")
        return 1
    dest = drive.copy_image(img, root, name=src.stem)
    print(f"wrote {dest}. Now move the rear switch back to the Keyboard position; the LED "
          "flickers blue/red while the keypad loads the new settings.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cp48tool", description="Program Genovation CP24/CP48 keypads.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("show", help="list the macros in a .ckd file")
    s.add_argument("ckd"); s.set_defaults(fn=cmd_show)

    s = sub.add_parser("compile", help="compile a .ckd into a .bin image")
    s.add_argument("ckd"); s.add_argument("-o", "--output")
    s.add_argument("--usb-default", type=lambda v: int(v, 0), default=0,
                   help="USB device type byte when the CKD has none (default 0, as older MacroMaster)")
    s.set_defaults(fn=cmd_compile)

    s = sub.add_parser("decode", help="print the contents of a .bin image")
    s.add_argument("bin"); s.set_defaults(fn=cmd_decode)

    s = sub.add_parser("verify", help="check that a .ckd compiles to exactly the given .bin")
    s.add_argument("ckd"); s.add_argument("bin"); s.set_defaults(fn=cmd_verify)

    drive_help = "keypad drive letter (e.g. F) instead of auto-detecting the CONTROLPAD volume"
    s = sub.add_parser("status", help="look for the keypad in Flash Drive mode")
    s.add_argument("--drive", help=drive_help)
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("flash", help="copy a .ckd/.bin onto the keypad (Flash Drive mode)")
    s.add_argument("file"); s.add_argument("-y", "--yes", action="store_true", help="don't ask")
    s.add_argument("--drive", help=drive_help)
    s.set_defaults(fn=cmd_flash)

    s = sub.add_parser("gui", help="open the graphical editor")
    s.add_argument("ckd", nargs="?")
    s.set_defaults(fn=lambda a: __import__("cp48tool.gui", fromlist=["run"]).run(a.ckd))

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except (CompileError, ValueError, OSError, drive.DriveError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
