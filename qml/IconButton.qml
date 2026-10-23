import QtQuick
import QtQuick.Controls
import "."

// Round toolbar button with a Segoe Fluent icon.
Rectangle {
    id: btn
    property string icon: ""
    property string tip: ""
    property bool danger: false
    signal clicked()

    width: 40; height: 40; radius: 20
    color: mouse.containsMouse ? (danger ? Theme.bad : Theme.surfaceHover) : Theme.surface
    border.color: Theme.border

    Text {
        anchors.centerIn: parent
        text: btn.icon
        font.family: Theme.iconFont
        font.pixelSize: 15
        color: mouse.containsMouse && btn.danger ? "white" : Theme.text
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: btn.clicked()
    }
    ToolTip.visible: tip !== "" && mouse.containsMouse
    ToolTip.text: tip
    ToolTip.delay: 500
    Behavior on color { ColorAnimation { duration: 120 } }
}
