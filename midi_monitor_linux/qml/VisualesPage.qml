import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root

    property string imagePath: ""
    property string ccInfo: "Esperando eventos CC..."
    property string pathInfo: ""

    function updateVisual(imgPath, channel, cc, value) {
        root.ccInfo = "Canal: %1 | CC: %2 | Valor: %3"
            .arg(channel + 1).arg(cc).arg(value)

        root.imagePath = imgPath

        if (imgPath) {
            // Mostrar las últimas 3 partes de la ruta
            var parts = imgPath.split("/")
            root.pathInfo = parts.slice(-3).join("/")
        } else {
            var padded_cc  = String(cc).padStart(3, "0")
            var padded_val = String(value).padStart(3, "0")
            root.pathInfo = "No encontrado: " + padded_cc + "/" + padded_val
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 6

        // ── Info de evento CC ─────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true

            Controls.Label {
                text: root.ccInfo
                font.bold: true
                font.pixelSize: 15
                font.family: "Monospace"
            }

            Item { Layout.fillWidth: true }

            Controls.Label {
                text: root.pathInfo
                font.pixelSize: 11
                font.family: "Monospace"
                color: Kirigami.Theme.disabledTextColor
                elide: Text.ElideLeft
                Layout.maximumWidth: 400
            }
        }

        // ── Área de imagen ────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#0a0a0a"
            radius: 6
            border.color: "#333333"
            border.width: 1

            Image {
                id: displayImage
                anchors.fill: parent
                anchors.margins: 4
                source: root.imagePath ? ("file://" + root.imagePath) : ""
                fillMode: Image.PreserveAspectFit
                smooth: true
                asynchronous: true
                visible: root.imagePath !== ""

                Controls.BusyIndicator {
                    anchors.centerIn: parent
                    running: parent.status === Image.Loading
                    visible: running
                }
            }

            Controls.Label {
                anchors.centerIn: parent
                text: "Sin imagen\n\nEnvía un evento CC MIDI\n(canales 1–6, cualquier CC)"
                horizontalAlignment: Text.AlignHCenter
                color: "#444444"
                font.pixelSize: 17
                visible: root.imagePath === ""
            }
        }
    }
}
