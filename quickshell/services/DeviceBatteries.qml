pragma Singleton

import "airpods.js" as AirPods
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Bluetooth
import Quickshell.Services.UPower

// One shared list of connected peripherals and their battery levels, used by
// both the bar widget and the desktop widget. Sources, merged by name:
//  - BlueZ Battery Service: any connected device that reports a battery
//    (keyboards, mice, controllers, headphones, phones, watches, ...)
//  - UPower non-laptop devices (game controllers via the kernel driver)
//  - the airpods-battery scanner, for AirPods (BlueZ does not report those)
// Devices with no battery reading are left out. Each entry:
//   { name, label, glyph, icon, known, level (0..1), charging, dim }
Scope {
    id: root

    readonly property real lowThreshold: 0.2

    // The Apple-style symbols font is optional (it cannot be redistributed, see the README);
    // without it the Material icons are used.
    readonly property bool symbolsReady: symbolsFont.status === FontLoader.Ready

    FontLoader {
        id: symbolsFont

        source: Qt.resolvedUrl("../assets/fonts/devices.otf")
    }

    // Material fallback icon for devices without bundled artwork.
    function iconFor(hint: string, name: string): string {
        const s = ((hint ?? "") + " " + (name ?? "")).toLowerCase();
        if (/gam|joystick|controller|dualsense|dualshock|playstation|xbox/.test(s)) return "sports_esports";
        if (/keyboard/.test(s)) return "keyboard";
        if (/mouse|pointer|trackpad/.test(s)) return "mouse";
        if (/headphone|headset|airpods|buds|audio-card/.test(s)) return "headphones";
        if (/speaker/.test(s)) return "speaker";
        if (/phone|iphone|android/.test(s)) return "smartphone";
        if (/watch|band/.test(s)) return "watch";
        if (/tablet|ipad/.test(s)) return "tablet";
        return "bluetooth";
    }

    // SF Symbols glyph (a code point in assets/fonts/devices.otf) for the common
    // device types, or 0 to fall back to the Material icon.
    function glyphFor(hint: string, name: string): int {
        if (!root.symbolsReady)
            return 0;
        const s = ((hint ?? "") + " " + (name ?? "")).toLowerCase();
        if (/gam|joystick|controller|dualsense|dualshock|playstation|xbox/.test(s)) return 0x1006F9;
        if (/keyboard/.test(s)) return 0x100E91;
        if (/mouse|pointer|trackpad/.test(s)) return 0x100EB1;
        if (/headphone|headset|airpods max|audio-card/.test(s)) return 0x100EB9;
        if (/phone|iphone/.test(s)) return 0x100E90;
        if (/watch/.test(s)) return 0x100E97;
        return 0;
    }

    // AirPods battery, published by the airpods-battery scanner as JSON.
    // Absent or stale (> 3 min) means unknown.
    property string airpodsRaw: ""
    property real nowSec: Date.now() / 1000

    readonly property var airpods: {
        try {
            return JSON.parse(root.airpodsRaw);
        } catch (e) {
            return null;
        }
    }

    // Staleness is checked against this, so an old reading ages out on its own.
    Timer {
        interval: 5000
        running: true
        repeat: true
        onTriggered: root.nowSec = Date.now() / 1000
    }

    // USB devices plugged in right now (written by the airpods-battery scanner). A Bluetooth
    // device that is also plugged in over USB under the same name is charging: Bluetooth
    // itself does not report that.
    property string usbRaw: "[]"
    readonly property var usbProducts: {
        try {
            return JSON.parse(root.usbRaw);
        } catch (e) {
            return [];
        }
    }

    function pluggedIn(name: string): bool {
        const token = (name ?? "").toLowerCase().split(/\s+/)[0];
        return token.length >= 4 && root.usbProducts.some(p => p.indexOf(token) !== -1);
    }

    // Charging inferred from the battery level: Bluetooth gives no charge state. A level that
    // goes up means charging until it drops, or stays flat for 15 minutes.
    property var lastLevel: ({})
    property var chargeUntil: ({})
    property int chargeTick: 0

    function chargingByTrend(name: string): bool {
        root.chargeTick;  // re-evaluate when the samples change
        return Date.now() < (root.chargeUntil[name] ?? 0);
    }

    Timer {
        interval: 20000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            const now = Date.now();
            for (const d of Bluetooth.devices.values) {
                if (!d.connected || !d.batteryAvailable)
                    continue;
                const level = Math.round(d.battery * 100);
                const before = root.lastLevel[d.name];
                if (before !== undefined) {
                    if (level > before)
                        root.chargeUntil[d.name] = now + 15 * 60 * 1000;
                    else if (level < before)
                        root.chargeUntil[d.name] = 0;
                }
                root.lastLevel[d.name] = level;
            }
            root.chargeTick++;
        }
    }

    FileView {
        id: usbFile

        path: (Quickshell.env("XDG_RUNTIME_DIR") ?? "/tmp") + "/usb-products.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: root.usbRaw = text()
    }

    FileView {
        id: airpodsFile

        path: (Quickshell.env("XDG_RUNTIME_DIR") ?? "/tmp") + "/airpods-battery.json"
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            root.airpodsRaw = text();
            root.nowSec = Date.now() / 1000;
        }
    }

    readonly property var entries: {
        const out = [];
        for (const d of Bluetooth.devices.values) {
            if (/airpods|beats/i.test(d.name ?? "")) {
                // Shown while connected, or while the lid is open and they are advertising.
                if (AirPods.isFresh(root.airpods, root.nowSec, d.connected)) {
                    for (const e of AirPods.entries(root.airpods, d.name, qsTr("Case"))) {
                        if (!root.symbolsReady)
                            e.glyph = 0;
                        out.push(e);
                    }
                    continue;
                }
            }
            if (!d.connected)
                continue;
            // No battery reading: nothing to show (no empty 0% ring).
            if (!d.batteryAvailable)
                continue;
            out.push({
                name: d.name,
                label: "",
                glyph: root.glyphFor(d.icon, d.name),
                icon: root.iconFor(d.icon, d.name),
                known: true,
                level: d.battery,
                charging: root.pluggedIn(d.name) || root.chargingByTrend(d.name),
                dim: false
            });
        }
        for (const u of UPower.devices.values) {
            if (u.isLaptopBattery || u.type === UPowerDeviceType.LinePower || !u.isPresent)
                continue;
            const key = (u.model ?? "").toLowerCase();
            // Already listed through BlueZ under the same name.
            if (out.find(e => e.name && e.name.toLowerCase() === key))
                continue;
            out.push({
                name: u.model || qsTr("Device"),
                label: "",
                glyph: root.glyphFor("", u.model),
                icon: root.iconFor("", u.model),
                known: true,
                level: u.percentage,
                charging: u.state === UPowerDeviceState.Charging || root.pluggedIn(u.model),
                dim: false
            });
        }
        return out;
    }
}
