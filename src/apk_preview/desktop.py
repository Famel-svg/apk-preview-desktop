from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtGui import QImage, QMouseEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from .android import DISPLAY_PROFILES, AndroidController
from .errors import PreviewError
from .runner import sanitize_frozen_windows_dll_search
from .session import Session, SessionStore


class Signals(QObject):
    success = Signal(object)
    failure = Signal(str)


T = TypeVar("T")


class Job[T](QRunnable):
    def __init__(self, function: Callable[[], T]) -> None:
        super().__init__()
        self.function = function
        self.signals = Signals()

    def run(self) -> None:
        try:
            self.signals.success.emit(self.function())
        except Exception as exc:  # noqa: BLE001 - worker boundary forwards errors to UI thread
            self.signals.failure.emit(str(exc))


class DeviceView(QLabel):
    tapped = Signal(int, int)

    def __init__(self) -> None:
        super().__init__("Inicie AVD para visualizar")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(360, 640)
        self.setStyleSheet("background:#15171c;color:#9298a5;border-radius:18px;padding:12px")
        self._image_size = (0, 0)
        self._image = QImage()

    def show_png(self, png: bytes) -> None:
        image = QImage.fromData(png)
        self._image = image
        self._image_size = (image.width(), image.height())
        self._render_image()

    def _render_image(self) -> None:
        if not self._image.isNull():
            self.setPixmap(
                QPixmap.fromImage(self._image).scaled(
                    self.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def resizeEvent(self, event: QResizeEvent) -> None:
        self._render_image()
        super().resizeEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pixmap = self.pixmap()
        width, height = self._image_size
        if pixmap and width and height:
            rendered = pixmap.size()
            left = (self.width() - rendered.width()) / 2
            top = (self.height() - rendered.height()) / 2
            x = int((event.position().x() - left) * width / rendered.width())
            y = int((event.position().y() - top) * height / rendered.height())
            if 0 <= x < width and 0 <= y < height:
                self.tapped.emit(x, y)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.controller = AndroidController()
        self.store = SessionStore()
        self.session = self.store.load()
        self.pool = QThreadPool.globalInstance()
        self._jobs: set[QRunnable] = set()
        self._refresh_pending = False
        self.apk_path: Path | None = None
        self.setWindowTitle("APK Preview Desktop")
        self.resize(1180, 820)
        self._build_ui()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self._load_avds()

    def _build_ui(self) -> None:
        toolbar = QToolBar("Sessão")
        self.addToolBar(toolbar)
        self.avd = QComboBox()
        toolbar.addWidget(self.avd)
        start = QPushButton("Iniciar")
        start.clicked.connect(self.start_session)
        toolbar.addWidget(start)
        choose = QPushButton("Escolher APK")
        choose.clicked.connect(self.choose_apk)
        toolbar.addWidget(choose)
        install = QPushButton("Instalar APK")
        install.clicked.connect(self.install_apk)
        toolbar.addWidget(install)
        self.profile = QComboBox()
        self.profile.addItems(list(DISPLAY_PROFILES))
        toolbar.addWidget(self.profile)
        self.orientation = QComboBox()
        self.orientation.addItems(["portrait", "landscape"])
        toolbar.addWidget(self.orientation)
        self.theme = QComboBox()
        self.theme.addItems(["system", "light", "dark"])
        toolbar.addWidget(self.theme)
        self.font_scale = QComboBox()
        self.font_scale.addItems(["1.0", "1.3", "1.5", "2.0"])
        toolbar.addWidget(self.font_scale)
        apply_display = QPushButton("Aplicar tela")
        apply_display.clicked.connect(self.change_display)
        toolbar.addWidget(apply_display)
        stop = QPushButton("Encerrar")
        stop.clicked.connect(self.stop_session)
        toolbar.addWidget(stop)

        root = QSplitter()
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self.device = DeviceView()
        self.device.tapped.connect(self.tap)
        left_layout.addWidget(self.device, 1)
        nav = QHBoxLayout()
        for label, action in (("Voltar", "back"), ("Início", "home"), ("Recentes", "recents")):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, key=action: self.key(key))
            nav.addWidget(button)
        refresh = QPushButton("Atualizar")
        refresh.clicked.connect(self.refresh)
        nav.addWidget(refresh)
        left_layout.addLayout(nav)
        root.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Apps instalados"))
        self.apps = QComboBox()
        right_layout.addWidget(self.apps)
        open_app = QPushButton("Abrir app")
        open_app.clicked.connect(self.launch_app)
        right_layout.addWidget(open_app)
        tree_button = QPushButton("Inspecionar árvore da tela")
        tree_button.clicked.connect(self.inspect_tree)
        right_layout.addWidget(tree_button)
        self.tree = QTextEdit()
        self.tree.setReadOnly(True)
        right_layout.addWidget(self.tree, 1)
        root.addWidget(right)
        root.setSizes([760, 420])
        self.setCentralWidget(root)
        self.statusBar().showMessage("Pronto")

    def _job(
        self,
        function: Callable[[], T],
        on_success: Callable[[T], object] | None = None,
        on_complete: Callable[[], object] | None = None,
    ) -> None:
        job = Job(function)
        self._jobs.add(job)
        if on_success is not None:
            job.signals.success.connect(on_success)

        def release_success(_value: object) -> None:
            self._jobs.discard(job)
            if on_complete is not None:
                on_complete()

        def release_failure(_message: str) -> None:
            self._jobs.discard(job)
            if on_complete is not None:
                on_complete()

        job.signals.success.connect(release_success)
        job.signals.failure.connect(self._show_error)
        job.signals.failure.connect(release_failure)
        self.pool.start(job)

    def _show_error(self, message: str) -> None:
        self.statusBar().showMessage(message)

    def _serial(self) -> str:
        if not self.session:
            raise PreviewError(
                "SESSION_REQUIRED", "Sessão não iniciada.", "Escolha AVD e clique Iniciar."
            )
        return self.session.serial

    def _load_avds(self) -> None:
        def loaded(names: list[str]) -> None:
            self.avd.addItems(names)
            self.timer.start(2500)
            if self.session:
                self.refresh()

        self._job(self.controller.list_avds, loaded)

    def start_session(self) -> None:
        avd = self.avd.currentText()
        self.statusBar().showMessage("Iniciando Android…")

        def done(serial: str) -> None:
            self.session = Session(serial=serial, avd=avd)
            self.store.save(self.session)
            self.refresh_apps()
            self.refresh()

        self._job(lambda: self.controller.start_avd(avd), done)

    def choose_apk(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Escolher APK", "", "Android APK (*.apk)")
        if path:
            self.apk_path = Path(path)
            self.statusBar().showMessage(path)

    def install_apk(self) -> None:
        if not self.apk_path:
            QMessageBox.information(self, "APK", "Escolha arquivo APK primeiro.")
            return
        apk_path = self.apk_path
        self._job(
            lambda: self.controller.install_apk(self._serial(), apk_path),
            lambda _value: self.refresh_apps(),
        )

    def refresh_apps(self) -> None:
        def done(packages: list[str]) -> None:
            self.apps.clear()
            self.apps.addItems(packages)

        self._job(lambda: self.controller.list_apps(self._serial()), done)

    def launch_app(self) -> None:
        package = self.apps.currentText()

        def launch() -> None:
            self.controller.launch_app(self._serial(), package)
            if self.session:
                self.session.active_package = package
                self.store.save(self.session)

        self._job(launch, lambda _value: self.refresh())

    def refresh(self) -> None:
        if self.session and not self._refresh_pending:
            self._refresh_pending = True
            self._job(
                lambda: self.controller.capture(self._serial()),
                self.device.show_png,
                self._refresh_finished,
            )

    def _refresh_finished(self) -> None:
        self._refresh_pending = False

    def inspect_tree(self) -> None:
        self._job(lambda: self.controller.ui_tree(self._serial()), self.tree.setPlainText)

    def change_display(self) -> None:
        if self.session:
            profile = self.profile.currentText()
            orientation = self.orientation.currentText()
            theme = self.theme.currentText()
            font_scale = float(self.font_scale.currentText())
            self._job(
                lambda: self.controller.configure_display(
                    self._serial(), profile, orientation, theme, font_scale
                ),
                lambda _value: self.refresh(),
            )

    def stop_session(self) -> None:
        if not self.session:
            return

        def stopped(_value: None) -> None:
            self.store.clear()
            self.session = None
            self.device.clear()
            self.device.setText("Sessão encerrada")

        self._job(lambda: self.controller.stop(self._serial()), stopped)

    def key(self, name: str) -> None:
        self._job(lambda: self.controller.key(self._serial(), name), lambda _value: self.refresh())

    def tap(self, x: int, y: int) -> None:
        self._job(lambda: self.controller.tap(self._serial(), x, y), lambda _value: self.refresh())


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    sanitize_frozen_windows_dll_search()
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
