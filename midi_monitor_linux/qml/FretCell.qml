import QtQuick
import QtQuick.Controls as Controls

// Una celda del mástil. `fretNumber` 0 = cuerda al aire (nut), 1..17 = trastes.
// `pressed` = dedo apoyado (sostenido); pluck() = flash breve al puntear.
Item {
    id: root
    width: fretNumber === 0 ? 48 : 40
    height: 58

    property int fretNumber: 0
    property bool pressed: false
    property color pressColor: "#f39c12"    // dedo apoyado
    property color pluckColor: "#ffd34d"    // punteo (flash)
    readonly property bool isOpen: fretNumber === 0
    // Puntos de posición clásicos de una guitarra.
    readonly property bool hasDot: fretNumber === 3 || fretNumber === 5
                                   || fretNumber === 7 || fretNumber === 9
                                   || fretNumber === 12 || fretNumber === 15

    property bool _plucking: false

    function pluck() {
        root._plucking = true
        offTimer.restart()
    }

    Timer {
        id: offTimer
        interval: 150
        onTriggered: root._plucking = false
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 3
        radius: 6
        color: root._plucking ? root.pluckColor
               : root.pressed ? root.pressColor
               : (root.isOpen ? "#20303a" : "#2a2a2a")
        border.width: root.isOpen ? 3 : 2
        border.color: root._plucking ? Qt.lighter(root.pluckColor, 1.4)
                      : root.pressed ? Qt.lighter(root.pressColor, 1.3)
                      : (root.isOpen ? "#3a5060" : "#444444")

        Behavior on color { ColorAnimation { duration: 60 } }
        Behavior on border.color { ColorAnimation { duration: 60 } }

        // Marca de posición (traste con punto).
        Rectangle {
            visible: root.hasDot && !root.pressed && !root._plucking
            anchors.centerIn: parent
            width: 10
            height: 10
            radius: 5
            color: "#4a4a4a"
        }

        Controls.Label {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 4
            text: root.isOpen ? "0" : root.fretNumber
            color: (root.pressed || root._plucking) ? "#1a1a1a" : "#888888"
            font.bold: true
            font.pixelSize: 12
        }
    }
}
