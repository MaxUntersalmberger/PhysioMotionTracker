import ctypes
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HU.PhysioMotionTracker.1")

from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QApplication, QMainWindow
from PyQt5.QtGui import QIcon
from pathlib import Path
import sys
import os

# Add calibration_app parent directory to path for proper package imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Relatief pad vanuit guiMain.py naar de imagesGUI map
sys.path.append(os.path.join(os.path.dirname(__file__), "imagesGUI"))



#pyrcc5 resources.qrc -o resources_rc.py 


# Patch: fix voor QtCore.Qt.QFrame references in de gegenereerde gui.py
if not hasattr(QtCore.Qt, 'QFrame'):
    QtCore.Qt.QFrame = QtWidgets.QFrame

from calibration_app.ui.gui import Ui_MainWindow
from calibration_app.ui.guiLogic import Logic
from calibration_app.ui.guiStyle import apply_styles
import io

# --- CONSOLE STREAM REDIRECTOR ---
class ConsoleStream(io.StringIO):
    """Stream class that redirects output to the console widget"""
    def __init__(self, console_widget):
        super().__init__()
        self.console_widget = console_widget
    
    def write(self, text):
        """Schrijft tekst naar de console widget"""
        if text.strip():  # Alleen niet-lege tekst schrijven
            self.console_widget.appendPlainText(text.rstrip())
        return len(text)
    
    def flush(self):
        """Flush operatie (geen-op voor GUI)"""
        pass

class MainWindow(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        apply_styles(self)
        
        # Redirect stdout en stderr naar de console widget
        sys.stdout = ConsoleStream(self.plaintextedit_console)
        sys.stderr = ConsoleStream(self.plaintextedit_console)
        
        self.logic = Logic(self)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(":/HU_Logo.png"))
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec_())