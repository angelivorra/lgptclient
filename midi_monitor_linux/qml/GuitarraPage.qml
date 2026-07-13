import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Visor de la Roboguitarra. Traduce los eventos MIDI del mástil a un traste
// iluminado, un flash al puntear, un indicador de pitch bend (whammy del
// joystick) y dos medidores de CC (reverb 91 / chorus 93).
Item {
    id: root

    // Debe coincidir con config.py y main.cpp: 3 cuerdas, una por canal.
    // channel = CANALES[c]; openNote = NOTA_AIRE[c].
    readonly property int numFrets: 17
    readonly property var strings: [
        { channel: 0, openNote: 64, label: "1ª · Mi4" },
        { channel: 1, openNote: 59, label: "2ª · Si3" },
        { channel: 2, openNote: 55, label: "3ª · Sol3" }
    ]
    readonly property var noteNames: ["C", "C#", "D", "D#", "E", "F", "F#",
                                      "G", "G#", "A", "A#", "B"]

    property string lastEvent: "Esperando eventos..."
    property int currentChannel: -1
    property int bendValue: 0        // -8192..8191, centro 0
    property int reverbValue: 0      // CC 91, 0..127
    property int chorusValue: 0      // CC 93, 0..127

    function _noteName(note) {
        return noteNames[note % 12] + (Math.floor(note / 12) - 1)
    }

    // Devuelve la fila (GuitarStringRow) cuyo canal coincide, o null.
    function _rowForChannel(channel) {
        for (var i = 0; i < stringRepeater.count; i++) {
            var r = stringRepeater.itemAt(i)
            if (r && r.channel === channel)
                return r
        }
        return null
    }

    // La cuerda se identifica por canal; fret 0 = aire (nut), 1..numFrets = trastes.
    function noteOn(note, channel, velocity) {
        var row = _rowForChannel(channel)
        if (!row)
            return
        var fret = note - row.openNote
        if (fret < 0 || fret > root.numFrets)
            return
        row.setPressed(fret, true)
        row.pluck(fret)
        root.currentChannel = channel
        root.lastEvent = row.stringLabel
                         + " · " + (fret === 0 ? "aire" : "traste " + fret)
                         + " · " + root._noteName(note)
                         + " · Ch " + (channel + 1)
    }

    function noteOff(note, channel) {
        var row = _rowForChannel(channel)
        if (!row)
            return
        var fret = note - row.openNote
        if (fret < 0 || fret > root.numFrets)
            return
        row.setPressed(fret, false)
    }

    function setBend(pitch) {
        root.bendValue = pitch
    }

    function setCC(control, value) {
        if (control === 91)
            root.reverbValue = value
        else if (control === 93)
            root.chorusValue = value
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 12

        // ── Cabecera ──────────────────────────────────────────────────────
        RowLayout {
            spacing: 6
            Kirigami.Icon {
                source: "audio-input-microphone"
                Layout.preferredWidth: Kirigami.Units.iconSizes.small
                Layout.preferredHeight: Kirigami.Units.iconSizes.small
            }
            Controls.Label {
                text: "Visualización de la Guitarra"
                font.italic: true
                color: Kirigami.Theme.disabledTextColor
            }
            Item { Layout.fillWidth: true }
            Kirigami.Chip {
                text: root.currentChannel >= 0
                      ? "Canal MIDI " + (root.currentChannel + 1)
                      : "Sin nota"
                closable: false
                checkable: false
            }
        }

        Item { Layout.preferredHeight: 4 }

        // ── Mástil (una fila por cuerda) ───────────────────────────────────
        Controls.ScrollView {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignHCenter
            Layout.preferredHeight: mastil.implicitHeight
            contentWidth: mastil.implicitWidth
            Controls.ScrollBar.vertical.policy: Controls.ScrollBar.AlwaysOff

            Column {
                id: mastil
                spacing: 4

                Repeater {
                    id: stringRepeater
                    model: root.strings
                    GuitarStringRow {
                        channel: modelData.channel
                        openNote: modelData.openNote
                        stringLabel: modelData.label
                        numFrets: root.numFrets
                    }
                }
            }
        }

        Controls.Label {
            Layout.alignment: Qt.AlignHCenter
            text: root.lastEvent
            font.family: "Monospace"
            font.pixelSize: 14
            color: Kirigami.Theme.textColor
        }

        Item { Layout.fillHeight: true }

        // ── Pitch bend (whammy del joystick) ───────────────────────────────
        ColumnLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 24
            Layout.rightMargin: 24
            spacing: 4

            Controls.Label {
                text: "Pitch bend (joystick · global a las 3 cuerdas)"
                font.bold: true
                color: Kirigami.Theme.disabledTextColor
                font.pixelSize: 12
            }

            Rectangle {
                Layout.fillWidth: true
                height: 26
                radius: 4
                color: "#222222"
                border.color: "#444444"
                border.width: 1

                // Línea central de reposo.
                Rectangle {
                    width: 2
                    height: parent.height
                    anchors.horizontalCenter: parent.horizontalCenter
                    color: "#555555"
                }

                // Indicador que se desplaza según el bend (-8192..8191).
                Rectangle {
                    id: bendKnob
                    width: 10
                    height: parent.height - 6
                    y: 3
                    radius: 3
                    color: "#3498db"
                    // 0 → centro; ±8192 → borde. Se limita al ancho del carril.
                    x: {
                        var half = (parent.width - width) / 2
                        var off = root.bendValue / 8192 * half
                        return half + off
                    }
                    Behavior on x { NumberAnimation { duration: 40 } }
                }
            }
        }

        // ── Medidores de CC (joystick eje A5) ──────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 24
            Layout.rightMargin: 24
            Layout.bottomMargin: 12
            spacing: 24

            CcMeter {
                Layout.fillWidth: true
                label: "Reverb (CC 91)"
                value: root.reverbValue
                fillColor: "#2ecc71"
            }
            CcMeter {
                Layout.fillWidth: true
                label: "Chorus (CC 93)"
                value: root.chorusValue
                fillColor: "#9b59b6"
            }
        }
    }

    // Medidor horizontal 0..127 con relleno animado (estilo CcStrip).
    component CcMeter: ColumnLayout {
        property string label: ""
        property int value: 0
        property color fillColor: "#2ecc71"
        spacing: 4

        RowLayout {
            Layout.fillWidth: true
            Controls.Label {
                text: label
                font.bold: true
                font.pixelSize: 12
                color: Kirigami.Theme.disabledTextColor
            }
            Item { Layout.fillWidth: true }
            Controls.Label {
                text: value
                font.family: "Monospace"
                font.pixelSize: 12
                color: Kirigami.Theme.textColor
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: 20
            radius: 4
            color: "#222222"
            border.color: "#444444"
            border.width: 1

            Rectangle {
                height: parent.height - 4
                y: 2
                x: 2
                radius: 3
                width: (parent.width - 4) * (value / 127.0)
                color: fillColor
                Behavior on width { NumberAnimation { duration: 80 } }
            }
        }
    }
}
