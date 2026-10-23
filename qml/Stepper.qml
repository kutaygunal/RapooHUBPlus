import QtQuick
import "."

// - value + control in A HUB's style.
Row {
    id: stepper
    property int value: 0
    property int from: 0
    property int to: 100
    property int step: 1
    property string suffix: ""
    signal changed(int value)
    spacing: 6

    Pill {
        width: 34; height: 34
        text: "−"
        fontSize: 15
        enabledLook: stepper.value > stepper.from
        onClicked: stepper.changed(Math.max(stepper.from, stepper.value - stepper.step))
    }
    Rectangle {
        width: 74; height: 34; radius: 10
        color: Theme.surface2
        border.color: Theme.border
        Text {
            anchors.centerIn: parent
            text: stepper.value + stepper.suffix
            color: Theme.text
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.weight: Font.DemiBold
        }
    }
    Pill {
        width: 34; height: 34
        text: "+"
        fontSize: 15
        enabledLook: stepper.value < stepper.to
        onClicked: stepper.changed(Math.min(stepper.to, stepper.value + stepper.step))
    }
}
