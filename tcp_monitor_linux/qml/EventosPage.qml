import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Item {
    id: root

    // Llamados desde main.qml mediante las señales del backend
    function onNoteHit(note, channel) {
        if (note >= 0 && note < 128) {
            noteGrid.lightNote(note)
        }
    }

    function onCcReceived(controller, channel, value) {
        ccList.addEntry(controller, channel, value)
    }

    // Colores por octava (C1..B1, C2..B2 ...)
    readonly property var octaveColors: [
        "#e57373", "#ffb74d", "#fff176",
        "#81c784", "#4fc3f7", "#9575cd", "#f48fb1", "#a1887f"
    ]

    function noteColor(note) {
        return octaveColors[Math.floor(note / 12) % octaveColors.length]
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 8

        // ── Cabecera ─────────────────────────────────────────────────────
        RowLayout {
            spacing: 6
            Kirigami.Icon {
                source: "network-wired"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            Controls.Label {
                text: "Notas MIDI activas (C1–B8)"
                font.italic: true
                color: Kirigami.Theme.disabledTextColor
            }
        }

        // ── Grid de notas ────────────────────────────────────────────────
        Item {
            Layout.fillWidth: true
            implicitHeight: noteGrid.implicitHeight + 8

            NoteGrid {
                id: noteGrid
                anchors.horizontalCenter: parent.horizontalCenter
                noteColorCallback: root.noteColor
            }
        }

        Kirigami.Separator { Layout.fillWidth: true }

        // ── Últimos CC ───────────────────────────────────────────────────
        RowLayout {
            spacing: 6
            Kirigami.Icon {
                source: "media-playlist-consecutive"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            Controls.Label {
                text: "Últimos Control Change"
                font.italic: true
                color: Kirigami.Theme.disabledTextColor
            }
        }

        CcStrip {
            id: ccList
            Layout.fillWidth: true
            implicitHeight: 64
        }
    }
}
