pragma Singleton
import QtQuick
import MT760

QtObject {
    readonly property bool dark: Hub.darkMode

    readonly property color bg: dark ? "#0e1014" : "#f2f4f7"
    readonly property color surface: dark ? "#171a20" : "#ffffff"
    readonly property color surface2: dark ? "#1f232b" : "#eef1f5"
    readonly property color surfaceHover: dark ? "#262b35" : "#e6eaf0"
    readonly property color border: dark ? "#272c35" : "#e2e6ed"
    readonly property color text: dark ? "#e9ecf1" : "#171a20"
    readonly property color textDim: dark ? "#8b94a4" : "#6b7280"
    readonly property color textFaint: dark ? "#5b6372" : "#a3aab6"
    readonly property color accent: "#3d7eff"
    readonly property color accent2: "#8b5cf6"
    readonly property color accentSoft: dark ? "#1b2846" : "#dde7ff"
    readonly property color good: "#22c55e"
    readonly property color warn: "#f59e0b"
    readonly property color bad: "#ef4444"
    readonly property color heroGlow: dark ? "#1a2440" : "#e4ebff"

    readonly property int radius: 18
    readonly property int radiusSmall: 12
    readonly property string fontFamily: "Segoe UI Variable Text"
    readonly property string iconFont: "Segoe Fluent Icons"

    // Segoe Fluent Icons glyphs
    readonly property string icMouse: ""
    readonly property string icSettings: ""
    readonly property string icTheme: ""
    readonly property string icPause: ""
    readonly property string icPlay: ""
    readonly property string icMinimize: ""
    readonly property string icClose: ""
    readonly property string icProfile: ""
    readonly property string icSpeed: ""
    readonly property string icButtons: ""
    readonly property string icSliders: ""
    readonly property string icHistory: ""
    readonly property string icFolder: ""
    readonly property string icLock: ""
    readonly property string icBolt: ""
    readonly property string icCheck: ""
    readonly property string icRecord: ""
    readonly property string icPlug: ""
    readonly property string icAdd: ""
    readonly property string icApps: ""
    readonly property string icFlow: ""
}
