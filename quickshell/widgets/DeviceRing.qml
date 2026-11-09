import QtQuick
import QtQuick.Shapes

// One continuous battery ring: a full track circle with the charge drawn over it,
// starting at the top and running clockwise. While charging, a gap is left at the
// top for the bolt.
Item {
    id: root

    property real value: 0
    property real strokeWidth: 8
    property bool gap: false
    property color fgColour: "white"
    property color trackColour: "#33ffffff"

    readonly property real gapDeg: gap ? 26 : 0
    readonly property real radius: (Math.min(width, height) - strokeWidth) / 2
    readonly property real fullSweep: 360 - 2 * gapDeg

    implicitWidth: 64
    implicitHeight: 64

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            fillColor: "transparent"
            strokeColor: root.trackColour
            strokeWidth: root.strokeWidth
            capStyle: ShapePath.RoundCap

            PathAngleArc {
                centerX: root.width / 2
                centerY: root.height / 2
                radiusX: root.radius
                radiusY: root.radius
                startAngle: -90 + root.gapDeg
                sweepAngle: root.fullSweep
            }
        }

        ShapePath {
            fillColor: "transparent"
            strokeColor: root.value > 0.004 ? root.fgColour : "transparent"
            strokeWidth: root.strokeWidth
            capStyle: ShapePath.RoundCap

            PathAngleArc {
                centerX: root.width / 2
                centerY: root.height / 2
                radiusX: root.radius
                radiusY: root.radius
                startAngle: -90 + root.gapDeg
                sweepAngle: root.fullSweep * Math.max(0, Math.min(1, root.value))
            }
        }
    }
}
