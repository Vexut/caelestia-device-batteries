# Device Batteries for Caelestia

A battery-ring widget for the [Caelestia](https://github.com/caelestia-dots/shell) Quickshell desktop
shell: a desktop widget and a bar widget showing the battery of your Bluetooth peripherals
(keyboard, mouse, game controller, headphones, phone, ...) and **AirPods**, with per-pod and case
levels, in-case dimming, charging bolts and pages when there are more than four devices.

* The card fills its box: rings only when roughly square, a wide row with percentages when wide, both 4 devices per page. Scroll or swipe to change pages.
* Any device that reports a battery over Bluetooth (BlueZ) or UPower appears automatically.
* AirPods: left pod, right pod and case, from a small scanner service (below).
* Material Symbols icons by default; an Apple-style icon font is optional (see *Icons*).

## Tested with

* **AirPods Pro 3**: the only AirPods model this has been checked with. Other models (AirPods 1–4, Pro 1/2, Max,
  Beats) are untested and may show wrong or missing values, especially the case, because the newer models use
  an encrypted broadcast whose layout differs between models.
* Generic Bluetooth devices (keyboard, game controller) through BlueZ/UPower: checked on one setup. Anything
  that reports a standard Bluetooth battery level should work, but this is not verified for every device.
* Caelestia on KDE Plasma 6 (Wayland, Fedora). Other setups are untested.

## Install

Requires Caelestia (Quickshell), BlueZ, Python 3.10+ and systemd (user services).

```sh
git clone https://github.com/Vexut/caelestia-device-batteries
cd caelestia-device-batteries
./install.py                 # --shell PATH for a non-default shell dir, --no-scanner to skip AirPods
systemctl --user restart caelestia-shell
```

Then add **Device Batteries** from the desktop "Add widget" menu, or enable "Device batteries" in
the taskbar settings. `./install.py --uninstall` removes everything it added.

The installer copies the QML files and adds the widget to the shell's catalog and bar. If a future
Caelestia version moves those files it prints the lines to add by hand instead.

### Dependencies

Everything is installed by `install.py`: the scanner gets its own virtualenv (`~/.local/share/airpods-battery/venv`)
with the pinned packages in `scanner/requirements.txt` ([bleak](https://github.com/hbldh/bleak),
[cryptography](https://github.com/pyca/cryptography)). Nothing is installed system-wide.

## AirPods

BlueZ does not report AirPods batteries, so `scanner/airpods_battery.py` runs as a user service and
writes `$XDG_RUNTIME_DIR/airpods-battery.json`:

* While connected it speaks Apple's AirPods control protocol (AACP, L2CAP PSM `0x1001`) for exact
  per-component levels, charging state and ear detection.
* It also reads the Bluetooth LE advertisements your own AirPods send. Newer models (e.g. Pro 3) encrypt
  them; the scanner decrypts only with the key *your* AirPods hand over when paired to your computer,
  and ignores other people's.
* The case has no connection of its own: its level and charging state come from a pod's broadcast, so they
  update while a pod is near the case with the lid open; the last value is kept meanwhile.

The decoding of the encrypted broadcast is reverse engineered and verified only on AirPods Pro 3; other models may differ.
The case's charging state is only reported by the AirPods when the case is plugged in or out, so it can lag
behind by a short while. Set `AIRPODS_DEBUG=1` on the service to log your own broadcasts to
`~/.local/state/airpods-battery/decrypted.log` and open an issue with them.

Nothing leaves your machine. The scanner makes no network connections.

## Icons

By default the widget uses Material Symbols (already part of the shell). To get Apple's SF Symbols look,
build the font from your own copy of the SF Symbols app (free from developer.apple.com):

```sh
tools/build-symbols-font.sh ~/Downloads/SF-Symbols-*.dmg
systemctl --user restart caelestia-shell
```

**SF Symbols may not be redistributed**, so this repo ships no Apple artwork and the font you build is
for your own use only. See Apple's SF Symbols license.

## Licence and credits

GPL-3.0-or-later (see `LICENSE`), the same as Caelestia. Third-party notices: `THIRD-PARTY.md`.
"AirPods" and "SF Symbols" are trademarks of Apple Inc.; this project is not affiliated with or endorsed by Apple.
The protocol notes come from public reverse-engineering work, credited in `THIRD-PARTY.md`; no code was copied from it.
