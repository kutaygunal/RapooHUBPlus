import QtQuick
import QtQuick.Controls
import MT760
import "."

Card {
    title: "Activity"
    subtitle: "Button actions, tests and errors, newest first"

    ListView {
        id: list
        anchors.fill: parent
        clip: true
        spacing: 6
        model: Hub.activity
        ScrollBar.vertical: ScrollBar {}
        delegate: Rectangle {
            required property string modelData
            readonly property bool failed: modelData.indexOf("FAILED") >= 0 || modelData.indexOf("failed") >= 0
                                           || modelData.indexOf("Could not") >= 0
            width: list.width - 12
            height: 40
            radius: 10
            color: Theme.surface2
            Rectangle {
                width: 4; height: parent.height - 16; radius: 2
                anchors.left: parent.left; anchors.leftMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                color: failed ? Theme.bad : Theme.accent
            }
            Text {
                anchors.left: parent.left; anchors.leftMargin: 22
                anchors.right: parent.right; anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                text: modelData
                color: failed ? Theme.bad : Theme.text
                font.family: "Cascadia Mono"
                font.pixelSize: 12
                elide: Text.ElideRight
            }
        }
    }
    Text {
        anchors.centerIn: parent
        visible: list.count === 0
        text: "Nothing yet. Press an assigned button or use Test."
        color: Theme.textDim
        font.family: Theme.fontFamily
        font.pixelSize: 13
    }
}
