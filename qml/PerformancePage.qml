import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import MT760
import "."

Item {
    id: page
    readonly property var rates: [125, 250, 500, 1000]

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        Card {
            title: "Polling rate"
            subtitle: Hub.pollingRate ? "Read from the mouse. Changing it comes later."
                    : "Connect the mouse to read it."
            Layout.fillWidth: true
            Layout.preferredHeight: 300

            Row {
                anchors.fill: parent
                anchors.topMargin: 10
                spacing: 10
                Repeater {
                    model: page.rates
                    delegate: Item {
                        required property int index
                        required property int modelData
                        readonly property bool active: Hub.pollingRate === modelData
                        width: (parent.width - 30) / 4
                        height: parent.height
                        Rectangle {
                            anchors.bottom: parent.bottom
                            width: parent.width
                            height: parent.height * (0.45 + index * 0.17)
                            radius: 14
                            gradient: Gradient {
                                GradientStop { position: 0; color: active ? Theme.accent : Theme.surface2 }
                                GradientStop { position: 1; color: active ? Theme.accent2 : Theme.surface }
                            }
                            border.color: active ? "transparent" : Theme.border
                            Text {
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.top: parent.top
                                anchors.topMargin: 16
                                text: modelData + " Hz"
                                color: active ? "white" : Theme.textDim
                                font.family: Theme.fontFamily
                                font.pixelSize: active ? 18 : 15
                                font.weight: active ? Font.Bold : Font.Medium
                            }
                            Text {
                                visible: active
                                anchors.horizontalCenter: parent.horizontalCenter
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 14
                                text: "Current"
                                color: "#e3e9ff"
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 16

            Card {
                id: scrollCard
                title: "Windows scroll speed"
                Layout.fillWidth: true
                Layout.fillHeight: true
                readonly property bool pageMode: Hub.wheelLines < 0

                Column {
                    anchors.fill: parent
                    spacing: 10
                    Rectangle {
                        width: parent.width; height: 92; radius: Theme.radiusSmall
                        color: !scrollCard.pageMode ? Theme.accentSoft : Theme.surface2
                        border.color: !scrollCard.pageMode ? Theme.accent : Theme.border
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 18
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            Text { text: "Scroll by lines"; color: Theme.text; font.family: Theme.fontFamily
                                   font.pixelSize: 14; font.weight: Font.DemiBold }
                            Text { text: "Lines moved per wheel notch"; color: Theme.textDim
                                   font.family: Theme.fontFamily; font.pixelSize: 12 }
                        }
                        Stepper {
                            anchors.right: parent.right; anchors.rightMargin: 18
                            anchors.verticalCenter: parent.verticalCenter
                            from: 1; to: 20
                            value: Hub.wheelLines > 0 ? Hub.wheelLines : 3
                            onChanged: (v) => Hub.setWheelLines(v)
                        }
                        MouseArea { anchors.fill: parent; z: -1
                                    onClicked: if (Hub.wheelLines < 0) Hub.setWheelLines(3) }
                    }
                    Rectangle {
                        width: parent.width; height: 72; radius: Theme.radiusSmall
                        color: scrollCard.pageMode ? Theme.accentSoft : Theme.surface2
                        border.color: scrollCard.pageMode ? Theme.accent : Theme.border
                        Column {
                            anchors.left: parent.left; anchors.leftMargin: 18
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 4
                            Text { text: "Scroll a full page"; color: Theme.text; font.family: Theme.fontFamily
                                   font.pixelSize: 14; font.weight: Font.DemiBold }
                            Text { text: "One screen per wheel notch"; color: Theme.textDim
                                   font.family: Theme.fontFamily; font.pixelSize: 12 }
                        }
                        MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor
                                    onClicked: Hub.setWheelLines(-1) }
                    }
                }
            }

            Card {
                title: "Windows pointer speed"
                subtitle: "Windows default is 10"
                Layout.fillWidth: true
                Layout.fillHeight: true

                Slider {
                    id: speed
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    from: 1; to: 20; stepSize: 1; snapMode: Slider.SnapAlways
                    value: Hub.pointerSpeed
                    onMoved: Hub.setPointerSpeed(value)
                    background: Rectangle {
                        x: speed.leftPadding
                        y: speed.topPadding + speed.availableHeight / 2 - height / 2
                        width: speed.availableWidth; height: 12; radius: 6
                        color: Theme.surface2
                        Rectangle {
                            width: speed.visualPosition * parent.width; height: parent.height; radius: 6
                            gradient: Gradient {
                                orientation: Gradient.Horizontal
                                GradientStop { position: 0; color: Theme.accent }
                                GradientStop { position: 1; color: Theme.accent2 }
                            }
                        }
                    }
                    handle: Rectangle {
                        x: speed.leftPadding + speed.visualPosition * (speed.availableWidth - width)
                        y: speed.topPadding + speed.availableHeight / 2 - height / 2
                        width: 26; height: 26; radius: 13
                        color: "white"; border.color: Theme.accent2; border.width: 3
                    }
                }
                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: speed.top
                    anchors.bottomMargin: 18
                    text: Math.round(speed.value)
                    color: Theme.accent
                    font.family: Theme.fontFamily
                    font.pixelSize: 34
                    font.weight: Font.Bold
                }
                Row {
                    anchors.left: parent.left; anchors.right: parent.right
                    anchors.top: speed.bottom; anchors.topMargin: 8
                    Text { text: "Slow"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 12
                           width: parent.width / 2 }
                    Text { text: "Fast"; color: Theme.textDim; font.family: Theme.fontFamily; font.pixelSize: 12
                           width: parent.width / 2; horizontalAlignment: Text.AlignRight }
                }
            }
        }
    }
}
