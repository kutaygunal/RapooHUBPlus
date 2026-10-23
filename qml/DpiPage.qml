import QtQuick
import QtQuick.Layouts
import MT760
import "."

Item {
    id: page
    readonly property var values: Hub.dpiValues
    readonly property int current: Hub.dpiCurrent
    readonly property int maxDpi: values.length ? Math.max.apply(null, values) : 4000
    // live value from the mouse's own announcement, else the table entry for the current level
    readonly property int curDpi: Hub.liveDpi > 0 ? Hub.liveDpi
                                  : current >= 0 && current < values.length ? values[current] : 0

    ColumnLayout {
        anchors.fill: parent
        spacing: 16

        MouseView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumHeight: 240
            selected: "dpi"
            interactive: false
            showBottom: false
            labelOverride: page.curDpi ? "DPI button: " + page.curDpi + " DPI" : "DPI button"
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 270
            spacing: 16

            Card {
                title: "DPI levels"
                subtitle: values.length && current >= 0 ? "Level " + (current + 1) + " of " + values.length : ""
                Layout.preferredWidth: 380
                Layout.fillHeight: true

                Grid {
                    anchors.fill: parent
                    columns: 3
                    spacing: 10
                    Repeater {
                        model: page.values
                        delegate: Pill {
                            required property int index
                            required property var modelData
                            width: (parent.width - 20) / 3
                            height: 44
                            text: modelData
                            fontSize: 14
                            checked: index === page.current
                            enabledLook: Hub.writable
                            onClicked: Hub.setDpiLevel(index)
                        }
                    }
                }
                Text {
                    anchors.centerIn: parent
                    visible: !Hub.connected
                    width: parent.width
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: "Connect the mouse to read and change DPI."
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: 13
                }
            }

            Card {
                title: "DPI"
                Layout.fillWidth: true
                Layout.fillHeight: true

                Text {
                    id: big
                    anchors.left: parent.left
                    anchors.top: parent.top
                    text: page.curDpi ? page.curDpi : "—"
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: 44
                    font.weight: Font.Bold
                }
                Text {
                    anchors.left: big.right
                    anchors.leftMargin: 8
                    anchors.baseline: big.baseline
                    text: "DPI"
                    color: Theme.textDim
                    font.family: Theme.fontFamily
                    font.pixelSize: 16
                }

                Item {
                    id: dpiScale
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 34
                    height: 26

                    function pos(v) { return width * Math.min(1, v / page.maxDpi) }

                    Rectangle {
                        anchors.fill: parent
                        radius: height / 2
                        color: Theme.surface2
                    }
                    Rectangle {
                        height: parent.height
                        width: Math.max(height, dpiScale.pos(page.curDpi))
                        radius: height / 2
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0; color: Theme.accent }
                            GradientStop { position: 1; color: Theme.accent2 }
                        }
                        Behavior on width { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                    }
                    Rectangle {  // knob
                        visible: page.curDpi > 0
                        width: 30; height: 30; radius: 15
                        y: -2
                        x: Math.max(0, dpiScale.pos(page.curDpi) - width / 2)
                        color: "white"
                        border.color: Theme.accent2
                        border.width: 3
                        Behavior on x { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
                    }
                    Repeater {
                        model: page.values
                        delegate: Text {
                            required property int index
                            required property var modelData
                            text: modelData
                            x: dpiScale.pos(modelData) - width / 2
                            y: dpiScale.height + 10
                            color: index === page.current ? Theme.accent : Theme.textDim
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                            font.weight: index === page.current ? Font.Bold : Font.Normal
                        }
                    }
                }
                Text {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    text: Hub.connected && !Hub.writable
                          ? "Read-only over Bluetooth: press the DPI button, or use the cable or receiver to pick a level"
                          : "Press the DPI button or pick a level"
                    color: Theme.textFaint
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                }
            }
        }
    }
}
