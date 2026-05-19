import QtQuick
import QtQuick.Controls as Controls

Item {
    id: root
    width: 130
    height: 130

    property string padName: ""
    property string label: ""
    property color activeColor: "#888888"
    property bool lit: false

    function lightOn() {
        root.lit = true
        offTimer.restart()
    }

    Timer {
        id: offTimer
        interval: 150
        onTriggered: root.lit = false
    }

    Rectangle {
        anchors.fill: parent
        anchors.margins: 8
        radius: width / 2
        color: root.lit ? root.activeColor : "#2a2a2a"
        border.color: root.lit ? Qt.lighter(root.activeColor, 1.4) : "#444444"
        border.width: 3

        Behavior on color {
            ColorAnimation { duration: 60 }
        }
        Behavior on border.color {
            ColorAnimation { duration: 60 }
        }

        Controls.Label {
            anchors.centerIn: parent
            text: root.label
            color: root.lit ? "white" : "#777777"
            font.bold: true
            font.pixelSize: 15

            Behavior on color {
                ColorAnimation { duration: 60 }
            }
        }
    }
}
