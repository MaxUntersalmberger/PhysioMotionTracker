from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from mocap_app.core.config import AppConfig
from mocap_app.core.logging_config import configure_logging
from mocap_app.ui.main_window import MainWindow


def run() -> int:
    config = AppConfig()
    config.ensure_directories()
    configure_logging(config.logs_dir)

    app = QApplication(sys.argv)
    window = MainWindow(config=config)
    window.show()
    return app.exec()

