"""PySide6 editor for CP24/CP48 layouts.  Run:  python -m cp48tool gui [file.ckd]"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont, QKeyEvent, QKeySequence
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSizePolicy, QSpinBox, QTabWidget, QToolBar, QVBoxLayout, QWidget,
)

from . import drive
from .ckd import KeyType, LedFunction, Layout, MacroMode, UsbDeviceType
from .compiler import L1_MAX, L2_MAX, CompileError, compile_layout
from .macro import MacroError, from_text, to_text

# Physical grid: columns per row. KEY0 is top-left, numbered row by row (left to right).
GRID_COLS = {"CP24": 4, "CP48": 8}

MODE_LABELS = {
    MacroMode.AUTO: "Default (Auto Sense)",
    MacroMode.SEPARATE_UP: "Separate Up Codes (chording, held)",
    MacroMode.MACRO: "Macro (regular typing)",
    MacroMode.LITERAL: "Literal (you supply every break)",
    MacroMode.FAST_UP: "Fast Up Codes",
}
KEYTYPE_LABELS = {
    KeyType.NORMAL: "Normal key",
    KeyType.LEVEL_SHIFT: "Level Shift (hold for level 2)",
    KeyType.LEVEL_TOGGLE: "Level Toggle (press to switch level)",
}
LED_LABELS = {
    LedFunction.NOT_USED: "Not Used", LedFunction.CAPS_LOCK: "Caps Lock",
    LedFunction.NUM_LOCK: "Num Lock", LedFunction.LEVEL_INDICATOR: "Level Indicator",
    LedFunction.HOST_MACRO_CONTROL: "Host/Macro Control",
    LedFunction.POWER_INDICATOR: "Power Indicator", LedFunction.SCROLL_LOCK: "Scroll Lock",
}
USB_LABELS = {
    None: "(not set: keep as before)",
    UsbDeviceType.BASIC_KEYBOARD: "Basic Keyboard",
    UsbDeviceType.MULTIMEDIA_KEYBOARD: "Multimedia Keyboard",
    UsbDeviceType.MULTIMEDIA_KEYBOARD_MOUSE: "Multimedia Keyboard + Mouse",
}

# Qt key -> cp48tool key name, for the "record" field.
_QT_KEYS: dict[int, str] = {
    **{getattr(Qt.Key, f"Key_{c}"): c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"},
    **{getattr(Qt.Key, f"Key_F{i}"): f"F{i}" for i in range(1, 25)},
    Qt.Key.Key_Escape: "Esc", Qt.Key.Key_Tab: "Tab", Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Return: "Enter", Qt.Key.Key_Enter: "KPEnter", Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End",
    Qt.Key.Key_PageUp: "PageUp", Qt.Key.Key_PageDown: "PageDown", Qt.Key.Key_Left: "Left",
    Qt.Key.Key_Right: "Right", Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
    Qt.Key.Key_Space: "Space", Qt.Key.Key_Minus: "-", Qt.Key.Key_Equal: "=",
    Qt.Key.Key_BracketLeft: "[", Qt.Key.Key_BracketRight: "]", Qt.Key.Key_Backslash: "\\",
    Qt.Key.Key_Semicolon: ";", Qt.Key.Key_Apostrophe: "'", Qt.Key.Key_Comma: ",",
    Qt.Key.Key_Period: ".", Qt.Key.Key_Slash: "/", Qt.Key.Key_QuoteLeft: "`",
    Qt.Key.Key_Print: "PrintScreen", Qt.Key.Key_Pause: "Pause", Qt.Key.Key_CapsLock: "CapsLock",
    Qt.Key.Key_NumLock: "NumLock", Qt.Key.Key_ScrollLock: "ScrollLock",
    Qt.Key.Key_Menu: "App",
    # shifted symbols come through as their own Qt keys; map back to the physical key
    Qt.Key.Key_Exclam: "1", Qt.Key.Key_At: "2", Qt.Key.Key_NumberSign: "3",
    Qt.Key.Key_Dollar: "4", Qt.Key.Key_Percent: "5", Qt.Key.Key_AsciiCircum: "6",
    Qt.Key.Key_Ampersand: "7", Qt.Key.Key_Asterisk: "8", Qt.Key.Key_ParenLeft: "9",
    Qt.Key.Key_ParenRight: "0", Qt.Key.Key_Underscore: "-", Qt.Key.Key_Plus: "=",
    Qt.Key.Key_BraceLeft: "[", Qt.Key.Key_BraceRight: "]", Qt.Key.Key_Bar: "\\",
    Qt.Key.Key_Colon: ";", Qt.Key.Key_QuoteDbl: "'", Qt.Key.Key_Less: ",",
    Qt.Key.Key_Greater: ".", Qt.Key.Key_Question: "/", Qt.Key.Key_AsciiTilde: "`",
}
_MOD_KEYS = {Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta}


class RecordEdit(QLineEdit):
    """Press a key combination; emits it as chord text like 'Ctrl+Alt+K'."""

    recorded = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setPlaceholderText("click here, then press a shortcut to append it")

    def keyPressEvent(self, e: QKeyEvent) -> None:  # noqa: N802
        if e.key() in _MOD_KEYS:
            return
        name = _QT_KEYS.get(e.key())
        if name is None:
            self.setText(f"(unsupported key: {QKeySequence(e.key()).toString()})")
            return
        keypad = bool(e.modifiers() & Qt.KeyboardModifier.KeypadModifier)
        if keypad and name in "0123456789":
            name = f"KP{name}"
        mods = [n for flag, n in ((Qt.KeyboardModifier.ControlModifier, "Ctrl"),
                                  (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                                  (Qt.KeyboardModifier.AltModifier, "Alt"),
                                  (Qt.KeyboardModifier.MetaModifier, "Win"))
                if e.modifiers() & flag]
        text = "+".join([*mods, name])
        self.setText(text)
        self.recorded.emit(text)


class LevelEditor(QWidget):
    changed = Signal()

    def __init__(self, level: int) -> None:
        super().__init__()
        self.level = level
        self.name = QLineEdit()
        self.name.setPlaceholderText("label (for your keycap / reference)")
        self.text = QLineEdit()
        self.text.setFont(QFont("Consolas", 10))
        self.text.setPlaceholderText("e.g.  Ctrl+Alt+K    or    +LShift H -LShift delay(100) I")
        self.record = RecordEdit()
        self.record.recorded.connect(self._append)
        clear = QPushButton("Clear")
        clear.setToolTip("Erase this level's macro")
        clear.clicked.connect(self.clear_macro)
        rec_row = QHBoxLayout()
        rec_row.addWidget(self.record, 1)
        rec_row.addWidget(clear)
        self.mode = QComboBox()
        for m, lbl in MODE_LABELS.items():
            self.mode.addItem(lbl, m)
        self.repeat = QCheckBox("This macro can auto-repeat while held")
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.hexview = QLabel()
        self.hexview.setFont(QFont("Consolas", 9))
        self.hexview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.hexview.setWordWrap(True)

        form = QFormLayout(self)
        form.addRow("Name", self.name)
        form.addRow("Macro", self.text)
        form.addRow("Record", rec_row)
        form.addRow("Mode", self.mode)
        form.addRow("", self.repeat)
        form.addRow("CKD codes", self.hexview)
        form.addRow("", self.status)

        for w in (self.name, self.text):
            w.textEdited.connect(self._edited)
        self.mode.currentIndexChanged.connect(self._edited)
        self.repeat.toggled.connect(self._edited)
        self.valid = True
        self.codes = b""
        self._loading = False

    def clear_macro(self) -> None:
        # setText() doesn't emit textEdited, so push the change to the model explicitly.
        self.text.clear()
        self.record.clear()
        self._edited()

    def _append(self, chord: str) -> None:
        cur = self.text.text().strip()
        self.text.setText(f"{cur} {chord}".strip())
        self._edited()

    def load(self, name: str, codes: bytes, mode: MacroMode, repeat: bool) -> None:
        self._loading = True
        self.name.setText(name)
        self.text.setText(to_text(codes))
        self.mode.setCurrentIndex(self.mode.findData(mode))
        self.repeat.setChecked(repeat)
        self.record.clear()
        self._loading = False
        self._validate()

    def _validate(self) -> None:
        try:
            self.codes = from_text(self.text.text())
            self.valid = True
            self.hexview.setText(self.codes.hex(" ") or "(empty)")
        except MacroError as exc:
            self.valid = False
            self.hexview.setText("")
            self.status.setText(f"<span style='color:#c0392b'>{exc}</span>")
            return
        self.status.setText("")

    def set_capacity(self, limit: int) -> None:
        if self.valid:
            used = len(self.codes)
            color = "#c0392b" if used >= limit else "#7f8c8d"
            self.status.setText(f"<span style='color:{color}'>{used} / {limit - 1} bytes</span>")

    def _edited(self, *_) -> None:
        if self._loading:
            return
        self._validate()
        self.changed.emit()


class KeyButton(QPushButton):
    def __init__(self, index: int) -> None:
        super().__init__()
        self.index = index
        self.setCheckable(True)
        self.setMinimumSize(92, 62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def refresh(self, key) -> None:
        label = key.l1.name or to_text(key.l1.codes)
        if len(label) > 24:
            label = label[:23] + "…"
        tag = {KeyType.LEVEL_SHIFT: " ⇧", KeyType.LEVEL_TOGGLE: " ⇄"}.get(key.key_type, "")
        l2 = " ²" if key.l2.codes else ""
        self.setText(f"{self.index}{tag}{l2}\n{label}")
        self.setToolTip(f"KEY{self.index}\nL1: {to_text(key.l1.codes)}\nL2: {to_text(key.l2.codes)}")
        used = bool(key.l1.codes or key.l2.codes or key.key_type)
        self.setStyleSheet(
            "QPushButton{text-align:center;padding:4px;border-radius:6px;"
            f"background:{'#2e4a62' if used else '#3a3a3a'};color:{'#ecf0f1' if used else '#95a5a6'};"
            "border:1px solid #222}"
            "QPushButton:checked{border:2px solid #f39c12}")


class PropertiesDialog(QDialog):
    def __init__(self, layout: Layout, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keypad properties")
        g = layout.globals
        self.rollover = QSpinBox(); self.rollover.setRange(1, 6); self.rollover.setValue(g.key_rollover)
        self.pacing = QSpinBox(); self.pacing.setRange(0, 20); self.pacing.setSuffix(" ms")
        self.pacing.setValue(g.char_pacing)
        self.leds = []
        for v in (g.led1, g.led2, g.led3):
            c = QComboBox()
            for f, lbl in LED_LABELS.items():
                c.addItem(lbl, int(f))
            c.setCurrentIndex(max(0, c.findData(v)))
            self.leds.append(c)
        self.usb = QComboBox()
        for t, lbl in USB_LABELS.items():
            self.usb.addItem(lbl, None if t is None else int(t))
        self.usb.setCurrentIndex(max(0, self.usb.findData(g.usb_device_type)))
        form = QFormLayout(self)
        form.addRow("Key rollover", self.rollover)
        form.addRow("Inter-character pacing", self.pacing)
        form.addRow("LED 1", self.leds[0])
        form.addRow("LED 2 (2024+ CP48)", self.leds[1])
        form.addRow("LED 3 (2024+ CP48)", self.leds[2])
        form.addRow("USB device type", self.usb)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form.addRow(bb)

    def apply(self, layout: Layout) -> None:
        g = layout.globals
        g.key_rollover = self.rollover.value()
        g.char_pacing = self.pacing.value()
        g.led1, g.led2, g.led3 = (c.currentData() for c in self.leds)
        g.usb_device_type = self.usb.currentData()


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None) -> None:
        super().__init__()
        self.layout_: Layout = Layout.new("CP48")
        self.dirty = False
        self.current = 0
        self.buttons: list[KeyButton] = []

        tb = QToolBar(); tb.setMovable(False); self.addToolBar(tb)
        def act(text, slot, shortcut=None):
            a = QAction(text, self); a.triggered.connect(slot)
            if shortcut: a.setShortcut(shortcut)
            tb.addAction(a); return a
        act("New CP48", lambda: self.new("CP48"))
        act("New CP24", lambda: self.new("CP24"))
        act("Open…", self.open, QKeySequence.StandardKey.Open)
        act("Save", self.save, QKeySequence.StandardKey.Save)
        act("Save As…", self.save_as, QKeySequence.StandardKey.SaveAs)
        tb.addSeparator()
        act("Properties…", self.properties)
        tb.addSeparator()
        act("Program keypad…", self.flash)

        self.grid_box = QGroupBox("Keypad")
        self.grid = QGridLayout(self.grid_box)
        self.grid.setSpacing(6)

        self.keytype = QComboBox()
        for t, lbl in KEYTYPE_LABELS.items():
            self.keytype.addItem(lbl, t)
        self.keytype.currentIndexChanged.connect(self._key_edited)
        self.levels = [LevelEditor(1), LevelEditor(2)]
        tabs = QTabWidget()
        for lv in self.levels:
            tabs.addTab(lv, f"Level {lv.level}")
            lv.changed.connect(self._key_edited)
        self.key_title = QLabel()
        self.key_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        help_ = QLabel(
            "<b>Macro syntax</b>: <code>Ctrl+Alt+K</code> chord · <code>K</code> key · "
            "<code>+LShift</code>/<code>-LShift</code> press/release · <code>delay(200)</code> · "
            "<code>LED1On</code> · <code>MouseX+(10)</code> · <code>&lt;e0 6b&gt;</code> raw bytes. "
            "Names: Ctrl Shift Alt Win, RCtrl RShift RAlt RWin, F1–F24, Left Right Up Down, Home End, "
            "PageUp PageDown, Insert Delete, Esc Tab Enter Space Backspace, KP0–KP9, Mute VolumeUp, "
            "MouseLeft MouseRight…")
        help_.setWordWrap(True)
        help_.setStyleSheet("color:#7f8c8d")

        right = QWidget(); rv = QVBoxLayout(right)
        rv.addWidget(self.key_title)
        rv.addWidget(self.keytype)
        rv.addWidget(tabs, 1)
        rv.addWidget(help_)
        right.setMinimumWidth(460)

        central = QWidget(); h = QHBoxLayout(central)
        h.addWidget(self.grid_box, 3); h.addWidget(right, 2)
        self.setCentralWidget(central)
        self.resize(1400, 700)

        if path:
            self._load(Path(path))
        else:
            self._rebuild()

    # ---- file handling -------------------------------------------------------------
    def _title(self) -> None:
        name = self.layout_.path.name if self.layout_.path else "untitled"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} [{self.layout_.globals.model}] — cp48tool")

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        r = QMessageBox.question(self, "Unsaved changes", "Save changes first?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save()
        return r == QMessageBox.StandardButton.Discard

    def new(self, model: str) -> None:
        if self._confirm_discard():
            self.layout_ = Layout.new(model); self.dirty = False; self.current = 0; self._rebuild()

    def open(self) -> None:
        if not self._confirm_discard():
            return
        fn, _ = QFileDialog.getOpenFileName(self, "Open layout", str(Path.cwd()), "MacroMaster CKD (*.ckd)")
        if fn:
            self._load(Path(fn))

    def _load(self, p: Path) -> None:
        try:
            self.layout_ = Layout.load(p)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Open failed", str(exc)); return
        self.dirty = False; self.current = 0; self._rebuild()

    def save(self) -> bool:
        if self.layout_.path is None:
            return self.save_as()
        return self._write(self.layout_.path)

    def save_as(self) -> bool:
        fn, _ = QFileDialog.getSaveFileName(self, "Save layout", str(self.layout_.path or Path.cwd()),
                                            "MacroMaster CKD (*.ckd)")
        return self._write(Path(fn).with_suffix(".ckd")) if fn else False

    def _write(self, p: Path) -> bool:
        if not self._all_valid():
            return False
        try:
            image = compile_layout(self.layout_)
            self.layout_.save(p)
            p.with_suffix(".bin").write_bytes(image)   # like MacroMaster: keep the .bin alongside
        except (CompileError, OSError) as exc:
            QMessageBox.critical(self, "Save failed", str(exc)); return False
        self.dirty = False; self._title()
        self.statusBar().showMessage(f"Saved {p.name} and {p.with_suffix('.bin').name}", 5000)
        return True

    def closeEvent(self, e) -> None:  # noqa: N802
        e.accept() if self._confirm_discard() else e.ignore()

    # ---- grid & editing -----------------------------------------------------------
    def _rebuild(self) -> None:
        while self.grid.count():
            self.grid.takeAt(0).widget().deleteLater()
        cols = GRID_COLS.get(self.layout_.globals.model, 8)
        self.buttons = []
        for k in self.layout_.keys:
            b = KeyButton(k.index)
            b.clicked.connect(lambda _=False, i=k.index: self.select(i))
            self.grid.addWidget(b, k.index // cols, k.index % cols)
            b.refresh(k)
            self.buttons.append(b)
        self.select(min(self.current, len(self.buttons) - 1))
        self._title()

    def select(self, i: int) -> None:
        self.current = i
        for b in self.buttons:
            b.setChecked(b.index == i)
        k = self.layout_.keys[i]
        self.key_title.setText(f"Key {i}")
        self.keytype.blockSignals(True)
        self.keytype.setCurrentIndex(self.keytype.findData(k.key_type))
        self.keytype.blockSignals(False)
        for ed, lv in zip(self.levels, (k.l1, k.l2)):
            ed.load(lv.name, lv.codes, lv.mode, lv.auto_repeat)
        self._capacity()

    def _capacity(self) -> None:
        k = self.layout_.keys[self.current]
        self.levels[0].set_capacity(L1_MAX if not k.l2.codes else L2_MAX)
        self.levels[1].set_capacity(L2_MAX)

    def _key_edited(self) -> None:
        k = self.layout_.keys[self.current]
        k.key_type = self.keytype.currentData()
        for ed, lv in zip(self.levels, (k.l1, k.l2)):
            lv.name = ed.name.text()
            lv.mode = ed.mode.currentData()
            lv.auto_repeat = ed.repeat.isChecked()
            if ed.valid:
                lv.codes = ed.codes
        self.buttons[self.current].refresh(k)
        self._capacity()
        self.dirty = True; self._title()

    def _all_valid(self) -> bool:
        if not all(ed.valid for ed in self.levels):
            QMessageBox.warning(self, "Invalid macro", "Fix the macro text highlighted in red first.")
            return False
        try:
            compile_layout(self.layout_)
        except CompileError as exc:
            QMessageBox.warning(self, "Cannot compile", str(exc)); return False
        return True

    def properties(self) -> None:
        d = PropertiesDialog(self.layout_, self)
        if d.exec():
            d.apply(self.layout_); self.dirty = True; self._title()

    # ---- programming ------------------------------------------------------------
    def flash(self) -> None:
        if not self._all_valid():
            return
        image = compile_layout(self.layout_)
        while (root := drive.find_controlpad()) is None:
            r = QMessageBox.information(
                self, "Put the keypad in Flash Drive mode",
                "1. Move the switch on the back of the keypad to the Flash Drive position.\n"
                "2. Wait for the LED to turn solid red and the CONTROLPAD drive to appear.\n"
                "3. Click Retry.",
                QMessageBox.StandardButton.Retry | QMessageBox.StandardButton.Cancel)
            if r != QMessageBox.StandardButton.Retry:
                return
        old = ", ".join(p.name for p in drive.list_bins(root)) or "nothing"
        if QMessageBox.question(
                self, "Program keypad",
                f"Write {len(image)} bytes to {root} (replacing {old})?") != QMessageBox.StandardButton.Yes:
            return
        stem = self.layout_.path.stem if self.layout_.path else "KEYPAD"
        try:
            dest = drive.copy_image(image, root, name=stem)
        except (OSError, drive.DriveError) as exc:
            QMessageBox.critical(self, "Programming failed", str(exc)); return
        QMessageBox.information(
            self, "Done",
            f"Wrote {dest}.\n\nNow move the rear switch back to the Keyboard position. The LED "
            "flickers blue/red while the keypad loads the new settings, then it reboots.")


def run(path: str | None = None) -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyle("Fusion")
    w = MainWindow(path)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run(sys.argv[1] if len(sys.argv) > 1 else None))
