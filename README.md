# cp48tool

A replacement programmer for Genovation ControlPad CP24 and CP48 keypads with the
**Flash Drive** rear switch (firmware v1.x). It reads and writes MacroMaster `.ckd` files,
compiles them to the keypad's `.bin` format, and copies the image onto the keypad.

## Use

```powershell
.\cp48tool-gui.cmd EricKeycommands.ckd                         # editor (first run creates a venv in %LOCALAPPDATA%)
python -m cp48tool show EricKeycommands.ckd                     # list macros
python -m cp48tool flash EricKeycommands.ckd                    # program the keypad
python -m cp48tool verify EricKeycommands.ckd EricKeycommands.bin
python -m unittest discover -s tests -v
```

How programming works:

1. Move the rear switch to the Flash Drive position. The LED turns solid red and a `CONTROLPAD` drive appears.
2. The tool deletes the old `.BIN`, writes the new one, and flushes it to the device.
3. Move the switch back to the Keyboard position. The LED flickers while the keypad loads the new settings, then it reboots.

## Macro text

| Text | Meaning |
|---|---|
| `Ctrl+Alt+K` | chord: modifiers down, key, modifiers up |
| `K` | a single key |
| `+LShift` / `-LShift` | explicit press / release |
| `delay(200)` | pause in ms (4 ms steps) |
| `LED1On`, `Mute`, `MouseLeft`, `MouseX+(10)` | Genovation custom, media and mouse codes |
| `<e0 6b>` | raw bytes |

## .BIN format

This was recovered from `CPxxLoad.exe`. The compiler reproduces MacroMaster's own output byte for byte.

```
E4 01 0C  E0 70  T1 T2 S1 S2  KRO USB PACE LED1 LED2 LED3      header (T=toggle keys, S=shift keys, 80=none)
E4 02 kk  F2 F1 kk  L1 <codes..00>  L2 <codes..00>             one per key; F0 in codes becomes E3
E5                                                             end
flags: 01 data, 02 auto-repeat, 08 separate-up, 04 literal, 0C fast-up (00 = macro)
```
