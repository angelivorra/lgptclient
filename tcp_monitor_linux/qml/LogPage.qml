import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root

    property int eventCount: 0
    property bool autoScroll: true

    function tagColor(tag) {
        switch (tag) {
            case "info":       return "#4fc3f7"
            case "success":    return "#81c784"
            case "error":      return "#e57373"
            case "warning":    return "#ffb74d"
            case "midi_note":  return "#ba68c8"
            case "midi_cc":    return "#4db6ac"
            default:           return "#aaaaaa"
        }
    }

    Connections {
        target: logModel
        function onRowsInserted() {
            root.eventCount = logModel.entryCount()
            if (root.autoScroll) {
                listView.positionViewAtEnd()
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 6

        RowLayout {
            spacing: 6
            Kirigami.Icon {
                source: "view-list-text"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            Controls.Label {
                text: "Log de todos los eventos MIDI recibidos"
                font.italic: true
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // ── Área de log ──────────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#1a1a1a"
            radius: 6
            border.color: "#333333"
            border.width: 1

            ListView {
                id: listView
                anchors.fill: parent
                anchors.margins: 6
                model: logModel
                clip: true
                spacing: 1

                // Mantiene la vista al final cuando llega nuevo item
                onCountChanged: {
                    if (root.autoScroll) {
                        positionViewAtEnd()
                    }
                }

                delegate: Row {
                    width: listView.width
                    spacing: 8

                    Controls.Label {
                        text: model.timestamp
                        color: "#4fc3f7"
                        font.family: "Monospace"
                        font.pixelSize: 11
                    }

                    Controls.Label {
                        width: parent.width - 110
                        text: model.text
                        color: root.tagColor(model.tag)
                        font.family: "Monospace"
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }

                Controls.ScrollBar.vertical: Controls.ScrollBar {}
            }
        }

        // ── Barra inferior ───────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true

            Controls.Label {
                text: "Eventos: " + root.eventCount
                color: Kirigami.Theme.disabledTextColor
            }

            Item { Layout.fillWidth: true }

            Controls.CheckBox {
                text: "Auto-scroll"
                checked: root.autoScroll
                onCheckedChanged: root.autoScroll = checked
            }

            Controls.Button {
                text: "Limpiar"
                icon.name: "edit-clear-all"
                onClicked: {
                    logModel.clear()
                    root.eventCount = 0
                }
            }
        }
    }
}
