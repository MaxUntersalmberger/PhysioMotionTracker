from guiDesigner.gui import Ui_MainWindow
from PyQt5.QtWidgets import QApplication, QMainWindow
from guiLogic import Logic
from guiStyle import apply_styles
import sys

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        apply_styles(self)
        self.logic = Logic(self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())