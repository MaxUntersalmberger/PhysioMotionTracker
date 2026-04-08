from guiDesigner.gui import Ui_MainWindow
from PyQt5.QtWidgets import QApplication, QMainWindow
from guiLogic import Logic
from guiStyle import apply_styles  # Import de klasse
import sys

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        
        # Pas styling toe
        apply_styles(self)
        
        # Koppel de logica
        self.logic = Logic(self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())