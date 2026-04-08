from PyQt5 import QtCore

class apply_styles:
    def __init__(self, window):
        self.window = window
        self.set_custom_style()

    def set_custom_style(self):
        # Modern Dark Medical Theme
        self.window.setStyleSheet("""
            QMainWindow { background-color: #121212; }
            
            /* Sidebar Consistency */
            QFrame#frame_menu { 
                background-color: #1E1E1E; 
                border-right: 1px solid #333;
            }
            
            /* Typography Accessibility */
            QLabel { color: #FFFFFF; font-family: 'Segoe UI'; font-size: 14px; }
            
            /* Buttons Affordance */
            QPushButton {
                background-color: #2D2D2D;
                color: white;
                border-radius: 8px;
                padding: 10px;
                border: 1px solid #444;
            }
            QPushButton:hover { background-color: #3D3D3D; border: 1px solid #0078D4; }
            
            /* Main Action Hierarchy (Calibration Button) */
            QPushButton#pushButton {
                background-color: #0078D4;
                font-weight: bold;
                font-size: 16px;
                border: none;
            }
            QPushButton#pushButton:hover { background-color: #1084E3; }
            QPushButton#pushButton:disabled { background-color: #555; color: #AAA; }
            
            /* Dropdown Consistency */
            QComboBox {
                background-color: #2D2D2D;
                color: white;
                border: 1px solid #444;
                padding: 5px;
                border-radius: 4px;
            }
        """)
        
        # Voeg hand-cursor toe voor alle interactieve elementen (Affordance)
        self.window.btn_main.setCursor(QtCore.Qt.PointingHandCursor)
        self.window.btn_cameras.setCursor(QtCore.Qt.PointingHandCursor)
        self.window.btn_settings.setCursor(QtCore.Qt.PointingHandCursor)
        self.window.pushButton.setCursor(QtCore.Qt.PointingHandCursor)