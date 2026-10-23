import QtQuick
import MT760
import "."

// Top + underside illustrations with clickable hotspots and an A HUB-style leader line.
Item {
    id: view
    property string selected: ""
    property bool interactive: true
    property bool showBottom: true
    property string labelOverride: ""
    signal picked(string key)

    function control(key) {
        for (let c of Hub.controls) if (c.key === key) return c
        return null
    }
    readonly property var sel: control(selected)

    // fit both views (and the gap between them) into the available width and height
    readonly property real gap: showBottom ? 48 : 0
    readonly property real imgH: Math.min(height * 0.94,
                                          (width * 0.8 - gap) / (showBottom ? 2 : 1) * 560 / 420)
    readonly property real imgW: imgH * 420 / 560

    Row {
        id: images
        anchors.centerIn: parent
        spacing: view.gap

        Repeater {
            model: view.showBottom ? ["top", "bottom"] : ["top"]
            delegate: Item {
                id: pane
                required property string modelData
                readonly property bool isTop: modelData === "top"
                // both views share one outline and scale, so they're drawn the same size, aligned
                width: view.imgW
                height: view.imgH

                Image {
                    anchors.fill: parent
                    source: "assets/mouse_" + pane.modelData + ".svg"
                    sourceSize: Qt.size(width * 2, height * 2)
                    smooth: true
                    mipmap: true
                }
                Text {
                    visible: view.showBottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.top: parent.bottom
                    anchors.topMargin: -6
                    text: pane.isTop ? "Top" : "Underside"
                    color: Theme.textFaint
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                }

                Repeater {
                    model: Hub.controls
                    delegate: Item {
                        required property var modelData
                        readonly property bool isSel: modelData.key === view.selected
                        visible: modelData.view === pane.modelData && (view.interactive || isSel)
                        x: modelData.x * pane.width
                        y: modelData.y * pane.height

                        Rectangle {  // pulse ring
                            anchors.centerIn: parent
                            width: 32; height: 32; radius: 16
                            color: "transparent"
                            border.color: Theme.accent
                            border.width: 2
                            visible: parent.isSel
                            SequentialAnimation on scale {
                                running: parent.visible
                                loops: Animation.Infinite
                                NumberAnimation { from: 0.6; to: 1.3; duration: 1000; easing.type: Easing.OutCubic }
                            }
                            SequentialAnimation on opacity {
                                running: parent.visible
                                loops: Animation.Infinite
                                NumberAnimation { from: 1; to: 0; duration: 1000 }
                            }
                        }
                        Rectangle {
                            anchors.centerIn: parent
                            width: parent.isSel ? 16 : (dotMouse.containsMouse ? 15 : 12)
                            height: width; radius: width / 2
                            color: parent.isSel ? Theme.accent : (modelData.hook !== "" ? "white" : "#c3c8cf")
                            border.color: Theme.accent
                            border.width: parent.isSel ? 0 : 2
                            Behavior on width { NumberAnimation { duration: 100 } }
                        }
                        MouseArea {
                            id: dotMouse
                            anchors.centerIn: parent
                            width: 30; height: 30
                            enabled: view.interactive
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: view.picked(modelData.key)
                        }
                    }
                }
            }
        }
    }

    // leader line + label for the selection, drawn in view coordinates
    Item {
        id: leader
        anchors.fill: parent
        visible: view.sel !== null
        // the Row's children include the Repeater itself, so look the pane up by name
        readonly property Item pane: {
            if (!view.sel) return null
            const want = view.showBottom ? view.sel.view : "top"
            for (let i = 0; i < images.children.length; i++)
                if (images.children[i].modelData === want) return images.children[i]
            return null
        }
        // mapToItem isn't reactive: mention the geometry so these update on resize
        readonly property real paneLeft: pane ? images.x + pane.x + 0 * view.width * view.height : 0
        readonly property real paneTop: pane ? images.y + pane.y + 0 * images.height : 0
        readonly property point dot: pane && view.sel
            ? Qt.point(paneLeft + view.sel.x * pane.width, paneTop + view.sel.y * pane.height) : Qt.point(0, 0)
        readonly property bool rightSide: view.sel ? (view.sel.view === "bottom" || view.sel.x > 0.6) : false
        readonly property real endX: pane ? (rightSide ? paneLeft + pane.width + 34 : paneLeft - 34) : 0

        Rectangle {
            x: Math.min(leader.dot.x, leader.endX)
            y: leader.dot.y - 1
            width: Math.abs(leader.dot.x - leader.endX)
            height: 2
            color: Theme.accent
        }
        Rectangle {
            x: leader.endX - 4; y: leader.dot.y - 4
            width: 8; height: 8; radius: 4
            color: Theme.accent
        }
        Rectangle {
            readonly property string label: view.labelOverride !== "" ? view.labelOverride : (view.sel ? view.sel.label : "")
            height: 30
            width: lbl.implicitWidth + 24
            radius: 15
            color: Theme.surface
            border.color: Theme.accent
            y: leader.dot.y - height / 2
            x: leader.rightSide ? leader.endX + 10 : leader.endX - width - 10
            Text {
                id: lbl
                anchors.centerIn: parent
                text: parent.label
                color: Theme.text
                font.family: Theme.fontFamily
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }
    }
}
