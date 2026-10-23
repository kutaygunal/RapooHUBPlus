import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import MT760
import "."

// Edit the action of one hook button for one trigger (click / double / long).
Item {
    id: ed
    property string hook: ""
    property string controlLabel: ""
    property string trigger: "click"
    property string type: "run"
    property string error: ""
    property string savedText: ""
    property bool recording: false
    property bool firmware: false
    // what an unassigned trigger does for this control
    readonly property string hint: !firmware ? ""
        : hook === "dpi" ? "Unassigned presses still cycle DPI (cable or receiver)."
        : hook.startsWith("wheel") ? "Each wheel notch runs the action once."
        : "Unassigned presses keep the normal behaviour."

    readonly property var triggers: Hub.triggersFor(hook)
    function shortLabel(key) {
        return ({click: "Click", double: "Double", long: "Long press"})[key] || ""
    }
    // Fluent arrow icons (the plain arrow characters fall back to colour emoji on Windows)
    function arrowIcon(key) {
        return ({gesture_up: "", gesture_down: "", gesture_left: "", gesture_right: "",
                 scroll_up: "", scroll_down: ""})[key] || ""
    }
    readonly property string inheritedText: Hub.revision >= 0 ? Hub.inherited(hook, trigger) : ""

    function load() {
        error = ""
        recording = false
        if (triggers.length && !triggers.some(t => t.key === trigger)) trigger = triggers[0].key
        const a = Hub.binding(hook, trigger)
        type = a.type || "run"
        path.text = a.path || ""
        args.text = a.args || ""
        cwd.text = a.cwd || ""
        admin.checked = !!a.admin
        hidden.checked = !!a.hidden
        target.text = a.target || ""
        combo.text = a.combo || ""
        mediaKey = a.key || "play_pause"
        dpiMode = a.mode || "next"
        dpiLevel = a.level || 1
        savedText = Hub.describe(a)
    }
    onHookChanged: load()
    onTriggerChanged: load()
    Component.onCompleted: load()
    Connections { target: Hub; function onRevisionChanged() { ed.savedText = Hub.describe(Hub.binding(ed.hook, ed.trigger)) } }

    property string mediaKey: "play_pause"
    property string dpiMode: "next"
    property int dpiLevel: 1

    function collect() {
        if (type === "run" || type === "focus")
            return {type: type, path: path.text, args: args.text, cwd: cwd.text, admin: admin.checked, hidden: hidden.checked}
        if (type === "open") return {type: "open", target: target.text}
        if (type === "keys") return {type: "keys", combo: combo.text}
        if (type === "media") return {type: "media", key: mediaKey}
        return {type: "dpi", mode: dpiMode, level: dpiLevel}
    }

    // Qt key -> name understood by winput.parse_combo
    function keyName(e) {
        const k = e.key
        if (k >= Qt.Key_A && k <= Qt.Key_Z) return String.fromCharCode(k).toLowerCase()
        if (k >= Qt.Key_0 && k <= Qt.Key_9) return String.fromCharCode(k)
        if (k >= Qt.Key_F1 && k <= Qt.Key_F24) return "f" + (k - Qt.Key_F1 + 1)
        const named = {}
        named[Qt.Key_Return] = "enter"; named[Qt.Key_Enter] = "enter"; named[Qt.Key_Tab] = "tab"
        named[Qt.Key_Escape] = "esc"; named[Qt.Key_Space] = "space"; named[Qt.Key_Backspace] = "backspace"
        named[Qt.Key_Delete] = "delete"; named[Qt.Key_Insert] = "insert"; named[Qt.Key_Home] = "home"
        named[Qt.Key_End] = "end"; named[Qt.Key_PageUp] = "pgup"; named[Qt.Key_PageDown] = "pgdn"
        named[Qt.Key_Left] = "left"; named[Qt.Key_Right] = "right"; named[Qt.Key_Up] = "up"
        named[Qt.Key_Down] = "down"; named[Qt.Key_Print] = "printscreen"
        return named[k] || ""
    }

    FileDialog {
        id: fileDialog
        title: "Choose a program or script"
        nameFilters: ["Programs and scripts (*.exe *.bat *.cmd *.ps1 *.py *.pyw *.sh *.lnk)", "All files (*)"]
        onAccepted: path.text = Hub.localPath(selectedFile)
    }
    FileDialog {
        id: openFileDialog
        title: "Choose a file"
        onAccepted: target.text = Hub.localPath(selectedFile)
    }
    FolderDialog {
        id: cwdDialog
        title: "Start in"
        onAccepted: cwd.text = Hub.localPath(selectedFolder)
    }
    FolderDialog {
        id: openFolderDialog
        title: "Choose a folder"
        onAccepted: target.text = Hub.localPath(selectedFolder)
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 14

        // trigger tabs
        RowLayout {
            spacing: 8
            Repeater {
                model: ed.triggers
                delegate: Row {
                    id: trig
                    required property var modelData
                    required property int index
                    readonly property bool bound: Hub.revision >= 0 && Hub.binding(ed.hook, modelData.key).type !== undefined
                    readonly property bool inherited: !bound && Hub.revision >= 0 && Hub.inherited(ed.hook, modelData.key) !== ""
                    readonly property string group: modelData.key.startsWith("gesture") ? "Gesture"
                                                  : modelData.key.startsWith("scroll") ? "Hold + scroll" : ""
                    readonly property bool firstOfGroup: group !== "" && (index === 0 || !ed.triggers[index - 1].key.startsWith(modelData.key.split("_")[0]))
                    spacing: 6
                    Text {
                        visible: trig.firstOfGroup
                        anchors.verticalCenter: parent.verticalCenter
                        leftPadding: 8
                        text: trig.group
                        color: Theme.textFaint
                        font.family: Theme.fontFamily
                        font.pixelSize: 11
                    }
                    Pill {
                        height: 36
                        fontSize: 12
                        icon: ed.arrowIcon(trig.modelData.key)
                        text: ed.shortLabel(trig.modelData.key) + (trig.bound ? "  •" : trig.inherited ? "  ◦" : "")
                        checked: ed.trigger === trig.modelData.key
                        onClicked: ed.trigger = trig.modelData.key
                        ToolTip.visible: hov.hovered
                        ToolTip.text: trig.modelData.label + (trig.inherited ? " (from Default: " + Hub.inherited(ed.hook, trig.modelData.key) + ")" : "")
                        ToolTip.delay: 400
                        HoverHandler { id: hov }
                    }
                }
            }
            Text {
                Layout.fillWidth: true
                Layout.leftMargin: 8
                text: ed.error !== "" ? ed.error : ed.hint
                readonly property bool isError: ed.error !== ""
                color: isError ? Theme.bad : Theme.textDim
                font.family: Theme.fontFamily
                font.pixelSize: 12
                elide: Text.ElideRight
            }
            Pill {
                text: "Clear"
                enabledLook: ed.savedText !== ""
                onClicked: { Hub.clearBinding(ed.hook, ed.trigger); ed.load() }
            }
            Pill {
                text: "Test"
                enabledLook: ed.savedText !== ""
                onClicked: Hub.testBinding(ed.hook, ed.trigger)
            }
            Pill {
                icon: Theme.icCheck
                text: "Save"
                checked: true
                onClicked: {
                    ed.error = Hub.saveBinding(ed.hook, ed.trigger, ed.collect())
                    if (ed.error === "") ed.load()
                }
            }
        }

        // action type chips
        Flow {
            Layout.fillWidth: true
            spacing: 8
            Repeater {
                model: Hub.actionTypes
                delegate: Pill {
                    required property var modelData
                    height: 34
                    fontSize: 12
                    text: modelData.label
                    checked: ed.type === modelData.key
                    onClicked: { ed.type = modelData.key; ed.error = "" }
                }
            }
        }

        // fields
        StackLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.preferredHeight: 0  // take the space that's left, never grow the card
            clip: true
            currentIndex: ({run: 0, focus: 0, open: 1, keys: 2, media: 3, dpi: 4})[ed.type]

            GridLayout {  // run / focus
                columns: 4
                columnSpacing: 10
                rowSpacing: 10
                Field { id: path; Layout.columnSpan: 3; Layout.fillWidth: true
                        placeholderText: "Program or script: .exe .bat .cmd .ps1 .py .sh .lnk" }
                Pill { text: "Browse..."; onClicked: fileDialog.open() }
                Field { id: args; Layout.fillWidth: true; Layout.columnSpan: 2; placeholderText: "Arguments (optional)" }
                Field { id: cwd; Layout.fillWidth: true; placeholderText: "Start in (default: its folder)" }
                Pill { text: "Folder..."; onClicked: cwdDialog.open() }
                Check { id: admin; text: "Run as administrator"; Layout.columnSpan: 2 }
                Check { id: hidden; text: "Hide window (background script)"; visible: ed.type === "run"
                        Layout.columnSpan: 2 }
                Text { visible: ed.type === "focus"; Layout.columnSpan: 2; color: Theme.textDim
                       font.family: Theme.fontFamily; font.pixelSize: 12
                       text: "Brings the app to the front if it's open, minimizes it if it's already in front." }
            }

            RowLayout {  // open
                spacing: 10
                Layout.alignment: Qt.AlignTop
                Field { id: target; Layout.fillWidth: true; Layout.alignment: Qt.AlignTop
                        placeholderText: "https://..., a file, or a folder" }
                Pill { text: "File..."; Layout.alignment: Qt.AlignTop; onClicked: openFileDialog.open() }
                Pill { text: "Folder..."; Layout.alignment: Qt.AlignTop; onClicked: openFolderDialog.open() }
            }

            RowLayout {  // keys
                spacing: 10
                Layout.alignment: Qt.AlignTop
                Field {
                    id: combo
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    placeholderText: ed.recording ? "Press the shortcut now..." : "e.g. ctrl+shift+t, win+d, alt+tab, f13"
                    readOnly: ed.recording
                    Keys.onPressed: (e) => {
                        if (!ed.recording) return
                        const name = ed.keyName(e)
                        if (!name) return
                        let parts = []
                        if (e.modifiers & Qt.ControlModifier) parts.push("ctrl")
                        if (e.modifiers & Qt.ShiftModifier) parts.push("shift")
                        if (e.modifiers & Qt.AltModifier) parts.push("alt")
                        if (e.modifiers & Qt.MetaModifier) parts.push("win")
                        parts.push(name)
                        combo.text = parts.join("+")
                        ed.recording = false
                        e.accepted = true
                    }
                }
                Pill {
                    Layout.alignment: Qt.AlignTop
                    icon: Theme.icRecord
                    text: ed.recording ? "Recording..." : "Record"
                    checked: ed.recording
                    onClicked: { ed.recording = !ed.recording; combo.forceActiveFocus() }
                }
            }

            Flow {  // media
                spacing: 8
                Repeater {
                    model: Hub.mediaKeys
                    delegate: Pill {
                        required property var modelData
                        text: modelData.label
                        checked: ed.mediaKey === modelData.key
                        onClicked: ed.mediaKey = modelData.key
                    }
                }
            }

            ColumnLayout {  // dpi
                spacing: 10
                Row {
                    spacing: 8
                    Repeater {
                        model: [{k: "next", l: "Next level"}, {k: "prev", l: "Previous level"}, {k: "set", l: "Set level"}]
                        delegate: Pill {
                            required property var modelData
                            text: modelData.l
                            checked: ed.dpiMode === modelData.k
                            onClicked: ed.dpiMode = modelData.k
                        }
                    }
                }
                Stepper {
                    visible: ed.dpiMode === "set"
                    from: 1; to: Math.max(1, Hub.dpiValues.length || 7)
                    value: ed.dpiLevel
                    suffix: Hub.dpiValues.length >= ed.dpiLevel ? "  (" + Hub.dpiValues[ed.dpiLevel - 1] + ")" : ""
                    onChanged: (v) => ed.dpiLevel = v
                }
                Text { text: "Needs the cable or the 2.4 GHz receiver."; color: Theme.textDim
                       font.family: Theme.fontFamily; font.pixelSize: 12 }
            }
        }
    }
}
