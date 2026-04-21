from PyQt5 import QtWidgets
from pathlib import Path
import shutil


class TabProcessing:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.window = logic_instance.window

    def setup(self):
        """Initialiseert de processing tab"""
        # Verbind knoppen met event handlers
        self.window.btn_export_toml.clicked.connect(self.on_export_toml)
        self.window.btn_start_processing.clicked.connect(self.on_start_processing)

    def on_export_toml(self):
        """Handler voor Export TOML knop - laat gebruiker bestand opslaan"""
        # Get the path to the template TOML file
        config_file = Path(__file__).parent / "config.toml"
        
        if not config_file.exists():
            QtWidgets.QMessageBox.warning(
                self.window,
                "Fout",
                "Config bestand niet gevonden!"
            )
            return
        
        # Open file save dialog
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self.window,
            "Export TOML bestand",
            "export_config.toml",
            "TOML Files (*.toml);;All Files (*)"
        )
        
        if file_path:
            try:
                # Copy the template file to the selected location
                shutil.copy(str(config_file), file_path)
                QtWidgets.QMessageBox.information(
                    self.window,
                    "Succes",
                    f"TOML bestand succesvol geëxporteerd naar:\n{file_path}"
                )
                print(f"TOML exported to: {file_path}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(
                    self.window,
                    "Fout bij exporteren",
                    f"Fout bij het exporteren van het bestand:\n{str(e)}"
                )

    def on_start_processing(self):
        """Handler voor Start Processing knop"""
        print("Start Processing clicked")
        # TODO: Implementeer processing start functionaliteit
