import "../../background/desktopicons"
import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import qs.components
import qs.services

// Battery rings for connected peripherals; data comes from the DeviceBatteries service.
Item {
    id: root

    readonly property var entries: DeviceBatteries.entries

    // Wide symbols (keyboard, controller, case, headphones) look too big at the normal
    // glyph size, so they are scaled down.
    function glyphScale(glyph: int): real {
        switch (glyph) {
        case 0x100E91: return 0.34;  // keyboard
        case 0x1006F9: return 0.36;  // game controller
        case 0x100E6B: return 0.38;  // charging case
        case 0x100EB9: return 0.40;  // headphones
        case 0x100EB1: return 0.42;  // mouse
        default: return 0.5;
        }
    }
    readonly property int ringSize: Math.round(Tokens.sizes.bar.innerWidth * 0.85)

    visible: entries.length > 0
    implicitHeight: Tokens.sizes.bar.innerWidth
    implicitWidth: visible ? row.implicitWidth + Tokens.padding.small : 0

    FontLoader {
        id: symbols

        source: Qt.resolvedUrl("../../../assets/fonts/devices.otf")
    }

    RowLayout {
        id: row

        anchors.centerIn: parent
        spacing: Tokens.spacing.small

        Repeater {
            model: root.entries

            RowLayout {
                id: cell

                required property var modelData
                readonly property bool low: modelData.known && modelData.level < DeviceBatteries.lowThreshold

                spacing: 2
                opacity: modelData.dim ? 0.38 : 1

                DeviceRing {
                    implicitWidth: root.ringSize
                    implicitHeight: root.ringSize
                    strokeWidth: 3
                    value: cell.modelData.known ? cell.modelData.level : 0
                    gap: cell.modelData.charging
                    fgColour: cell.low ? Colours.palette.m3error : Colours.palette.m3primary
                    trackColour: Qt.alpha(Colours.palette.m3onSurfaceVariant, 0.25)

                    Text {
                        anchors.centerIn: parent
                        visible: (cell.modelData.glyph ?? 0) !== 0
                        text: visible ? String.fromCodePoint(cell.modelData.glyph) + (cell.modelData.pair ? String.fromCodePoint(0x100C8D) : "") : ""
                        font.family: symbols.name
                        font.pixelSize: Math.round(root.ringSize * (cell.modelData.pair ? 0.34 : root.glyphScale(cell.modelData.glyph)))
                        color: Colours.palette.m3onSurface
                    }

                    MaterialIcon {
                        anchors.centerIn: parent
                        visible: (cell.modelData.glyph ?? 0) === 0
                        text: cell.modelData.icon
                        color: Colours.palette.m3onSurface
                    }
                }

                StyledText {
                    font.bold: true
                    text: cell.modelData.known ? Math.round(cell.modelData.level * 100) + "%" : "--"
                    color: cell.low ? Colours.palette.m3error : Colours.palette.m3onSurface
                }
            }
        }
    }
}
