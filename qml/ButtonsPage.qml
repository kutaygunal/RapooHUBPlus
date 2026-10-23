import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MT760
import "."

Item {
    id: page
    property string selected: "back"
    readonly property var sel: {
        for (let c of Hub.controls) if (c.key === selected) return c
        return Hub.controls[0]
    }

    Popup {
        id: profilePicker
        padding: 10
        background: Rectangle { color: Theme.surface; radius: Theme.radiusSmall; border.color: Theme.border }
        Column {
            spacing: 6
            Repeater {
                model: Hub.profiles
                delegate: Pill {
                    required property string modelData
                    width: 220
                    height: 34
                    fontSize: 12
                    text: modelData + (modelData === Hub.activeProfile ? "   (active)" : "")
                    checked: modelData === Hub.editingProfile
                    onClicked: { Hub.setEditingProfile(modelData); profilePicker.close() }
                }
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            // control tiles
            Grid {
                Layout.preferredWidth: 380
                Layout.alignment: Qt.AlignVCenter
                columns: 2
                spacing: 6
                Repeater {
                    model: Hub.controls
                    delegate: Rectangle {
                        id: tile
                        required property var modelData
                        readonly property bool hookable: modelData.hook !== ""
                        readonly property bool isSel: page.selected === modelData.key
                        readonly property int count: Hub.revision >= 0 ? Hub.bindingCount(modelData.hook) : 0
                        readonly property var onMouse: Hub.revision >= 0 && modelData.firmware ? Hub.mouseEntry(modelData.hook) : ({})
                        width: 186; height: 44
                        radius: Theme.radiusSmall
                        color: isSel ? "transparent" : (tileMouse.containsMouse ? Theme.surfaceHover : Theme.surface)
                        border.color: isSel ? "transparent" : Theme.border
                        Rectangle {
                            anchors.fill: parent
                            radius: parent.radius
                            visible: tile.isSel
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: Theme.accent }
                                GradientStop { position: 1; color: Theme.accent2 }
                            }
                        }
                        Column {
                            anchors.left: parent.left
                            anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 1
                            Text {
                                text: modelData.label
                                color: tile.isSel ? "white" : (tile.hookable ? Theme.text : Theme.textDim)
                                font.family: Theme.fontFamily
                                font.pixelSize: 13
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: !tile.hookable ? "Always left click"
                                    : tile.count ? tile.count + (tile.count === 1 ? " action" : " actions")
                                    : "Default"
                                color: tile.isSel ? "#dfe6ff" : (tile.count ? Theme.accent : Theme.textFaint)
                                font.family: Theme.fontFamily
                                font.pixelSize: 11
                            }
                        }
                        Rectangle {  // "stored on the mouse" badge
                            visible: tile.onMouse.ours === true
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: badge.implicitWidth + 14; height: 20; radius: 10
                            color: tile.isSel ? "#ffffff33" : Theme.accentSoft
                            Text {
                                id: badge
                                anchors.centerIn: parent
                                text: tile.onMouse.label || ""
                                color: tile.isSel ? "white" : Theme.accent
                                font.family: Theme.fontFamily
                                font.pixelSize: 10
                                font.weight: Font.DemiBold
                            }
                        }
                        Text {
                            visible: !tile.hookable
                            anchors.right: parent.right
                            anchors.rightMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            text: Theme.icLock
                            font.family: Theme.iconFont
                            font.pixelSize: 12
                            color: tile.isSel ? "white" : Theme.textFaint
                        }
                        MouseArea {
                            id: tileMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: page.selected = modelData.key
                        }
                    }
                }
            }

            MouseView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                selected: page.selected
                onPicked: (key) => page.selected = key
            }
        }

        Card {
            Layout.fillWidth: true
            Layout.preferredHeight: 330
            title: page.sel.label
            headerRight: [
                Pill {
                    id: profilePill
                    height: 32
                    fontSize: 12
                    icon: Theme.icProfile
                    text: "Editing: " + Hub.editingProfile + "  ▾"
                    accentWhenChecked: false
                    onClicked: {
                        const pos = profilePill.mapToItem(page, profilePill.width - 240, profilePill.height + 6)
                        profilePicker.x = pos.x
                        profilePicker.y = pos.y
                        profilePicker.open()
                    }
                }
            ]
            readonly property var onMouse: Hub.revision >= 0 && page.sel.firmware ? Hub.mouseEntry(page.sel.hook) : ({})
            subtitle: page.sel.hook === "" ? ""
                    : (editor.savedText !== "" ? "Now: " + editor.savedText
                       : editor.inheritedText !== "" ? "Now: from Default, " + editor.inheritedText
                       : "Now: default behaviour")
                      + (page.sel.firmware
                         ? (onMouse.label === undefined ? "   •   stored on the mouse over cable or receiver"
                            : onMouse.synced ? "   •   mouse sends " + onMouse.label
                            : "   •   mouse update pending")
                         : "")

            ActionEditor {
                id: editor
                anchors.fill: parent
                visible: page.sel.hook !== ""
                hook: page.sel.hook
                controlLabel: page.sel.label
                firmware: page.sel.firmware
            }

            Column {
                anchors.centerIn: parent
                visible: page.sel.hook === ""
                spacing: 8
                width: parent.width * 0.7
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: Theme.icLock
                    font.family: Theme.iconFont
                    font.pixelSize: 26
                    color: Theme.textFaint
                }
                Text {
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: "Left click is never remapped, so you can always click your way back. "
                          + "Every other control can run actions."
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                }
            }
        }
    }
}
