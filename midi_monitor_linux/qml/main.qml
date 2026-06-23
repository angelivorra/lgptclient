import QtQuick
import QtQuick.Controls as Controls
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root
    title: "MIDI Monitor"
    width: 1000
    height: 750
    minimumWidth: 800
    minimumHeight: 600

    property bool connected: false
    property string statusText: "Desconectado"
    property var availablePorts: []
    property real bpm: 0.0

    Component.onCompleted: {
        availablePorts = midiBackend.getPorts()
    }

    function refreshPorts() {
        availablePorts = midiBackend.getPorts()
        if (availablePorts.length > 0 && portCombo.currentIndex < 0) {
            portCombo.currentIndex = 0
        }
    }

    Connections {
        target: midiBackend

        function onConnectionChanged(isConnected, portName) {
            root.connected = isConnected
            root.statusText = isConnected ? "Conectado: " + portName : "Desconectado"
        }

        function onPadHit(padName) {
            bateriaPage.lightPad(padName)
        }

        function onVisualChanged(imagePath, channel, cc, value) {
            visualesPage.updateVisual(imagePath, channel, cc, value)
        }

        function onBpmChanged(value) {
            root.bpm = value
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 8

        // ── Barra de sistema ────────────────────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: 8

            Kirigami.Chip {
                text: midiBackend.getSystemInfo()
                closable: false
            }

            Kirigami.Chip {
                id: midiChip
                readonly property bool available: midiBackend.isMidiAvailable()
                text: available
                    ? "✓ MIDI (" + midiBackend.getMidiBackendName() + ")"
                    : "✗ MIDI no disponible"
                closable: false
            }

            Item { Layout.fillWidth: true }

            Kirigami.Chip {
                id: bpmChip
                text: root.bpm > 0
                    ? "♩ = " + Math.round(root.bpm) + " BPM"
                    : "♩ = -- BPM"
                closable: false
                checkable: false
                enabled: root.bpm > 0
            }
        }

        // ── Panel de conexión ────────────────────────────────────────────
        Kirigami.AbstractCard {
            Layout.fillWidth: true

            contentItem: RowLayout {
                spacing: 12

                Rectangle {
                    width: 14
                    height: 14
                    radius: 7
                    color: root.connected ? "#4caf50" : "#9e9e9e"

                    Behavior on color {
                        ColorAnimation { duration: 200 }
                    }
                }

                Controls.Label {
                    text: "Puerto MIDI:"
                    font.bold: true
                }

                Controls.ComboBox {
                    id: portCombo
                    Layout.fillWidth: true
                    model: root.availablePorts
                    enabled: !root.connected
                }

                Controls.Button {
                    icon.name: "view-refresh"
                    display: Controls.AbstractButton.IconOnly
                    enabled: !root.connected
                    onClicked: root.refreshPorts()

                    Controls.ToolTip {
                        text: "Refrescar puertos"
                        visible: parent.hovered
                    }
                }

                Controls.Button {
                    text: root.connected ? "Desconectar" : "Conectar"
                    icon.name: root.connected ? "network-disconnect" : "network-connect"
                    highlighted: !root.connected
                    onClicked: {
                        if (root.connected) {
                            midiBackend.disconnectPort()
                        } else if (portCombo.currentText) {
                            midiBackend.connectPort(portCombo.currentText)
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

            BigTab {
                text: "Log"
                icon.name: "view-list-text"
            }
            BigTab {
                text: "Batería"
                icon.name: "audio-midi"
            }
            BigTab {
                text: "Visuales"
                icon.name: "image-x-generic"
            }
        }

        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            currentIndex: tabBar.currentIndex

            LogPage {
                id: logPage
            }

            BateriaPage {
                id: bateriaPage
            }

            VisualesPage {
                id: visualesPage
            }
        }
    }
}
