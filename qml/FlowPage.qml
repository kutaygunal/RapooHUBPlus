import QtQuick
import QtQuick.Dialogs
import QtQuick.Layouts
import MT760
import "."

// Flow: copy on one PC, switch the mouse to the other PC's channel, paste there.
Item {
    id: page

    FolderDialog {
        id: saveDirDialog
        title: "Save received files in"
        onAccepted: FlowSync.setSaveDir(Hub.localPath(selectedFolder))
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        ColumnLayout {
            Layout.preferredWidth: 460
            Layout.maximumWidth: 460
            Layout.fillWidth: false
            Layout.fillHeight: true
            spacing: 16

            Card {
                title: "Flow"
                subtitle: "Clipboard follows your mouse"
                Layout.fillWidth: true
                Layout.preferredHeight: 250

                Column {
                    anchors.fill: parent
                    spacing: 14
                    Toggle {
                        width: parent.width
                        text: "Turn on Flow on this PC"
                        hint: "This PC is “" + FlowSync.thisName + "”. Keep both PCs on the same network and allow MT760 Hub through Windows Firewall."
                        checked: FlowSync.enabled
                        onToggled: (on) => FlowSync.setEnabled(on)
                    }
                    Rectangle {
                        width: parent.width
                        height: how.implicitHeight + 24
                        radius: Theme.radiusSmall
                        color: Theme.surface2
                        Text {
                            id: how
                            anchors.fill: parent
                            anchors.margins: 12
                            wrapMode: Text.Wrap
                            color: Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: 12
                            lineHeight: 1.25
                            text: "1. Copy text, an image or files on this PC.\n"
                                  + "2. Switch the mouse to the other PC's channel.\n"
                                  + "3. Paste there. Both PCs need Flow on, the same network, and one-time pairing. Allow MT760 Hub through Windows Firewall if pairing times out."
                        }
                    }
                }
            }

            Card {
                title: "Options"
                Layout.fillWidth: true
                Layout.fillHeight: true

                Column {
                    anchors.fill: parent
                    spacing: 12
                    Toggle {
                        width: parent.width
                        text: "Send copied files and folders"
                        checked: FlowSync.includeFiles
                        onToggled: (on) => FlowSync.setIncludeFiles(on)
                    }
                    RowLayout {
                        width: parent.width
                        Text { text: "Largest transfer"; color: Theme.text; font.family: Theme.fontFamily
                               font.pixelSize: 13; Layout.fillWidth: true }
                        Stepper { from: 10; to: 2000; step: 50; suffix: " MB"; value: FlowSync.maxMb
                                  onChanged: (v) => FlowSync.setMaxMb(v) }
                    }
                    RowLayout {
                        width: parent.width
                        spacing: 8
                        Column {
                            Layout.fillWidth: true
                            Text { text: "Received files go to"; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 13 }
                            Text { text: FlowSync.saveDir; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 11
                                   width: parent.width; elide: Text.ElideMiddle }
                        }
                        Pill { height: 32; fontSize: 12; text: "Change..."; onClicked: saveDirDialog.open() }
                        Pill { height: 32; fontSize: 12; icon: Theme.icFolder; text: "Open"; onClicked: FlowSync.openSaveDir() }
                    }
                    Pill {
                        icon: Theme.icFlow
                        text: "Send clipboard now"
                        checked: true
                        enabledLook: FlowSync.enabled && FlowSync.paired.length > 0
                        onClicked: FlowSync.sendNow()
                    }
                    Text {
                        width: parent.width
                        visible: FlowSync.lastEvent !== ""
                        text: FlowSync.lastEvent
                        color: Theme.textDim
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                        elide: Text.ElideRight
                    }
                }
            }
        }

        Card {
            title: "PCs"
            subtitle: FlowSync.enabled ? "Other PCs running MT760 Hub with Flow on" : "Turn on Flow to find other PCs"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 10

                Text { text: "Paired"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 12 }
                Repeater {
                    model: FlowSync.paired
                    delegate: Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        height: 58
                        radius: Theme.radiusSmall
                        color: Theme.surface2
                        Row {
                            anchors.left: parent.left; anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 12
                            Rectangle { width: 9; height: 9; radius: 5; anchors.verticalCenter: parent.verticalCenter
                                        color: modelData.online ? Theme.good : Theme.textFaint }
                            Column {
                                Text { text: modelData.name; color: Theme.text; font.family: Theme.fontFamily
                                       font.pixelSize: 14; font.weight: Font.DemiBold }
                                Text { text: (modelData.online ? "Online" : "Offline") + (modelData.host ? " • " + modelData.host : "")
                                       color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 11 }
                            }
                        }
                        Pill { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                               height: 32; fontSize: 12; text: "Unpair"; onClicked: FlowSync.unpair(modelData.id) }
                    }
                }
                Text {
                    visible: FlowSync.paired.length === 0
                    text: "No paired PCs yet."
                    color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: 12
                }

                Text { text: "Nearby"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 12
                       Layout.topMargin: 10 }
                Repeater {
                    model: FlowSync.nearby
                    delegate: Rectangle {
                        required property var modelData
                        visible: !modelData.paired
                        Layout.fillWidth: true
                        height: visible ? 58 : 0
                        radius: Theme.radiusSmall
                        color: Theme.surface2
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            Text { text: modelData.name; color: Theme.text; font.family: Theme.fontFamily
                                   font.pixelSize: 14; font.weight: Font.DemiBold }
                            Text { text: modelData.host; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 11 }
                        }
                        Pill { anchors.right: parent.right; anchors.rightMargin: 12; anchors.verticalCenter: parent.verticalCenter
                               height: 32; fontSize: 12
                               text: FlowSync.pairing.id === modelData.id && FlowSync.pairing.connecting
                                     ? "Connecting..." : "Pair"
                               checked: !(FlowSync.pairing.id === modelData.id && FlowSync.pairing.connecting)
                               enabledLook: !(FlowSync.pairing.id === modelData.id && FlowSync.pairing.connecting)
                               onClicked: FlowSync.pair(modelData.id) }
                    }
                }
                Text {
                    visible: FlowSync.enabled && FlowSync.nearby.filter(n => !n.paired).length === 0
                    Layout.fillWidth: true
                    wrapMode: Text.Wrap
                    text: "Looking for PCs... Turn on Flow in MT760 Hub on the other PC too."
                    color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: 12
                }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
