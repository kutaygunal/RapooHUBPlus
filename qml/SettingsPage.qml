import QtQuick
import QtQuick.Layouts
import MT760
import "."

Item {
    GridLayout {
        anchors.fill: parent
        columns: 2
        columnSpacing: 16
        rowSpacing: 16

        Card {
            title: "Device"
            Layout.fillWidth: true
            Layout.preferredHeight: 310
            Layout.alignment: Qt.AlignTop
            Column {
                anchors.fill: parent
                spacing: 12
                Repeater {
                    model: [
                        {k: "Model", v: "Rapoo MT760"},
                        {k: "Connection", v: Hub.connectionText},
                        {k: "Firmware", v: Hub.firmware || "—"},
                        {k: "Battery", v: Hub.battery >= 0 ? Hub.battery + "%" + (Hub.charging ? " (charging)" : "") : "—"}
                    ]
                    delegate: Row {
                        required property var modelData
                        width: parent.width
                        Text { width: 140; text: modelData.k; color: Theme.textDim
                               font.family: Theme.fontFamily; font.pixelSize: 13 }
                        Text { text: modelData.v; color: Theme.text; font.family: Theme.fontFamily
                               font.pixelSize: 13; font.weight: Font.DemiBold }
                    }
                }
            }
        }

        Card {
            title: "Button actions"
            Layout.fillWidth: true
            Layout.preferredHeight: 310
            Layout.alignment: Qt.AlignTop
            Column {
                anchors.fill: parent
                spacing: 12
                Row {
                    spacing: 8
                    Pill {
                        height: 34
                        fontSize: 12
                        text: "Reset mouse buttons"
                        enabledLook: Hub.connected
                        onClicked: Hub.resetMouseButtons()
                    }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: "Clears DPI, DIY, right-click and wheel actions and restores the factory mapping."
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                        width: 260
                        wrapMode: Text.Wrap
                    }
                }
                Toggle {
                    width: parent.width
                    text: "Pause all button actions"
                    hint: "Buttons behave normally until you resume."
                    checked: Hub.paused
                    onToggled: (on) => Hub.setPaused(on)
                }
                RowLayout {
                    width: parent.width
                    Text { text: "Long press after"; color: Theme.text; font.family: Theme.fontFamily
                           font.pixelSize: 13; Layout.fillWidth: true }
                    Stepper { from: 200; to: 2000; step: 50; suffix: " ms"; value: Hub.longPressMs
                              onChanged: (v) => Hub.setLongPressMs(v) }
                }
                RowLayout {
                    width: parent.width
                    Text { text: "Gesture distance"; color: Theme.text; font.family: Theme.fontFamily
                           font.pixelSize: 13; Layout.fillWidth: true }
                    Stepper { from: 20; to: 300; step: 10; suffix: " px"; value: Hub.gesturePx
                              onChanged: (v) => Hub.setGesturePx(v) }
                }
                RowLayout {
                    width: parent.width
                    Text { text: "Double click within"; color: Theme.text; font.family: Theme.fontFamily
                           font.pixelSize: 13; Layout.fillWidth: true }
                    Stepper { from: 150; to: 800; step: 25; suffix: " ms"; value: Hub.doubleClickMs
                              onChanged: (v) => Hub.setDoubleClickMs(v) }
                }
            }
        }

        Card {
            title: "App"
            Layout.fillWidth: true
            Layout.preferredHeight: 230
            Layout.alignment: Qt.AlignTop
            Column {
                anchors.fill: parent
                spacing: 12
                Toggle {
                    width: parent.width
                    text: "Dark mode"
                    checked: Hub.darkMode
                    onToggled: (on) => Hub.setDarkMode(on)
                }
                Toggle {
                    width: parent.width
                    text: "Start with Windows"
                    hint: "Starts minimized to the tray."
                    checked: Hub.autostart
                    onToggled: (on) => Hub.setAutostart(on)
                }
                Pill {
                    icon: Theme.icFolder
                    text: "Open profiles folder"
                    onClicked: Qt.openUrlExternally("file:///" + Hub.configDir.replace(/\\/g, "/"))
                }
            }
        }

        Card {
            title: "About"
            Layout.fillWidth: true
            Layout.preferredHeight: 230
            Layout.alignment: Qt.AlignTop
            Text {
                anchors.fill: parent
                wrapMode: Text.Wrap
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: 13
                lineHeight: 1.3
                text: "MT760 Hub talks to the mouse with the protocol recovered from A HUB. "
                      + "Close A HUB while this is running: both apps can't read the mouse at the same time.\n\n"
                      + "Button actions use a Windows mouse hook, so they work in every connection mode."
            }
        }

        Item { Layout.fillHeight: true; Layout.columnSpan: 2 }
    }
}
