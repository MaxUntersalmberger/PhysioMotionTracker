class Logic:
    def __init__(self, window):
        self.window = window
        
        # Koppel de knoppen aan de pagina's van de stackedWidget
        # Index 0 = Main, Index 1 = Camera's, Index 2 = Settings (gebaseerd op je gui.py)
        self.window.btn_main.clicked.connect(lambda: self.window.stackedWidget.setCurrentIndex(0))
        self.window.btn_cameras.clicked.connect(lambda: self.window.stackedWidget.setCurrentIndex(1))
        self.window.btn_settings.clicked.connect(lambda: self.window.stackedWidget.setCurrentIndex(2))

    # De oude toggle_hello functie heb ik verwijderd omdat de objecten 
    # (pushButton en label) niet meer in je nieuwe gui.py staan.