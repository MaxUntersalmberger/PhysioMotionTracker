class apply_styles:
    def __init__(self, window):
        self.window = window
        self.set_custom_style()

    def set_custom_style(self):
        # We stylen het menu frame en de knoppen erin
        self.window.frame_menu.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border: none;
            }
            QPushButton {
                background-color: #34495e;
                color: white;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1abc9c;
            }
            QPushButton:pressed {
                background-color: #16a085;
            }
        """)
        
        # Optioneel: de achtergrond van de pagina's
        self.window.stackedWidget.setStyleSheet("background-color: #ecf0f1;")