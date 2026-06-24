import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root

    // Propiedades alimentadas desde main.qml
    property real  bpm:     0.0
    property real  latency: 0.0
    property bool  playing: false

    property int statNotas: 0
    property int statCc:    0
    property int statBpm:   0
    property var errors:    []

    function updateStats(notas, cc, bpmMsgs) {
        root.statNotas = notas
        root.statCc    = cc
        root.statBpm   = bpmMsgs
    }

    function addError(text) {
        var updated = root.errors.slice()
        updated.unshift(text)
        if (updated.length > 10) updated.pop()
        root.errors = updated
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        // ── Cabecera ─────────────────────────────────────────────────────
        RowLayout {
            spacing: 6
            Kirigami.Icon {
                source: "dialog-information"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            Controls.Label {
                text: "Estado del servidor"
                font.italic: true
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // ── BPM + play state + latencia ───────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            // BPM grande
            Kirigami.AbstractCard {
                Layout.preferredWidth: 220

                contentItem: ColumnLayout {
                    spacing: 4

                    Controls.Label {
                        text: "BPM"
                        font.bold: true
                        color: Kirigami.Theme.disabledTextColor
                        Layout.alignment: Qt.AlignHCenter
                    }

                    Controls.Label {
                        text: root.bpm > 0 ? Math.round(root.bpm) : "--"
                        font.family: "Monospace"
                        font.pixelSize: 52
                        font.bold: true
                        color: "#4fc3f7"
                        Layout.alignment: Qt.AlignHCenter
                    }
                }
            }

            // Estado play + latencia
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 8

                Kirigami.AbstractCard {
                    Layout.fillWidth: true
                    contentItem: RowLayout {
                        spacing: 10
                        Rectangle {
                            width: 18; height: 18; radius: 9
                            color: root.playing ? "#4caf50" : "#9e9e9e"
                            Behavior on color { ColorAnimation { duration: 200 } }
                        }
                        Controls.Label {
                            text: root.playing ? "▶  PLAYING" : "■  STOPPED"
                            font.bold: true
                            font.pixelSize: 16
                        }
                    }
                }

                Kirigami.AbstractCard {
                    Layout.fillWidth: true
                    contentItem: ColumnLayout {
                        spacing: 4

                        Controls.Label {
                            text: "Latencia media"
                            font.bold: true
                            color: Kirigami.Theme.disabledTextColor
                        }

                        RowLayout {
                            spacing: 8

                            Controls.Label {
                                text: Math.round(root.latency) + " ms"
                                font.family: "Monospace"
                                font.pixelSize: 22
                                color: root.latency < 50  ? "#4caf50"
                                     : root.latency < 150 ? "#ffb74d" : "#e57373"
                            }

                            Rectangle {
                                Layout.fillWidth: true
                                height: 12
                                radius: 6
                                color: "#222"
                                Rectangle {
                                    readonly property real pct: Math.min(1.0, root.latency / 300)
                                    width: parent.width * pct
                                    height: parent.height
                                    radius: parent.radius
                                    color: pct < 0.17 ? "#4caf50" : pct < 0.5 ? "#ffb74d" : "#e57373"
                                    Behavior on width { NumberAnimation { duration: 150 } }
                                }
                            }
                        }
                    }
                }
            }
        }

        // ── Estadísticas desde el último START ────────────────────────────
        Kirigami.AbstractCard {
            Layout.fillWidth: true
            contentItem: RowLayout {
                spacing: 24

                Controls.Label {
                    text: "Desde último START:"
                    font.bold: true
                    color: Kirigami.Theme.disabledTextColor
                }

                Repeater {
                    model: [
                        { label: "NOTA", value: root.statNotas, color: "#ba68c8" },
                        { label: "CC",   value: root.statCc,    color: "#4db6ac" },
                        { label: "BPM",  value: root.statBpm,   color: "#4fc3f7" },
                    ]
                    delegate: RowLayout {
                        spacing: 4
                        Controls.Label { text: modelData.label + ":"; color: modelData.color; font.bold: true }
                        Controls.Label { text: modelData.value; font.family: "Monospace" }
                    }
                }

                Item { Layout.fillWidth: true }

                Controls.Label {
                    text: "Errores: " + tcpBackend.getErrorCount()
                    color: tcpBackend.getErrorCount() > 0 ? "#e57373" : Kirigami.Theme.disabledTextColor
                    font.bold: tcpBackend.getErrorCount() > 0
                }
            }
        }

        // ── Últimos errores ───────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#1a1a1a"
            radius: 6
            border.color: "#333"
            border.width: 1
            visible: root.errors.length > 0

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 8
                spacing: 4

                Controls.Label {
                    text: "Últimos errores / advertencias"
                    font.bold: true
                    color: Kirigami.Theme.disabledTextColor
                }

                Repeater {
                    model: root.errors
                    delegate: Controls.Label {
                        text: "⚠  " + modelData
                        color: "#ffb74d"
                        font.family: "Monospace"
                        font.pixelSize: 11
                    }
                }
            }
        }

        Controls.Label {
            Layout.alignment: Qt.AlignHCenter
            text: "Sin errores registrados"
            color: "#4caf50"
            font.italic: true
            visible: root.errors.length === 0
        }

        Item { Layout.fillHeight: true }
    }
}
