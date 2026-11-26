"""Run with:  python -m unittest discover -s tests -v   (from the project folder)"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cp48tool import KeyType, Layout, MacroMode, compile_layout, decode_image  # noqa: E402
from cp48tool.compiler import CompileError  # noqa: E402
from cp48tool.macro import MacroError, from_text, to_text  # noqa: E402

EXAMPLES = Path(r"C:\Program Files (x86)\Genovation\MacroMasterCPxx\Examples\Macro_Files")


class GoldenFiles(unittest.TestCase):
    """The compiler must reproduce .BIN files that MacroMaster wrote, byte for byte."""

    def check(self, stem: str) -> None:
        ckd, binf = ROOT / f"{stem}.ckd", ROOT / f"{stem}.bin"
        if not (ckd.exists() and binf.exists()):
            self.skipTest(f"{stem} not present")
        self.assertEqual(compile_layout(Layout.load(ckd)).hex(" "), binf.read_bytes().hex(" "))

    def test_cp48(self):
        self.check("EricKeycommands")

    def test_cp24(self):
        self.check("EricKeycommands_24")

    def test_untitled_decodes(self):
        p = ROOT / "untitled.bin"
        if not p.exists():
            self.skipTest("untitled.bin not present")
        img = decode_image(p.read_bytes())
        self.assertEqual(len(img.keys), 48)
        self.assertEqual(img.char_pacing, 4)
        self.assertTrue(all(not k.l1.codes and not k.l2.codes for k in img.keys))

    def test_decode_matches_ckd(self):
        p = ROOT / "EricKeycommands.ckd"
        if not p.exists():
            self.skipTest("no ckd")
        lay = Layout.load(p)
        img = decode_image(compile_layout(lay))
        for k, d in zip(lay.keys, img.keys):
            self.assertEqual(d.l1.codes, k.l1.codes, f"KEY{k.index}")


class CkdRoundTrip(unittest.TestCase):
    def test_lossless(self):
        files = [*ROOT.glob("*.ckd"), *(EXAMPLES.glob("*.ckd") if EXAMPLES.exists() else [])]
        for f in files:
            raw = f.read_bytes().decode("latin-1")
            if "Model_Number=MacroMaster" in raw:
                continue  # legacy 68x file format
            with self.subTest(f=f.name):
                self.assertEqual(Layout.from_text(raw).to_text(), raw)

    def test_examples_compile(self):
        if not EXAMPLES.exists():
            self.skipTest("MacroMaster not installed")
        for f in EXAMPLES.glob("DefaultCP*.ckd"):
            with self.subTest(f=f.name):
                decode_image(compile_layout(Layout.load(f)))
        img = decode_image(compile_layout(Layout.load(EXAMPLES / "MouseClicks.ckd")))
        self.assertEqual(img.usb_device_type, 12)


class CompilerRules(unittest.TestCase):
    def lay(self):
        return Layout.new("CP24")

    def rec(self, lay, i):
        return decode_image(compile_layout(lay)).keys[i]

    def test_single_key_is_separate_up(self):
        lay = self.lay(); lay.keys[0].l1.codes = from_text("H")
        self.assertEqual(self.rec(lay, 0).l1.flags, 0x09)

    def test_multi_key_is_macro(self):
        lay = self.lay(); lay.keys[0].l1.codes = from_text("Ctrl+H")
        self.assertEqual(self.rec(lay, 0).l1.flags, 0x01)

    def test_lone_modifier_tap_special_case(self):
        lay = self.lay(); lay.keys[0].l1.codes = from_text("+LShift -LShift")
        r = self.rec(lay, 0)
        self.assertEqual((r.l1.flags, r.l1.codes), (0x09, b"\x12"))

    def test_modes_and_repeat(self):
        lay = self.lay()
        lay.keys[1].l1.codes = from_text("A B"); lay.keys[1].l1.mode = MacroMode.LITERAL
        lay.keys[1].l1.auto_repeat = True
        lay.keys[2].l2.codes = from_text("C"); lay.keys[2].l2.mode = MacroMode.FAST_UP
        img = decode_image(compile_layout(lay))
        self.assertEqual(img.keys[1].l1.flags, 0x01 | 0x02 | 0x04)
        self.assertEqual(img.keys[2].l2.flags, 0x01 | 0x0C)

    def test_level_keys_in_header(self):
        lay = self.lay()
        lay.keys[3].key_type = KeyType.LEVEL_TOGGLE
        lay.keys[5].key_type = KeyType.LEVEL_SHIFT
        img = decode_image(compile_layout(lay))
        self.assertEqual((img.toggle_keys, img.shift_keys), ([3], [5]))

    def test_length_limits(self):
        lay = self.lay()
        lay.keys[0].l1.codes = bytes([0x1C]) * 223
        compile_layout(lay)
        lay.keys[0].l1.codes = bytes([0x1C]) * 224
        with self.assertRaises(CompileError):
            compile_layout(lay)
        lay.keys[0].l1.codes = bytes([0x1C]) * 112
        lay.keys[0].l2.codes = b"\x1c"
        with self.assertRaises(CompileError):
            compile_layout(lay)      # level 1 shrinks to 111 once level 2 is used

    def test_reserved_codes_rejected(self):
        lay = self.lay(); lay.keys[0].l1.codes = b"\xe6"
        with self.assertRaises(CompileError):
            compile_layout(lay)


class DriveDetection(unittest.TestCase):
    def test_label_padding_and_case(self):
        from cp48tool.drive import is_controlpad_label
        for ok in ("CONTROLPAD", "CONTROLPAD ", "controlpad", " ControlPad\t"):
            self.assertTrue(is_controlpad_label(ok), repr(ok))
        for bad in (None, "", "CONTROLPA", "CONTROLPAD2", "USB DRIVE"):
            self.assertFalse(is_controlpad_label(bad), repr(bad))


class MacroText(unittest.TestCase):
    def test_chord(self):
        self.assertEqual(from_text("Ctrl+Alt+K").hex(), "141142f011f014")
        self.assertEqual(to_text(bytes.fromhex("141142f011f014")), "Ctrl+Alt+K")

    def test_extended_chord(self):
        self.assertEqual(from_text("RCtrl+Left").hex(), "e014e06be0f014")
        self.assertEqual(to_text(bytes.fromhex("e014e06be0f014")), "RCtrl+Left")

    def test_misc_tokens(self):
        self.assertEqual(from_text("Win delay(200) LED1On MouseX+(10) <e2 30>").hex(),
                         "e01fe20132e205900ae230")
        self.assertEqual(to_text(bytes.fromhex("e065e20132e065")), "MouseForward delay(200) MouseForward")

    def test_roundtrip_user_file(self):
        p = ROOT / "EricKeycommands.ckd"
        if not p.exists():
            self.skipTest("no ckd")
        for k in Layout.load(p).keys:
            self.assertEqual(from_text(to_text(k.l1.codes)), k.l1.codes, f"KEY{k.index}")

    def test_errors(self):
        for bad in ("NotAKey", "K+Ctrl", "delay(9999)", "MouseX+"):
            with self.subTest(bad=bad), self.assertRaises(MacroError):
                from_text(bad)


if __name__ == "__main__":
    unittest.main()
