import QtQuick
import QtQuick.Layouts
import "."

// Rounded surface with an optional title and A HUB-style accent underline.
Rectangle {
    id: card
    property string title: ""
    property string subtitle: ""
    property alias headerRight: headerRightSlot.data
    default property alias content: body.data
    property int padding: 22

    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.border
    border.width: 1

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: card.padding
        spacing: 14

        RowLayout {
            visible: card.title !== ""
            Layout.fillWidth: true
            Column {
                spacing: 4
                Text {
                    text: card.title
                    color: Theme.text
                    font.family: Theme.fontFamily
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                }
                Rectangle {
                    width: 18; height: 3; radius: 2
                    gradient: Gradient {
                        orientation: Gradient.Horizontal
                        GradientStop { position: 0; color: Theme.accent }
                        GradientStop { position: 1; color: Theme.accent2 }
                    }
                }
            }
            Text {
                visible: card.subtitle !== ""
                text: card.subtitle
                color: Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: 12
                Layout.leftMargin: 10
                Layout.alignment: Qt.AlignTop
            }
            Item { Layout.fillWidth: true }
            Row { id: headerRightSlot; spacing: 8 }
        }

        Item {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
        }
    }
}
