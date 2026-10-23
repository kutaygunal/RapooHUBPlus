import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import MT760
import "."

// Per-app profiles: which apps switch to which profile, DPI on switch, and button overrides.
Item {
    id: page
    signal editButtons()

    property string selected: "Default"
    property string error: ""

    Connections {
        target: Hub
        function onProfilesChanged() {
            if (Hub.profiles.indexOf(page.selected) < 0) page.selected = "Default"
            page.infoRev++
        }
    }
    property int infoRev: 0
    readonly property var detail: infoRev >= 0 ? Hub.profileInfo(selected) : ({})

    FileDialog {
        id: exeDialog
        property string mode: "add"  // "add" to the selected profile, "new" profile for an app
        title: "Choose an app"
        nameFilters: ["Programs (*.exe)"]
        onAccepted: {
            const p = Hub.localPath(selectedFile)
            page.error = mode === "new" ? Hub.addProfileForApp(p) : Hub.addProfileApp(page.selected, p)
            if (mode === "new" && page.error === "") page.selected = Hub.editingProfile
        }
    }

    Popup {
        id: appPicker
        property string mode: "add"
        property var apps: []
        modal: true
        focus: true
        anchors.centerIn: Overlay.overlay
        width: 460
        height: Math.min(520, 120 + apps.length * 46)
        padding: 18
        background: Rectangle { color: Theme.surface; radius: Theme.radius; border.color: Theme.border }
        ColumnLayout {
            anchors.fill: parent
            spacing: 10
            Text {
                text: appPicker.mode === "new" ? "New profile for a running app" : "Add a running app"
                color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 15; font.weight: Font.DemiBold
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                spacing: 6
                model: appPicker.apps
                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    height: 40
                    radius: 10
                    color: rowMouse.containsMouse ? Theme.surfaceHover : Theme.surface2
                    Column {
                        anchors.left: parent.left; anchors.leftMargin: 12
                        anchors.right: parent.right; anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        Text { text: modelData.exe; color: Theme.text; font.family: Theme.fontFamily
                               font.pixelSize: 13; font.weight: Font.DemiBold }
                        Text { text: modelData.title; color: Theme.textDim; font.family: Theme.fontFamily
                               font.pixelSize: 11; elide: Text.ElideRight; width: parent.width }
                    }
                    MouseArea {
                        id: rowMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            page.error = appPicker.mode === "new" ? Hub.addProfileForApp(modelData.exe)
                                                                   : Hub.addProfileApp(page.selected, modelData.exe)
                            if (appPicker.mode === "new" && page.error === "") page.selected = Hub.editingProfile
                            appPicker.close()
                        }
                    }
                }
            }
            RowLayout {
                Pill { text: "Browse for .exe..."; onClicked: { exeDialog.mode = appPicker.mode; appPicker.close(); exeDialog.open() } }
                Item { Layout.fillWidth: true }
                Pill { text: "Cancel"; onClicked: appPicker.close() }
            }
        }
    }

    function pickApp(mode) {
        appPicker.mode = mode
        appPicker.apps = Hub.runningApps()
        appPicker.open()
    }

    RowLayout {
        anchors.fill: parent
        spacing: 16

        // profile list
        Card {
            title: "Profiles"
            Layout.preferredWidth: 380
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 10

                Toggle {
                    Layout.fillWidth: true
                    text: "Switch automatically"
                    hint: Hub.foregroundApp !== "" ? "In front now: " + Hub.foregroundApp + "  →  " + Hub.activeProfile
                                                   : "Follows the app in front"
                    checked: Hub.autoSwitch
                    onToggled: (on) => Hub.setAutoSwitch(on)
                }

                ListView {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    spacing: 8
                    model: Hub.profiles
                    delegate: Rectangle {
                        id: row
                        required property string modelData
                        readonly property var p: page.infoRev >= 0 ? Hub.profileInfo(modelData) : ({})
                        readonly property bool isSel: page.selected === modelData
                        width: ListView.view.width
                        height: 58
                        radius: Theme.radiusSmall
                        color: isSel ? Theme.accentSoft : (rowMouse2.containsMouse ? Theme.surfaceHover : Theme.surface2)
                        border.color: isSel ? Theme.accent : "transparent"
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 14
                            anchors.right: activeBadge.left; anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text { text: row.modelData; color: Theme.text; font.family: Theme.fontFamily
                                   font.pixelSize: 14; font.weight: Font.DemiBold }
                            Text {
                                width: parent.width
                                elide: Text.ElideRight
                                text: row.p.isDefault ? "Used everywhere else" + (row.p.actions ? " • " + row.p.actions + (row.p.actions === 1 ? " action" : " actions") : "")
                                     : (row.p.apps && row.p.apps.length ? row.p.apps.join(", ") : "No apps yet")
                                       + (row.p.actions ? " • " + row.p.actions + (row.p.actions === 1 ? " action" : " actions") : "")
                                color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 11
                            }
                        }
                        Rectangle {
                            id: activeBadge
                            visible: row.p.active === true
                            anchors.right: parent.right; anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: activeText.implicitWidth + 16; height: 22; radius: 11
                            color: Theme.good
                            Text { id: activeText; anchors.centerIn: parent; text: "Active"; color: "white"
                                   font.family: Theme.fontFamily; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                        MouseArea {
                            id: rowMouse2
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: { page.selected = row.modelData; page.error = "" }
                        }
                    }
                }

                RowLayout {
                    spacing: 8
                    Pill { text: "New for app..."; icon: Theme.icAdd; checked: true; onClicked: page.pickApp("new") }
                    Pill {
                        text: "Blank"
                        onClicked: {
                            let n = 1
                            while (Hub.profiles.indexOf("Profile " + n) >= 0) n++
                            page.error = Hub.addProfile("Profile " + n)
                            if (page.error === "") page.selected = "Profile " + n
                        }
                    }
                }
            }
        }

        // details
        Card {
            title: page.selected
            subtitle: page.detail.isDefault ? "Applies to every app without its own profile"
                                            : "Only changes what you set; everything else comes from Default"
            Layout.fillWidth: true
            Layout.fillHeight: true

            ColumnLayout {
                anchors.fill: parent
                spacing: 18

                RowLayout {
                    visible: !page.detail.isDefault
                    spacing: 10
                    Text { text: "Name"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 13
                           Layout.preferredWidth: 110 }
                    Field { id: nameField; text: page.selected; Layout.preferredWidth: 280 }
                    Pill { text: "Rename"; enabledLook: nameField.text.trim() !== page.selected && nameField.text.trim() !== ""
                           onClicked: { const n = nameField.text.trim(); page.error = Hub.renameProfile(page.selected, n)
                                        if (page.error === "") page.selected = n } }
                }

                RowLayout {
                    visible: !page.detail.isDefault
                    spacing: 10
                    Text { text: "Apps"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 13
                           Layout.preferredWidth: 110; Layout.alignment: Qt.AlignTop; topPadding: 8 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: page.detail.apps || []
                            delegate: Rectangle {
                                required property string modelData
                                height: 34; radius: 17
                                width: appLabel.implicitWidth + 44
                                color: Theme.surface2
                                border.color: Theme.border
                                Text { id: appLabel; anchors.left: parent.left; anchors.leftMargin: 14
                                       anchors.verticalCenter: parent.verticalCenter
                                       text: modelData; color: Theme.text; font.family: Theme.fontFamily; font.pixelSize: 12 }
                                Text { anchors.right: parent.right; anchors.rightMargin: 12
                                       anchors.verticalCenter: parent.verticalCenter
                                       text: Theme.icClose; font.family: Theme.iconFont; font.pixelSize: 10; color: Theme.textDim
                                       MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor
                                                   onClicked: Hub.removeProfileApp(page.selected, modelData) } }
                            }
                        }
                        Pill { height: 34; fontSize: 12; text: "Add app..."; icon: Theme.icAdd; onClicked: page.pickApp("add") }
                    }
                }

                RowLayout {
                    spacing: 10
                    Text { text: "DPI on switch"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 13
                           Layout.preferredWidth: 110 }
                    Flow {
                        Layout.fillWidth: true
                        spacing: 8
                        Pill {
                            height: 34; fontSize: 12
                            text: "Don't change"
                            checked: !page.detail.dpiLevel
                            onClicked: Hub.setProfileDpi(page.selected, 0)
                        }
                        Repeater {
                            model: Hub.dpiValues.length ? Hub.dpiValues : [1, 2, 3, 4, 5, 6, 7]
                            delegate: Pill {
                                required property int index
                                required property var modelData
                                height: 34; fontSize: 12
                                text: Hub.dpiValues.length ? modelData : "Level " + (index + 1)
                                checked: page.detail.dpiLevel === index + 1
                                onClicked: Hub.setProfileDpi(page.selected, index + 1)
                            }
                        }
                    }
                }
                Text {
                    Layout.fillWidth: true
                    Layout.leftMargin: 120
                    wrapMode: Text.Wrap
                    text: page.detail.isDefault
                          ? "Default's DPI applies when you leave an app profile that changed DPI. Changing DPI needs the mouse connected."
                          : "Switching into this profile sets that DPI, and leaving it restores your previous level. "
                            + "Each change is saved on the mouse, so it's best for apps you switch to now and then."
                    color: Theme.textFaint; font.family: Theme.fontFamily; font.pixelSize: 11
                }

                Item { Layout.fillHeight: true }

                RowLayout {
                    spacing: 10
                    Text {
                        Layout.fillWidth: true
                        text: page.error
                        color: Theme.bad
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        elide: Text.ElideRight
                    }
                    Pill {
                        visible: !page.detail.isDefault
                        text: "Delete profile"
                        onClicked: Hub.deleteProfile(page.selected)
                    }
                    Pill {
                        icon: Theme.icMouse
                        text: "Edit buttons for " + page.selected
                        checked: true
                        onClicked: { Hub.setEditingProfile(page.selected); page.editButtons() }
                    }
                }
            }
        }
    }
}
