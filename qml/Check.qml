import QtQuick
import "."

// Themed checkbox with a label.
Item {
    id: check
    property string text: ""
    property bool checked: false
    implicitWidth: row.implicitWidth
    implicitHeight: 30

    Row {
        id: row
        anchors.verticalCenter: parent.verticalCenter
        spacing: 10
        Rectangle {
            width: 20; height: 20; radius: 6
            anchors.verticalCenter: parent.verticalCenter
            color: check.checked ? Theme.accent : Theme.surface2
            border.color: check.checked ? Theme.accent : Theme.border
            border.width: 1.5
            Text {
                anchors.centerIn: parent
                visible: check.checked
                text: Theme.icCheck
                font.family: Theme.iconFont
                font.pixelSize: 11
                color: "white"
            }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: check.text
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 13
        }
    }
    MouseArea {
        anchors.fill: row
        cursorShape: Qt.PointingHandCursor
        onClicked: check.checked = !check.checked
    }
}
