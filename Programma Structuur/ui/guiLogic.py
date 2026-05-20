from PyQt5 import QtCore, QtWidgets
from tab_home import TabHome
from tab_cameras import TabCameras
from tab_diagnostics import TabDiagnostics
from tab_directory import TabDirectory
from tab_results import TabResults
from tab_settings import TabSettings
from pathlib import Path
from datetime import datetime
import sys
import webbrowser

# Voeg parent directory toe aan path zodat core module gevonden wordt
sys.path.insert(0, str(Path(__file__).parent.parent))

# --- DE KLASSE VOOR ORCHESTRATIE ---
class Logic:
    def __init__(self, window):
        self.window = window

        self.nav_buttons = [
            self.window.btn_home,
            self.window.btn_cameras,
            self.window.btn_results,
            self.window.btn_directory,
            self.window.btn_diagnostics,
            self.window.btn_advanced_settings
        ]

        self.window.btn_home.clicked.connect(lambda: self.switch_page(0))
        self.window.btn_cameras.clicked.connect(lambda: self.switch_page(1))
        self.window.btn_results.clicked.connect(lambda: self.switch_page(2))
        self.window.btn_directory.clicked.connect(lambda: self.switch_page(3))
        self.window.btn_diagnostics.clicked.connect(lambda: self.switch_page(4))
        self.window.btn_advanced_settings.clicked.connect(lambda: self.switch_page(5))
        
        
        # --- HOME ACTION CONNECTIONS ---
        self.window.btn_newproject.clicked.connect(self.create_new_project)
        self.window.btn_loadproject.clicked.connect(self.load_project)

        # --- INITIALISEER TABS ---
        self.tab_home = TabHome(self)
        self.tab_cameras = TabCameras(self)
        self.tab_results = TabResults(self)
        self.tab_directory = TabDirectory(self)
        self.tab_diagnostics = TabDiagnostics(self)
        self.tab_settings = TabSettings(self)

        # Setup elke tab
        self.tab_home.setup()
        self.tab_cameras.setup()
        self.tab_results.setup()
        self.tab_directory.setup()
        self.tab_diagnostics.setup()
        self.tab_settings.setup()

        # --- MENU ACTION CONNECTIONS ---
        self.window.actionNew_project.triggered.connect(self.create_new_project)
        self.window.actionOpen_project.triggered.connect(self.load_project)
        self.window.actionQuit.triggered.connect(self.quit_application)
        self.window.actionOpen_documentation.triggered.connect(self.open_documentation)

        self.switch_page(0)

    def switch_page(self, index):
        """Wisselt de actieve pagina in het stackedWidget en update de knop-styling"""
        # Verander de pagina van het stackedWidget uit de Designer
        self.window.stackedWidget.setCurrentIndex(index)

        # Styling: De actieve knop krijgt een duidelijke kleur, de rest blijft standaard
        active_style = "background-color: #0078D4; color: white; font-weight: bold; border: 1px solid #005A9E;"
        normal_style = "background-color: #2D2D2D; color: white; border: 1px solid #444;"

        for i, btn in enumerate(self.nav_buttons):
            if i == index:
                btn.setStyleSheet(active_style)
            else:
                btn.setStyleSheet(normal_style)

    def create_new_project(self):
        """Maakt een nieuw projectfolder aan in de sessions map met timestamp"""
        try:
            # Laad de app configuratie
            from core.config import AppConfig
            config = AppConfig.load()
            sessions_dir = config.sessions_dir or Path.cwd() / "sessions"
            
            # Zorg dat de sessions directory bestaat
            sessions_dir.mkdir(parents=True, exist_ok=True)
            
            # Genereer timestamp in formaat: YYYY-MM-DD_HH_MM_SS
            timestamp = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
            project_folder_name = f"Session_{timestamp}"
            project_path = sessions_dir / project_folder_name
            
            # Maak de projectfolder aan
            project_path.mkdir(parents=True, exist_ok=True)
            
            # Navigeer naar de camera's tab en open deze folder
            self.switch_page(1)  # Schakel naar tab_camera (index 1)
            self.tab_directory.load_root_directory(project_path)
            
            print(f"Nieuw project aangemaakt: {project_path}")

            # # Toon succes bericht
            # QtWidgets.QMessageBox.information(
            #     self.window,
            #     "Project aangemaakt",
            #     f"Nieuw project aangemaakt:\n{project_folder_name}"
            # )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.window,
                "Fout",
                f"Kon project niet aanmaken:\n{str(e)}"
            )
            print(f"Fout bij aanmaken project: {str(e)}") 

    def load_project(self):
        """Opent een bestaand projectfolder via bestandsverkenner"""
        try:
            from core.config import AppConfig
            
            # Bepaal de startmap (sessions directory)
            config = AppConfig.load()
            start_dir = config.sessions_dir or Path.cwd() / "sessions"
            
            # Open bestandsverkenner
            selected_dir = QtWidgets.QFileDialog.getExistingDirectory(
                self.window,
                "Selecteer een project map",
                str(start_dir)
            )
            
            if selected_dir:
                project_path = Path(selected_dir)
                
                # Stel deze als het huidige project in
                config.default_sessions_dir = project_path.parent
                config.save()
                
                # Navigeer naar de camera's tab
                self.switch_page(1)
                self.tab_directory.load_root_directory(project_path)

                print(f"Project geladen: {project_path}")
                # # Toon succes bericht               

                # QtWidgets.QMessageBox.information(
                #     self.window,
                #     "Project geladen",
                #     f"Project geladen:\n{project_path.name}"
                # )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.window,
                "Fout",
                f"Kon project niet openen:\n{str(e)}"
            )
            print(f"Fout bij laden project: {str(e)}") 

    def quit_application(self):
        """Sluit de applicatie af"""
        self.window.close()

    def open_documentation(self):
        webbrowser.open('https://github.com/MaxUntersalmberger/PhysioMotionTracker')  # Go to example.com
        print("Documentation opened in web browser.")
