import QtQuick
import QtQuick.Controls
import "."

TextField {
    id: field
    implicitHeight: 40
    color: Theme.text
    placeholderTextColor: Theme.textFaint
    selectionColor: Theme.accent
    selectedTextColor: "white"
    font.family: Theme.fontFamily
    font.pixelSize: 13
    leftPadding: 14
    rightPadding: 14
    background: Rectangle {
        radius: Theme.radiusSmall
        color: Theme.surface2
        border.color: field.activeFocus ? Theme.accent : Theme.border
        border.width: field.activeFocus ? 2 : 1
    }
}
