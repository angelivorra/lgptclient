import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: "TCP Monitor"
    width: 1050
    height: 750
    minimumWidth: 800
    minimumHeight: 600

    property bool connected: false
    property string statusText: "Desconectado"
    property real bpm: 0.0
    property real latency: 0.0
    property bool playing: false

    Connections {
        target: tcpBackend

        function onConnectionChanged(isConnected, addr) {
            root.connected = isConnected
            root.statusText = isConnected ? "Conectado: " + addr : "Desconectado"
        }

        function onBpmChanged(value) {
            root.bpm = value
        }

        function onLatencyChanged(value) {
            root.latency = value
        }

        function onPlayStateChanged(isPlaying) {
            root.playing = isPlaying
        }

        function onNoteHit(note, channel) {
            eventosPage.onNoteHit(note, channel)
        }

        function onCcReceived(controller, channel, value) {
            eventosPage.onCcReceived(controller, channel, value)
        }

        function onStatsChanged(notas, cc, bpmMsgs) {
            estadoPage.updateStats(notas, cc, bpmMsgs)
        }

        function onErrorEvent(text, tag) {
            estadoPage.addError(text)
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        // ── Barra de sistema ─────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Kirigami.Chip {
                text: tcpBackend.getSystemInfo()
                closable: false
            }

            Kirigami.Chip {
                text: root.connected ? "● Conectado" : "○ Desconectado"
                closable: false
                checkable: false
                opacity: root.connected ? 1.0 : 0.5
            }

            Kirigami.Chip {
                text: root.playing ? "▶ Playing" : "■ Stop"
                closable: false
                checkable: false
                opacity: root.playing ? 1.0 : 0.5
            }

            Item { Layout.fillWidth: true }

            Kirigami.Chip {
                id: bpmChip
                text: root.bpm > 0 ? "♩ = " + Math.round(root.bpm) + " BPM" : "♩ = -- BPM"
                closable: false
                checkable: false
                enabled: root.bpm > 0
            }

            Kirigami.Chip {
                id: latChip
                readonly property color latColor: root.latency < 50
                    ? "#4caf50"
                    : root.latency < 150 ? "#ffb74d" : "#e57373"
                text: "⏱ " + Math.round(root.latency) + " ms"
                closable: false
                checkable: false
                visible: root.connected
            }
        }

        // ── Panel de conexión ────────────────────────────────────────────
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: RowLayout {
                spacing: 10

                Rectangle {
                    width: 14; height: 14; radius: 7
                    color: root.connected ? "#4caf50" : "#9e9e9e"
                    Behavior on color { ColorAnimation { duration: 200 } }
                }

                Controls.Label { text: "Host:"; font.bold: true }

                Controls.TextField {
                    id: hostField
                    text: tcpBackend.getDefaultHost()
                    placeholderText: "IP del servidor"
                    enabled: !root.connected
                    implicitWidth: 160
                }

                Controls.Label { text: "Puerto:"; font.bold: true }

                Controls.TextField {
                    id: portField
                    text: tcpBackend.getDefaultPort()
                    placeholderText: "puerto"
                    enabled: !root.connected
                    implicitWidth: 70
                    validator: IntValidator { bottom: 1; top: 65535 }
                }

                Controls.Button {
                    text: root.connected ? "Desconectar" : "Conectar"
                    icon.name: root.connected ? "network-disconnect" : "network-connect"
                    highlighted: !root.connected
                    onClicked: {
                        if (root.connected) {
                            tcpBackend.disconnectFromServer()
                        } else {
                            tcpBackend.connectToServer(hostField.text, parseInt(portField.text))
                        }
                    }
                }

                Controls.Label {
                    text: root.statusText
                    color: root.connected
                        ? Kirigami.Theme.positiveTextColor
                        : Kirigami.Theme.disabledTextColor
                }
            }
        }

        // ── Pestañas ─────────────────────────────────────────────────────
        Controls.TabBar {
            id: tabBar
            Layout.fillWidth: true

            component BigTab: Controls.TabButton {
                display: Controls.AbstractButton.TextBesideIcon
                implicitHeight: Kirigami.Units.gridUnit * 3
                padding: Kirigami.Units.largeSpacing
                icon.width: Kirigami.Units.iconSizes.medium
                icon.height: Kirigami.Units.iconSizes.medium
                font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.3
                font.bold: checked
            }

            BigTab { text: "Log";     icon.name: "view-list-text" }
            BigTab { text: "Eventos"; icon.name: "network-wired" }
            BigTab { text: "Estado";  icon.name: "dialog-information" }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            LogPage     { id: logPage }
            EventosPage { id: eventosPage }
            EstadoPage  {
                id: estadoPage
                bpm:     root.bpm
                latency: root.latency
                playing: root.playing
            }
        }
    }
}
