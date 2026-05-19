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
                    text: "↻"
                    enabled: !root.connected
                    onClicked: root.refreshPorts()

                    Controls.ToolTip {
                        text: "Refrescar puertos"
                        visible: parent.hovered
                    }
                }

                Controls.Button {
                    text: root.connected ? "■  Desconectar" : "▶  Conectar"
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

            Controls.TabButton { text: "Log" }
            Controls.TabButton { text: "Batería" }
            Controls.TabButton { text: "Visuales" }
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
