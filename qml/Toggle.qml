import QtQuick
import "."

// Label + switch row.
Item {
    id: toggle
    property string text: ""
    property string hint: ""
    property bool checked: false
    signal toggled(bool on)

    implicitHeight: Math.max(42, labels.implicitHeight)
    implicitWidth: 300

    Column {
        id: labels
        anchors.left: parent.left
        anchors.right: track.left
        anchors.rightMargin: 12
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Text {
            width: parent.width
            text: toggle.text
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
        Text {
            width: parent.width
            visible: toggle.hint !== ""
            text: toggle.hint
            color: Theme.textDim
            font.family: Theme.fontFamily
            font.pixelSize: 11
            wrapMode: Text.Wrap
        }
    }

    Rectangle {
        id: track
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: 44; height: 24; radius: 12
        color: toggle.checked ? Theme.accent : Theme.surface2
        border.color: toggle.checked ? Theme.accent : Theme.border
        Rectangle {
            width: 18; height: 18; radius: 9
            y: 3
            x: toggle.checked ? parent.width - width - 3 : 3
            color: "white"
            Behavior on x { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        }
        Behavior on color { ColorAnimation { duration: 140 } }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: toggle.toggled(!toggle.checked)
    }
}
