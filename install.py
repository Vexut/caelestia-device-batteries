#!/usr/bin/env python3
"""Install (or --uninstall) the Device Batteries widget into a Caelestia shell checkout.

    ./install.py [--shell ~/.config/quickshell/caelestia] [--no-scanner] [--uninstall]

Copies the QML files, registers the widget in the shell's widget catalog and bar, and
(unless --no-scanner) sets up the AirPods scanner as a systemd user service with its own
Python virtualenv. Every patch is idempotent and is skipped with a warning if the shell's
files do not look as expected."""
import argparse, os, pathlib, shutil, subprocess, sys

HERE = pathlib.Path(__file__).resolve().parent
ap = argparse.ArgumentParser()
ap.add_argument("--shell", default="~/.config/quickshell/caelestia")
ap.add_argument("--no-scanner", action="store_true")
ap.add_argument("--uninstall", action="store_true")
args = ap.parse_args()
SH = pathlib.Path(args.shell).expanduser()
if not (SH / "shell.qml").exists():
    sys.exit(f"{SH} does not look like a Caelestia shell (no shell.qml). Use --shell.")

FILES = {
    "quickshell/services/DeviceBatteries.qml": "services/DeviceBatteries.qml",
    "quickshell/services/airpods.js": "services/airpods.js",
    "quickshell/widgets/DeviceBatteriesWidget.qml": "modules/background/desktopicons/widgets/DeviceBatteriesWidget.qml",
    "quickshell/widgets/DeviceRing.qml": "modules/background/desktopicons/DeviceRing.qml",
    "quickshell/bar/BtBatteries.qml": "modules/bar/components/BtBatteries.qml",
}
# (file, anchor line that stays, text inserted before the anchor)
CATALOG = ("modules/background/desktopicons/WidgetCatalog.qml", '        { type: "note"',
    '        { type: "devices", name: qsTr("Device Batteries"), icon: "battery_android_full", size: { w: 2, h: 2 }, min: { w: 1, h: 1 }, max: { w: 4, h: 2 }, shape: "square-or-wide", contentPadding: 9, source: "widgets/DeviceBatteriesWidget.qml" },\n')
BARDEL = ("modules/bar/Bar.qml", "            DelegateChoice {\n                roleValue: \"showDesktop\"",
    '            DelegateChoice {\n                roleValue: "btBatteries"\n                delegate: WrappedLoader {\n                    sourceComponent: BtBatteries {}\n                }\n            }\n')
LABEL = ("modules/nexus/pages/panels/taskbar/BarComponents.qml", '            "notes":',
    '            "btBatteries": { icon: "battery_android_full", name: qsTr("Device batteries") },\n')

# Fixed-shape card support in BigItem (a widget can ask for a square / 2:1 card via info.shape).
BIGITEM = ("modules/background/desktopicons/BigItem.qml", [
 ("        anchors.leftMargin: root.frameless ? 0 : root.sideGap\n        anchors.rightMargin: root.frameless ? 0 : root.sideGap\n        anchors.topMargin: root.frameless ? 0 : root.topGap\n        anchors.bottomMargin: root.frameless ? 0 : root.labelHeight\n",
  "        anchors.leftMargin: root.frameless ? 0 : root.sideGap - root.leftPull\n        anchors.rightMargin: root.frameless ? 0 : root.sideGap + root.fitX * 2 + root.leftPull\n        anchors.topMargin: root.frameless ? 0 : root.topGap + root.fitY\n        anchors.bottomMargin: root.frameless ? 0 : root.labelHeight + root.fitY\n"),
 ("    readonly property real labelHeight: isGroup ? Tokens.padding.extraLargeIncreased : topGap\n",
  "    readonly property real labelHeight: isGroup ? Tokens.padding.extraLargeIncreased : topGap\n    // A widget can ask for a fixed card shape (info.shape): a square, or 2:1 when its box is wide.\n    // The card is then the largest such shape that fits in the box, against its left neighbour.\n    readonly property real availW: width - sideGap * 2\n    readonly property real availH: height - topGap - labelHeight\n    readonly property real fitRatio: info.shape ? (availW / availH >= 1.5 ? 2 : 1) : 0\n    // Wide boxes keep the whole height (no 2:1 crop) and only cap the width at 2.6:1.\n    readonly property real fitW: fitRatio === 2 ? Math.min(availW, availH * 2.6) : (fitRatio > 0 ? Math.min(availW, availH) : availW)\n    readonly property real fitH: fitRatio === 2 ? availH : (fitRatio > 0 ? fitW : availH)\n    readonly property real fitX: (availW - fitW) / 2\n    readonly property real fitY: (availH - fitH) / 2\n    readonly property real leftPull: fitRatio > 0 ? sideGap - 2 : 0\n"),
 ("anchors.margins: root.frameless ? 0 : (root.isGroup ? Tokens.padding.small : Tokens.padding.large)",
  "anchors.margins: root.frameless ? 0 : (root.isGroup ? Tokens.padding.small : (info.contentPadding ?? Tokens.padding.large))"),
])

def patch_bigitem(remove):
    rel, pairs = BIGITEM
    f = SH / rel
    s = f.read_text()
    for old, new in pairs:
        if remove:
            s = s.replace(new, old)
        elif new in s:
            continue
        elif old in s:
            s = s.replace(old, new, 1)
        else:
            print(f"WARNING: could not patch {rel}; the widget will still work but not as a fixed-shape card")
            return
    f.write_text(s)

def patch(spec, remove):
    rel, anchor, text = spec
    f = SH / rel
    s = f.read_text()
    if remove:
        f.write_text(s.replace(text, ""))
    elif text in s:
        pass
    elif anchor in s:
        f.write_text(s.replace(anchor, text + anchor, 1))
    else:
        print(f"WARNING: could not patch {rel}: anchor not found; add this by hand:\n{text}")

def bar_widgets(remove):
    f = SH / "modules/bar/BarWidgets.qml"
    s = f.read_text()
    entry = '{ id: "btBatteries", zone: "right" }'
    if remove:
        s = s.replace(',\n        ' + entry, "").replace(entry, "")
    elif entry not in s:
        i = s.rfind("}", 0, s.index("]", s.index("zone")))
        s = s[:i + 1] + ",\n        " + entry + s[i + 1:]
    f.write_text(s)

if args.uninstall:
    for dst in FILES.values():
        (SH / dst).unlink(missing_ok=True)
    for spec in (CATALOG, BARDEL, LABEL):
        patch(spec, True)
    bar_widgets(True)
    patch_bigitem(True)
    if not args.no_scanner:
        subprocess.run(["systemctl", "--user", "disable", "--now", "airpods-battery.service"], check=False)
    print("Removed. Restart the shell: systemctl --user restart caelestia-shell")
    sys.exit()

for src, dst in FILES.items():
    (SH / dst).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / src, SH / dst)
for spec in (CATALOG, BARDEL, LABEL):
    patch(spec, False)
bar_widgets(False)
patch_bigitem(False)

if not args.no_scanner:
    d = pathlib.Path("~/.local/share/airpods-battery").expanduser()
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "scanner/airpods_battery.py", d)
    subprocess.run([sys.executable, "-m", "venv", str(d / "venv")], check=True)
    subprocess.run([str(d / "venv/bin/pip"), "install", "--quiet", "-r", str(HERE / "scanner/requirements.txt")], check=True)
    u = pathlib.Path("~/.config/systemd/user").expanduser()
    u.mkdir(parents=True, exist_ok=True)
    shutil.copy2(HERE / "scanner/airpods-battery.service", u)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "airpods-battery.service"], check=True)
print("Installed. Restart the shell: systemctl --user restart caelestia-shell")
