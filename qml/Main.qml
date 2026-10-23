import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MT760
import "."

ApplicationWindow {
    id: win
    width: 1240
    height: 820
    minimumWidth: 1100
    minimumHeight: 760
    visible: false  // main.py shows it (or keeps it in the tray with --tray)
    title: "MT760 Hub"
    flags: Qt.Window | Qt.FramelessWindowHint
    color: Theme.bg
    font.family: Theme.fontFamily

    property int page: 0
    readonly property var pages: [
        {label: "DPI", icon: Theme.icSpeed},
        {label: "Buttons", icon: Theme.icMouse},
        {label: "Profiles", icon: Theme.icApps},
        {label: "Flow", icon: Theme.icFlow},
        {label: "Performance", icon: Theme.icSliders},
        {label: "Activity", icon: Theme.icHistory},
        {label: "Settings", icon: Theme.icSettings}
    ]

    Rectangle {  // thin window border (frameless)
        anchors.fill: parent
        color: "transparent"
        border.color: Theme.border
        z: 100
    }

    // ---- top bar -----------------------------------------------------------------------------
    Item {
        id: topBar
        anchors { left: parent.left; right: parent.right; top: parent.top }
        height: 78

        DragHandler {
            target: null
            onActiveChanged: if (active) win.startSystemMove()
        }
        TapHandler {
            onDoubleTapped: win.visibility === Window.Maximized ? win.showNormal() : win.showMaximized()
        }

        Row {
            anchors.left: parent.left
            anchors.leftMargin: 26
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10

            Rectangle {  // device pill
                height: 44
                width: devRow.implicitWidth + 32
                radius: 22
                color: Theme.surface
                border.color: Theme.border
                Row {
                    id: devRow
                    anchors.centerIn: parent
                    spacing: 10
                    Text {
                        text: Theme.icMouse
                        font.family: Theme.iconFont
                        font.pixelSize: 18
                        color: Theme.accent
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        Text {
                            text: "Rapoo MT760"
                            color: Theme.text
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Row {
                            spacing: 6
                            Rectangle {
                                width: 7; height: 7; radius: 4
                                anchors.verticalCenter: parent.verticalCenter
                                color: Hub.connected ? Theme.good : Theme.textFaint
                            }
                            Text {
                                text: Hub.connectionText
                                color: Theme.textDim
                                font.pixelSize: 11
                            }
                        }
                    }
                    // battery
                    Row {
                        visible: Hub.battery >= 0
                        spacing: 6
                        anchors.verticalCenter: parent.verticalCenter
                        Rectangle {
                            width: 30; height: 15; radius: 4
                            color: "transparent"
                            border.color: Theme.textDim
                            border.width: 1.5
                            anchors.verticalCenter: parent.verticalCenter
                            Rectangle {
                                x: 2.5; y: 2.5
                                height: parent.height - 5
                                width: Math.max(2, (parent.width - 5) * Hub.battery / 100)
                                radius: 2
                                color: Hub.battery <= 20 ? Theme.bad : Theme.good
                            }
                            Rectangle {
                                x: parent.width; y: 4.5; width: 3; height: 6; radius: 1
                                color: Theme.textDim
                            }
                        }
                        Text {
                            text: Hub.battery + "%" + (Hub.charging ? " ⚡" : "")
                            color: Theme.text
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }

            Pill {
                height: 44
                icon: Theme.icProfile
                text: "Profile: " + Hub.activeProfile
                accentWhenChecked: false
                onClicked: win.page = 2
            }

            Rectangle {
                visible: Hub.paused
                height: 44
                width: pausedRow.implicitWidth + 28
                radius: 22
                color: Theme.warn
                Row {
                    id: pausedRow
                    anchors.centerIn: parent
                    spacing: 8
                    Text { text: Theme.icPause; font.family: Theme.iconFont; color: "white"; font.pixelSize: 13
                           anchors.verticalCenter: parent.verticalCenter }
                    Text { text: "Actions paused"; color: "white"; font.pixelSize: 13; font.weight: Font.DemiBold
                           anchors.verticalCenter: parent.verticalCenter }
                }
            }
        }

        Row {
            anchors.right: parent.right
            anchors.rightMargin: 24
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10
            IconButton {
                icon: Hub.paused ? Theme.icPlay : Theme.icPause
                tip: Hub.paused ? "Resume button actions" : "Pause button actions"
                onClicked: Hub.setPaused(!Hub.paused)
            }
            IconButton {
                icon: Theme.icTheme
                tip: Hub.darkMode ? "Light mode" : "Dark mode"
                onClicked: Hub.setDarkMode(!Hub.darkMode)
            }
            Rectangle { width: 1; height: 22; color: Theme.border; anchors.verticalCenter: parent.verticalCenter }
            IconButton { icon: Theme.icMinimize; tip: "Minimize"; onClicked: win.showMinimized() }
            IconButton { icon: Theme.icClose; tip: "Close to tray"; danger: true; onClicked: Hub.hideWindow() }
        }
    }

    // ---- pages -------------------------------------------------------------------------------
    StackLayout {
        id: stack
        anchors { left: parent.left; right: parent.right; top: topBar.bottom; bottom: nav.top }
        anchors.leftMargin: 28
        anchors.rightMargin: 28
        anchors.topMargin: 6
        anchors.bottomMargin: 18
        currentIndex: win.page

        DpiPage {}
        ButtonsPage {}
        ProfilesPage { onEditButtons: win.page = 1 }
        FlowPage {}
        PerformancePage {}
        ActivityPage {}
        SettingsPage {}
    }

    // ---- bottom navigation -------------------------------------------------------------------
    Row {
        id: nav
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 20
        spacing: 10
        Repeater {
            model: win.pages
            delegate: Pill {
                required property int index
                required property var modelData
                height: 44
                icon: modelData.icon
                text: modelData.label
                fontSize: 14
                checked: win.page === index
                onClicked: win.page = index
            }
        }
    }

    // ---- resize grip (frameless windows have none) --------------------------------------------
    Item {
        width: 18; height: 18
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        DragHandler {
            target: null
            onActiveChanged: if (active) win.startSystemResize(Qt.RightEdge | Qt.BottomEdge)
        }
        HoverHandler { cursorShape: Qt.SizeFDiagCursor }
    }

    // ---- Flow pairing dialog (a request can arrive while any page is open) --------------------
    Rectangle {
        anchors.fill: parent
        color: "#80000000"
        visible: FlowSync.pairing.code !== undefined
        z: 50
        MouseArea { anchors.fill: parent }  // block clicks behind the dialog
        Rectangle {
            anchors.centerIn: parent
            width: 460
            height: pairCol.implicitHeight + 48
            radius: Theme.radius
            color: Theme.surface
            border.color: Theme.border
            Column {
                id: pairCol
                anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top
                anchors.margins: 24
                spacing: 14
                Text {
                    text: FlowSync.pairing.initiator ? "Pairing with " + FlowSync.pairing.name : FlowSync.pairing.name + " wants to pair"
                    color: Theme.text; font.pixelSize: 18; font.weight: Font.DemiBold
                }
                Text {
                    width: parent.width
                    wrapMode: Text.Wrap
                    text: "Check that " + FlowSync.pairing.name + " shows the same code. Accept only if they match."
                    color: Theme.textDim; font.pixelSize: 13
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    text: FlowSync.pairing.code || ""
                    color: Theme.accent; font.pixelSize: 44; font.weight: Font.Bold; font.letterSpacing: 6
                }
                Row {
                    anchors.right: parent.right
                    spacing: 10
                    visible: !FlowSync.pairing.answered
                    Pill { text: "They don't match"; onClicked: FlowSync.answerPairing(false) }
                    Pill { text: "Codes match, pair"; checked: true; onClicked: FlowSync.answerPairing(true) }
                }
                Text {
                    visible: FlowSync.pairing.answered === true
                    text: "Waiting for " + FlowSync.pairing.name + "..."
                    color: Theme.textDim; font.pixelSize: 13
                }
            }
        }
    }

    // ---- toast -------------------------------------------------------------------------------
    Rectangle {
        id: toast
        property string message: ""
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: nav.top
        anchors.bottomMargin: 14
        width: toastText.implicitWidth + 36
        height: 40
        radius: 20
        color: Theme.text
        opacity: 0
        visible: opacity > 0
        Text { id: toastText; anchors.centerIn: parent; text: toast.message; color: Theme.bg; font.pixelSize: 13 }
        Behavior on opacity { NumberAnimation { duration: 180 } }
        Timer { id: toastTimer; interval: 3500; onTriggered: toast.opacity = 0 }
    }
    Connections {
        target: Hub
        function onToast(msg) { toast.message = msg; toast.opacity = 1; toastTimer.restart() }
    }
}
