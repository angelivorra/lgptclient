import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts

// Muestra los últimos N eventos CC como tarjetas con barra de valor.
Item {
    id: root

    readonly property int maxItems: 8

    ListModel { id: ccModel }

    function addEntry(controller, channel, value) {
        // Si ya existe ese CC, actualizar en vez de añadir
        for (var i = 0; i < ccModel.count; i++) {
            if (ccModel.get(i).controller === controller && ccModel.get(i).channel === channel) {
                ccModel.setProperty(i, "value", value)
                return
            }
        }
        if (ccModel.count >= maxItems) {
            ccModel.remove(0)
        }
        ccModel.append({ "controller": controller, "channel": channel, "value": value })
    }

    ListView {
        anchors.fill: parent
        model: ccModel
        orientation: ListView.Horizontal
        spacing: 6
        clip: true

        delegate: Rectangle {
            width: 90
            height: root.height - 4
            radius: 6
            color: "#1e1e1e"
            border.color: "#333"
            border.width: 1

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 6
                spacing: 2

                Controls.Label {
                    text: "CC " + model.controller
                    font.bold: true
                    font.pixelSize: 12
                    color: "#4db6ac"
                    Layout.alignment: Qt.AlignHCenter
                }

                Controls.Label {
                    text: "Ch " + (model.channel + 1)
                    font.pixelSize: 10
                    color: "#888"
                    Layout.alignment: Qt.AlignHCenter
                }

                // Barra de valor
                Rectangle {
                    Layout.fillWidth: true
                    height: 8
                    radius: 4
                    color: "#333"

                    Rectangle {
                        width: parent.width * (model.value / 127)
                        height: parent.height
                        radius: parent.radius
                        color: "#4db6ac"
                        Behavior on width { NumberAnimation { duration: 80 } }
                    }
                }

                Controls.Label {
                    text: model.value
                    font.pixelSize: 11
                    color: "#ccc"
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }
    }
}
