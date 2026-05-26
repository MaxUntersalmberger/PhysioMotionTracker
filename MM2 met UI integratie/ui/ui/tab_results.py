class TabResults:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.window = logic_instance.window

    def setup(self):
        """Initialiseert de results tab"""
        # Haal de UI-referentie op uit je main window
        ui = self.window

        # Knop 1: Van het resultatenoverzicht NAAR de preview pagina
        ui.btn_res_show_tmol.clicked.connect(self.go_to_preview)

        # Knop 2: Van de preview pagina TERUG naar het resultatenoverzicht
        # Let op: in je GUI heet de sluitknop (het kruisje 'x') 'pushButton'
        ui.pushButton.clicked.connect(self.go_to_results_tab)

    def go_to_preview(self):
        """Schakelt naar de Preview TMOL pagina (Index 1)"""
        self.window.stackedWidget_2.setCurrentIndex(1)

    def go_to_results_tab(self):
        """Schakelt terug naar de Results Tab pagina (Index 0)"""
        self.window.stackedWidget_2.setCurrentIndex(0)