from PyQt5 import QtCore, QtWidgets
from tab_main import TabMain
from tab_cameras import TabCameras
from tab_settings import TabSettings

# --- DE KLASSE VOOR ORCHESTRATIE ---
class Logic:
    def __init__(self, window):
        self.window = window

        self.nav_buttons = [
            self.window.btn_main,
            self.window.btn_cameras,
            self.window.btn_settings
        ]

        self.window.btn_main.clicked.connect(lambda: self.switch_page(0))
        self.window.btn_cameras.clicked.connect(lambda: self.switch_page(1))
        self.window.btn_settings.clicked.connect(lambda: self.switch_page(2))

        # --- INITIALISEER TABS ---
        self.tab_main = TabMain(self)
        self.tab_cameras = TabCameras(self)
        self.tab_settings = TabSettings(self)

        # Setup elke tab
        self.tab_main.setup()
        self.tab_cameras.setup()
        self.tab_settings.setup()

        self.switch_page(0)

    def switch_page(self, index):
        """Wisselt de actieve pagina in het stackedWidget en update de knop-styling"""
        # Verander de pagina van het stackedWidget uit de Designer
        self.window.stackedWidget.setCurrentIndex(index)

        # Styling: De actieve knop krijgt een duidelijke kleur, de rest blijft standaard
        active_style = "background-color: #0078D4; color: white; font-weight: bold; border: 1px solid #005A9E;"
        normal_style = "background-color: #2D2D2D; color: white; border: 1px solid #444;"

        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.setStyleSheet(active_style)
            else:
                btn.setStyleSheet(normal_style)