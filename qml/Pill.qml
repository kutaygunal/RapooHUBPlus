import QtQuick
import "."

// Rounded button used for navigation, chips and toolbar actions.
Rectangle {
    id: pill
    property string text: ""
    property string icon: ""
    property bool checked: false
    property bool enabledLook: true
    property bool accentWhenChecked: true
    property int fontSize: 13
    property color textColor: checked && accentWhenChecked ? "white" : (enabledLook ? Theme.text : Theme.textFaint)
    signal clicked()

    implicitHeight: 40
    implicitWidth: row.implicitWidth + 32
    radius: height / 2
    color: checked && accentWhenChecked ? "transparent"
         : mouse.containsMouse && enabledLook ? Theme.surfaceHover : Theme.surface
    border.color: checked && accentWhenChecked ? "transparent" : Theme.border
    border.width: 1

    Rectangle {
        anchors.fill: parent
        radius: parent.radius
        visible: pill.checked && pill.accentWhenChecked
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0; color: Theme.accent }
            GradientStop { position: 1; color: Theme.accent2 }
        }
    }

    Row {
        id: row
        anchors.centerIn: parent
        spacing: 8
        Text {
            visible: pill.icon !== ""
            text: pill.icon
            font.family: Theme.iconFont
            font.pixelSize: pill.fontSize + 2
            color: pill.textColor
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            visible: pill.text !== ""
            text: pill.text
            font.family: Theme.fontFamily
            font.pixelSize: pill.fontSize
            font.weight: pill.checked ? Font.DemiBold : Font.Medium
            color: pill.textColor
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: pill.enabledLook ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (pill.enabledLook) pill.clicked()
    }

    Behavior on color { ColorAnimation { duration: 120 } }
}
