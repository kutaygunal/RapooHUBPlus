"""MT760 Hub: a replacement for A HUB.

Run:  python main.py          (add --tray to start minimized to the tray)
Close A HUB first; it takes the mouse's replies.
"""
import os
import sys

from PySide6.QtCore import QLockFile, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtQml import QQmlApplicationEngine, qmlRegisterSingletonInstance
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from actions import ActionRunner
from backend import Hub
from config import APP_DIR, BUTTONS, TRIGGERS, Config
from flow import Flow
from hook import ButtonHook

HERE = os.path.dirname(os.path.abspath(__file__))


def make_icon(paused=False):
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#8a8f98") if paused else QColor("#3d7eff"))
    p.setPen(Qt.NoPen)
    p.drawRoundedRect(14, 4, 36, 56, 18, 18)
    p.setBrush(QColor("white"))
    p.drawRoundedRect(30, 12, 4, 14, 2, 2)
    p.end()
    return QIcon(pm)


def main():
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)  # QApplication (not QGuiApplication) for the tray menu
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_icon())

    os.makedirs(APP_DIR, exist_ok=True)
    lock = QLockFile(os.path.join(APP_DIR, "hub.lock"))
    if not lock.tryLock(100):
        QMessageBox.information(None, "MT760 Hub", "MT760 Hub is already running (see the tray).")
        return

    config = Config()
    runner = ActionRunner()
    hub = Hub(config, runner)
    runner.log = hub.logRequested.emit
    runner.dpi_callback = lambda mode, level: hub.dpiActionRequested.emit(mode, level)

    def on_trigger(button, trigger):
        action = config.get(button, trigger)
        if action:
            runner.submit(action, f"{BUTTONS[button]} {TRIGGERS[trigger].lower()}")

    # DPI cycling is the one factory behaviour we can't inject, so remapped presses without an
    # action ask the worker to step the DPI level instead (needs the USB cable).
    hook = ButtonHook(config, on_trigger,
                      on_default=lambda button: hub.dpiActionRequested.emit("next", 0))
    try:
        hook.start()
        hub.log("Button hook active.")
    except OSError as e:
        hub.log(f"Button hook failed to start: {e}")

    flow = Flow()
    flow.toast.connect(hub.toast)
    flow.logRequested.connect(hub.log)
    hub.deviceChanged.connect(lambda: flow.mouseConnection(hub.connected))

    qmlRegisterSingletonInstance(Hub, "MT760", 1, 0, "Hub", hub)
    qmlRegisterSingletonInstance(Flow, "MT760", 1, 0, "FlowSync", flow)  # "Flow" would hide QtQuick's Flow layout
    engine = QQmlApplicationEngine()
    engine.addImportPath(os.path.join(HERE, "qml"))
    engine.load(QUrl.fromLocalFile(os.path.join(HERE, "qml", "Main.qml")))
    if not engine.rootObjects():
        print("Failed to load the interface (see errors above).", file=sys.stderr)
        sys.exit(1)
    window = engine.rootObjects()[0]

    tray = QSystemTrayIcon(make_icon(hub.paused), app)
    tray.setToolTip("MT760 Hub")
    menu = QMenu()
    act_open = QAction("Open MT760 Hub", menu)
    act_pause = QAction("Pause button actions", menu)
    act_pause.setCheckable(True)
    act_pause.setChecked(hub.paused)
    act_quit = QAction("Quit", menu)
    menu.addAction(act_open)
    menu.addAction(act_pause)
    menu.addSeparator()
    menu.addAction(act_quit)
    tray.setContextMenu(menu)

    def show_window():
        window.show()
        window.raise_()
        window.requestActivate()

    def on_paused(on):
        act_pause.setChecked(on)
        tray.setIcon(make_icon(on))

    def quit_app():
        hook.stop()
        runner.shutdown()
        flow.shutdown()
        hub.shutdown()
        tray.hide()
        app.quit()

    act_open.triggered.connect(show_window)
    act_pause.toggled.connect(hub.setPaused)
    hub.pausedToggled.connect(on_paused)
    hub.hideRequested.connect(window.hide)
    act_quit.triggered.connect(quit_app)
    tray.activated.connect(lambda r: show_window() if r == QSystemTrayIcon.Trigger else None)
    tray.show()

    if "--tray" not in sys.argv:
        show_window()
    code = app.exec()
    hook.stop()
    sys.exit(code)


if __name__ == "__main__":
    main()
