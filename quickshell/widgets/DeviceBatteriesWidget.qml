pragma ComponentBehavior: Bound

import ".."
import QtQuick
import QtQuick.Layouts
import Caelestia.Config
import Caelestia.Components
import qs.components
import qs.components.controls
import qs.services

// Battery rings for connected peripherals, in the style of Apple's battery widget:
// rings with the device artwork inside and the percentage below. Card styling and
// colours come from the shell palette, like the other desktop widgets.
Item {
    id: root

    property var frame
    property var controller

    FontLoader {
        id: symbols

        source: Qt.resolvedUrl("../../../../assets/fonts/devices.otf")
    }

    readonly property color ringColour: Colours.palette.m3primary
    readonly property color lowColour: Colours.palette.m3error
    readonly property color textColour: Colours.palette.m3onSurface
    readonly property color iconColour: Colours.palette.m3onSurface
    readonly property color trackColour: Qt.alpha(Colours.palette.m3onSurfaceVariant, 0.25)

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
    readonly property bool wide: width > height * 1.4
    // Four devices per page in both shapes; more than that gets pages.
    readonly property int perPage: 4
    readonly property int pages: Math.max(1, Math.ceil(entries.length / perPage))
    property int page: 0
    readonly property int curPage: Math.min(page, pages - 1)
    // Empty rings pad a single page up to four slots, like the original.
    readonly property int slots: pages > 1 ? perPage : Math.max(4, entries.length)
    // The shell draws the card (this is a framed widget, like Media and Calendar), so the area
    // here is exactly the card's content area and the card always matches its box.
    readonly property real cardW: width
    readonly property real cardH: height
    readonly property real shiftX: 0
    readonly property int cols: wide ? Math.min(4, slots) : Math.min(2, slots)
    readonly property int rows: Math.ceil(slots / cols)
    // The frame already pads its content.
    readonly property real pad: 0
    // The gap between rings equals the card's own margin (contentPadding in the catalog), so the
    // spacing is the same everywhere.
    readonly property real gap: 9
    // Square card: rings only, like Apple's. Wide card: rings with percentages.
    readonly property real textH: wide ? 26 : 0
    readonly property real cellW: (cardW - pad * 2 - gap * (cols - 1)) / cols
    readonly property real cellH: (cardH - pad * 2 - gap * (rows - 1)) / rows
    readonly property real ringSize: Math.max(32, Math.min(cellW, cellH - textH) * 0.82)

    // Scroll (mouse wheel / touchpad) or swipe over the card to change pages.
    MouseArea {
        id: pager

        property real startX: 0
        property real startY: 0

        function step(dir: int): void {
            root.page = Math.max(0, Math.min(root.pages - 1, root.curPage + dir));
        }

        anchors.fill: parent
        enabled: root.pages > 1
        onWheel: wheel => {
            const d = Math.abs(wheel.angleDelta.y) >= Math.abs(wheel.angleDelta.x) ? wheel.angleDelta.y : wheel.angleDelta.x;
            if (d !== 0)
                step(d < 0 ? 1 : -1);
        }
        onPressed: mouse => {
            startX = mouse.x;
            startY = mouse.y;
        }
        onReleased: mouse => {
            const dx = mouse.x - startX, dy = mouse.y - startY;
            const d = Math.abs(dx) >= Math.abs(dy) ? dx : dy;
            if (Math.abs(d) > 30)
                step(d < 0 ? 1 : -1);
        }
    }

    // Pages are stacked vertically and slide up and down as the page changes.
    Item {
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: root.shiftX
        width: root.cardW
        height: root.cardH
        clip: true

        Item {
            width: parent.width
            y: -root.curPage * root.cardH

            Behavior on y {
                NumberAnimation {
                    duration: 380
                    easing.type: Easing.OutCubic
                }
            }

            Repeater {
                model: root.pages

                Item {
                    id: pageItem

                    required property int index
                    readonly property int pageIdx: index

                    y: index * root.cardH
                    width: root.cardW
                    height: root.cardH

                GridLayout {
                    anchors.centerIn: parent
                    columns: root.cols
                    columnSpacing: root.gap
                    rowSpacing: root.gap

                    Repeater {
                        model: root.slots

                        ColumnLayout {
                            id: cell

                            required property int index
                            readonly property var pageEntries: root.entries.slice(pageItem.pageIdx * root.perPage, (pageItem.pageIdx + 1) * root.perPage)
                            readonly property var entry: pageEntries[index] ?? null
                            readonly property bool known: entry !== null && entry.known
                            readonly property bool low: known && entry.level < DeviceBatteries.lowThreshold

                            Layout.preferredWidth: root.cellW
                            spacing: 2
                            opacity: cell.entry?.dim ? 0.38 : 1

                            DeviceRing {
                                id: ring

                                Layout.alignment: Qt.AlignHCenter
                                implicitWidth: root.ringSize
                                implicitHeight: root.ringSize
                                strokeWidth: Math.max(5, Math.round(root.ringSize * 0.1))
                                value: cell.known ? cell.entry.level : 0
                                gap: cell.entry?.charging ?? false
                                fgColour: cell.low ? root.lowColour : root.ringColour
                                trackColour: root.trackColour

                                // Device symbol from the SF Symbols font.
                                Text {
                                    anchors.centerIn: parent
                                    anchors.verticalCenterOffset: Math.round(root.ringSize * 0.03)
                                    visible: (cell.entry?.glyph ?? 0) !== 0
                                    text: visible ? String.fromCodePoint(cell.entry.glyph) + (cell.entry?.pair ? String.fromCodePoint(0x100C8D) : "") : ""
                                    font.family: symbols.name
                                    font.pixelSize: Math.round(root.ringSize * (cell.entry?.pair ? 0.34 : root.glyphScale(cell.entry?.glyph ?? 0)))
                                    color: cell.known ? root.iconColour : Qt.alpha(root.iconColour, 0.45)
                                }

                                MaterialIcon {
                                    anchors.centerIn: parent
                                    visible: cell.entry !== null && (cell.entry.glyph ?? 0) === 0
                                    text: cell.entry?.icon ?? ""
                                    fontStyle: Tokens.font.icon.large
                                    color: cell.known ? root.iconColour : Qt.alpha(root.iconColour, 0.45)
                                }

                                // Charging bolt: white, in the gap at the top middle of the ring.
                                MaterialIcon {
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    y: Math.round(ring.strokeWidth / 2 - height / 2)
                                    visible: cell.entry?.charging ?? false
                                    text: "bolt"
                                    fill: 1
                                    color: "white"
                                }
                            }

                            StyledText {
                                Layout.alignment: Qt.AlignHCenter
                                visible: root.wide && cell.entry !== null
                                text: cell.known ? Math.round(cell.entry.level * 100) + "%" : "--"
                                font: Tokens.font.title.medium
                                color: cell.low ? root.lowColour : root.textColour
                            }
                        }
                    }
                }
                }
            }
        }
    }
}
