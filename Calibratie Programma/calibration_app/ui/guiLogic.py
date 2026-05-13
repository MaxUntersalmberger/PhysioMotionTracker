from PyQt5 import QtCore, QtWidgets
from calibration_app.ui.tab_home import TabHome
from calibration_app.ui.tab_cameras import TabCameras
from calibration_app.ui.tab_diagnostics import TabDiagnostics
from calibration_app.ui.tab_directory import TabDirectory
from calibration_app.ui.tab_results import TabResults
from calibration_app.ui.tab_settings import TabSettings
from pathlib import Path
from datetime import datetime
import sys
import webbrowser

# Voeg parent directory toe aan path zodat core module gevonden wordt
sys.path.insert(0, str(Path(__file__).parent.parent))

from ..config import CalibrationAppConfig
# --- DE KLASSE VOOR ORCHESTRATIE ---
class Logic:
    def __init__(self, window):
        self.window = window
        

        self.nav_buttons = [
            self.window.btn_home,
            self.window.btn_cameras,
            self.window.btn_directory,
            self.window.btn_results,
            self.window.btn_diagnostics,
            self.window.btn_advanced_settings
        ]

        self.window.btn_home.clicked.connect(lambda: self.switch_page(0))
        self.window.btn_cameras.clicked.connect(lambda: self.switch_page(1))
        self.window.btn_results.clicked.connect(lambda: self.switch_page(2))
        self.window.btn_directory.clicked.connect(lambda: self.switch_page(3))
        self.window.btn_diagnostics.clicked.connect(lambda: self.switch_page(4))
        self.window.btn_advanced_settings.clicked.connect(lambda: self.switch_page(5))
        
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        
        

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
        try:
            from pathlib import Path
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))

            from ..config import CalibrationAppConfig
            from ..project import CalibrationProjectRepository

            config = CalibrationAppConfig.load()
            timestamp = datetime.now().strftime("%Y-%m-%d_%H_%M_%S")
            name = f"Session_{timestamp}"

            repo = CalibrationProjectRepository(config.projects_dir)
            project = repo.create(name=name, sources_csv="0", target_fps=20.0)

            self._active_project = project
            self.switch_page(1)
            self.tab_directory.load_root_directory(project.root_dir)

            print(f"Nieuw project aangemaakt: {project.root_dir}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self.window, "Fout", f"Kon project niet aanmaken:\n{str(e)}")
            print(f"Fout bij aanmaken project: {str(e)}")

    def load_project(self):
        try:
            from pathlib import Path
            import sys
            sys.path.insert(0, str(Path(__file__).parent.parent))

            from ..config import CalibrationAppConfig

            config = CalibrationAppConfig.load()
            start_dir = config.projects_dir or Path.cwd() / "projects"

            selected_dir = QtWidgets.QFileDialog.getExistingDirectory(
                self.window, "Selecteer een project map", str(start_dir)
            )

            if selected_dir:
                project_path = Path(selected_dir)
                self.switch_page(1)
                self.tab_directory.load_root_directory(project_path)
                print(f"Project geladen: {project_path}")

        except Exception as e:
            QtWidgets.QMessageBox.critical(self.window, "Fout", f"Kon project niet openen:\n{str(e)}")
            print(f"Fout bij laden project: {str(e)}")

    def quit_application(self):
        """Sluit de applicatie af"""
        self.window.close()

    def open_documentation(self):
        webbrowser.open('https://github.com/MaxUntersalmberger/PhysioMotionTracker')  # Go to example.com
        print("Documentation opened in web browser.")
