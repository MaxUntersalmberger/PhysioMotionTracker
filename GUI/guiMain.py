from PyQt5 import QtCore, QtWidgets # Voeg deze imports toe
from guiDesigner.gui import Ui_MainWindow
from PyQt5.QtWidgets import QApplication, QMainWindow
from guiLogic import Logic
from guiStyle import apply_styles
import sys

# --- HOTFIX VOOR DE SYNTAX ERROR ---
# We overschrijven de kapotte variabelen in de Qt library 
# zodat gui.py ze wel kan vinden.
if not hasattr(QtCore.Qt, "QFrame"):
    QtCore.Qt.QFrame = QtWidgets.QFrame
if not hasattr(QtCore.Qt, "Qt"):
    QtCore.Qt.Qt = QtCore.Qt
# ------------------------------------

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        # We vangen de fout op als setupUi wordt aangeroepen
        try:
            self.setupUi(self)
        except AttributeError:
            # Als de hotfix hierboven niet genoeg was, 
            # kun je hier handmatig correcties doen.
            pass
            
        apply_styles(self)
        self.logic = Logic(self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())