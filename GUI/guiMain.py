from guiDesigner.gui import Ui_MainWindow
from PyQt5.QtWidgets import QApplication, QMainWindow
from guiStyle import apply_styles
from guiLogic import Logic
import sys

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        apply_styles(self)        # pas de styling toe
        self.logic = Logic(self)  # koppel de logica

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
    