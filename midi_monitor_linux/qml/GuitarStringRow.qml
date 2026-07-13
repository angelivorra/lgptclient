import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Una cuerda del mástil: etiqueta + cejuela (aire) + N trastes.
// El visor la identifica por `channel` (la cuerda c del firmware emite en
// CANALES[c]); el traste sale de nota - openNote.
Item {
    id: root

    property int channel: 0
    property int openNote: 59
    property string stringLabel: ""
    property int numFrets: 17

    implicitWidth: rowLayout.implicitWidth
    implicitHeight: rowLayout.implicitHeight

    function setPressed(fret, on) {
        var cell = fretRep.itemAt(fret)
        if (cell)
            cell.pressed = on
    }

    function pluck(fret) {
        var cell = fretRep.itemAt(fret)
        if (cell)
            cell.pluck()
    }

    RowLayout {
        id: rowLayout
        anchors.fill: parent
        spacing: 2

        Controls.Label {
            Layout.preferredWidth: 66
            text: root.stringLabel
            horizontalAlignment: Text.AlignRight
            font.bold: true
            font.pixelSize: 12
            color: Kirigami.Theme.disabledTextColor
        }

        Repeater {
            id: fretRep
            model: root.numFrets + 1
            FretCell {
                fretNumber: index
            }
        }
    }
}
