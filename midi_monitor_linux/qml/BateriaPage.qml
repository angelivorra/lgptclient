import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root

    property string lastEvent: "Esperando eventos..."

    function lightPad(padName) {
        switch (padName) {
            case "bombo":  bomboPad.lightOn();  break
            case "caja1":  caja1Pad.lightOn();  break
            case "caja2":  caja2Pad.lightOn();  break
            case "crash":  crashPad.lightOn();  break
        }
        root.lastEvent = "Hit: " + midiBackend.getPadLabel(padName)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        RowLayout {
            Controls.Label {
                text: "Visualización de Batería"
                font.italic: true
                color: Kirigami.Theme.disabledTextColor
            }
            Item { Layout.fillWidth: true }
            Controls.Label {
                text: "Canal MIDI: " + midiBackend.getBateriaChannel()
                font.pixelSize: 11
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // ── Pads ─────────────────────────────────────────────────────────
        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.centerIn: parent
                spacing: 24

                // Fila superior: Crash
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter

                    DrumPad {
                        id: crashPad
                        padName: "crash"
                        label: midiBackend.getPadLabel("crash")
                        activeColor: midiBackend.getPadColor("crash")
                    }
                }

                // Fila inferior: Caja2 — Bombo — Caja1
                RowLayout {
                    Layout.alignment: Qt.AlignHCenter
                    spacing: 32

                    DrumPad {
                        id: caja2Pad
                        padName: "caja2"
                        label: midiBackend.getPadLabel("caja2")
                        activeColor: midiBackend.getPadColor("caja2")
                    }

                    DrumPad {
                        id: bomboPad
                        padName: "bombo"
                        label: midiBackend.getPadLabel("bombo")
                        activeColor: midiBackend.getPadColor("bombo")
                    }

                    DrumPad {
                        id: caja1Pad
                        padName: "caja1"
                        label: midiBackend.getPadLabel("caja1")
                        activeColor: midiBackend.getPadColor("caja1")
                    }
                }
            }
        }

        // ── Último evento ─────────────────────────────────────────────────
        Controls.Label {
            Layout.alignment: Qt.AlignHCenter
            text: root.lastEvent
            font.family: "Monospace"
            font.pixelSize: 13
            color: Kirigami.Theme.disabledTextColor
        }
    }
}
