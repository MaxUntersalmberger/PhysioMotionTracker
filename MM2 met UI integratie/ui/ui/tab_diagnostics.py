from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QGuiApplication


class TabDiagnostics:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.window = logic_instance.window

    def setup(self):
        """Initialiseert alle widgets op de instellingenpagina"""
        if hasattr(self.window, 'combo_set_res'):
            self.window.combo_set_res.blockSignals(True)
            self.window.combo_set_res.clear()
            self.window.combo_set_res.addItems(["988x720", "1280x720", "1920x1080", "Fullscreen"])
            self.window.combo_set_res.setCurrentIndex(0)
            self.window.combo_set_res.blockSignals(False)

            self.window.combo_set_res.currentIndexChanged.connect(self.change_window_size)

    def change_window_size(self):
        """Handelt resoluties af en zorgt dat Fullscreen ook echt het scherm vult"""
        res_text = self.window.combo_set_res.currentText()

        if res_text == "Fullscreen":
            # STAP 1: Hef de vaste maat op zodat het venster kan groeien
            self.window.setMinimumSize(0, 0)
            self.window.setMaximumSize(16777215, 16777215)
            self.window.centralwidget.setMinimumSize(0, 0)
            self.window.centralwidget.setMaximumSize(16777215, 16777215)

            # STAP 2: Ga naar Fullscreen
            self.window.showFullScreen()
        else:
            # Altijd terug naar normale modus
            if self.window.isFullScreen():
                self.window.showNormal()

            try:
                # Breedte en hoogte bepalen
                width, height = map(int, res_text.split('x'))

                # Zet het venster EN de centralwidget op de vaste maat
                self.window.centralwidget.setFixedSize(width, height)
                self.window.setFixedSize(width, height)

                # Centreer het venster op het scherm
                self.center_window()
            except ValueError:
                pass

    def center_window(self):
        """Hulpmethode om venster te centreren"""
        qr = self.window.frameGeometry()
        cp = QGuiApplication.primaryScreen().availableGeometry().center()
        qr.moveCenter(cp)
        self.window.move(qr.topLeft())
