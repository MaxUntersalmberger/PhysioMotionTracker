from __future__ import annotations

import logging
import sys

from PySide6.QtWidgets import QApplication

from core.config import AppConfig
from core.logging import configure_logging
from ui.main_window import MainWindow


def run_ui(config: AppConfig | None = None, argv: list[str] | None = None) -> int:
    resolved_config = config or AppConfig()
    resolved_config.ensure_directories()
    if not logging.getLogger().handlers:
        configure_logging(resolved_config.logs_dir)

    app = QApplication(argv or sys.argv)
    window = MainWindow(resolved_config)
    window.show()
    return app.exec()
