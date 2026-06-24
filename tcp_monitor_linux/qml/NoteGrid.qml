import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts

// Grid 12 columnas × 8 filas = 96 notas (C1-B8, MIDI 12-107)
// Cada celda se ilumina 200 ms al recibir la nota.
Item {
    id: root

    property var noteColorCallback: function(note) { return "#4caf50" }

    readonly property int cols: 12
    readonly property int rows: 8
    readonly property int cellW: 46
    readonly property int cellH: 34
    readonly property int gap: 3
    readonly property int noteOffset: 12   // C1 = MIDI 12

    implicitWidth:  cols * (cellW + gap) - gap
    implicitHeight: rows * (cellH + gap) - gap

    // Nombres de nota para la etiqueta de columna
    readonly property var noteNames: ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

    function lightNote(note) {
        var idx = note - noteOffset
        if (idx >= 0 && idx < cols * rows) {
            cells.itemAt(idx).flash()
        }
    }

    // Etiquetas de columna (C, C#, D ...)
    Row {
        id: colHeaders
        y: 0
        spacing: root.gap
        Repeater {
            model: root.cols
            Controls.Label {
                width: root.cellW
                text: root.noteNames[index]
                horizontalAlignment: Text.AlignHCenter
                font.pixelSize: 9
                color: (root.noteNames[index].length > 1) ? "#888" : "#ccc"
            }
        }
    }

    // Celdas de notas
    Repeater {
        id: cells
        model: root.cols * root.rows

        delegate: Item {
            id: cell

            readonly property int noteIndex: index
            readonly property int row: Math.floor(index / root.cols)
            readonly property int col: index % root.cols
            readonly property int midiNote: index + root.noteOffset
            property bool lit: false

            x: col * (root.cellW + root.gap)
            y: (root.rows - 1 - row) * (root.cellH + root.gap) + 14  // 14 = header height

            width:  root.cellW
            height: root.cellH

            function flash() {
                lit = true
                offTimer.restart()
            }

            Timer {
                id: offTimer
                interval: 200
                onTriggered: cell.lit = false
            }

            Rectangle {
                anchors.fill: parent
                radius: 4
                color: cell.lit ? root.noteColorCallback(cell.midiNote) : "#222"
                border.color: cell.lit ? Qt.lighter(color, 1.5) : "#3a3a3a"
                border.width: 1

                Behavior on color { ColorAnimation { duration: 60 } }

                // Octava en la primera columna
                Controls.Label {
                    visible: cell.col === 0
                    anchors { right: parent.right; bottom: parent.bottom; margins: 2 }
                    text: Math.floor(cell.midiNote / 12) - 1
                    font.pixelSize: 8
                    color: "#888"
                }
            }
        }
    }
}
