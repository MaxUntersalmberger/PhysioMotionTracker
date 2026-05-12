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
#sys.path.insert(0, str(Path(__file__).parent.parent))

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
        
        
        # --- HOME ACTION CONNECTIONS ---
        self.window.btn_newproject.clicked.connect(self.create_new_project)
        self.window.btn_loadproject.clicked.connect(self.load_project)
        
        # Voeg de rest toe zodra je die knoppen in de UI hebt:

        self.window.search_cameras.clicked.connect(self.probe_sources)
        # self.window.btn_capture_sample.clicked.connect(self.capture_sample)
        # self.window.btn_start_live.clicked.connect(self.start_live)
        # self.window.btn_stop.clicked.connect(self.stop_capture)
        # self.window.btn_capture_calib.clicked.connect(self.capture_calibration_sample)
        # self.window.btn_solve_intrinsics.clicked.connect(self.solve_intrinsics)
        # self.window.btn_solve_extrinsics.clicked.connect(self.solve_extrinsics)
        # self.window.btn_load_profile.clicked.connect(self.load_profile)
        # self.window.btn_save_profile.clicked.connect(self.save_profile)
        # self.window.btn_export_profile.clicked.connect(self.export_profile)
        # self.window.btn_reset_samples.clicked.connect(self.reset_samples)


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
        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))

        from calibration_app.config import CalibrationAppConfig
        from calibration_app.project import CalibrationProjectRepository
        from calibration_app.calibration_manager import CalibrationOnlyManager

        from calibration_app.legacy_bridge import ensure_legacy_path
        ensure_legacy_path()

        from calibration.repository import CalibrationRepository
        from capture.backend import OpenCVCaptureSession
        from capture.sources import parse_sources_csv

        self._config = CalibrationAppConfig.load()
        self._project_repo = CalibrationProjectRepository(self._config.projects_dir)
        self._calib_repo = CalibrationRepository()
        self._calib_manager = CalibrationOnlyManager()
        self._active_project = None
        self._current_bundle = None
        self._capture_session = None

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

# --- NEW PROJECT ---
    def create_new_project(self):
        try:
            from datetime import datetime
            name = f"Session_{datetime.now().strftime('%Y-%m-%d_%H_%M_%S')}"
            project = self._project_repo.create(name=name, sources_csv="0", target_fps=20.0)
            self._active_project = project
            self.switch_page(1)
            print(f"Project aangemaakt: {project.root_dir}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.window, "Fout", f"Kon project niet aanmaken:\n{str(e)}")
            print(f"Fout bij aanmaken project: {str(e)}")

# --- OPEN PROJECT ---
    def load_project(self):
        try:
            start = str(self._config.projects_dir)
            selected = QtWidgets.QFileDialog.getExistingDirectory(self.window, "Selecteer project", start)
            if selected:    
                from calibration_app.project import CalibrationProjectRepository
                self._active_project = self._project_repo.load(Path(selected))
                self.switch_page(1)
                print(f"Project geladen: {self._active_project.name}")
        except Exception as e:
            QtWidgets.QMessageBox.critical(self.window, "Fout", f"Kon project niet openen:\n{str(e)}")
            print(f"Fout bij laden project: {str(e)}")

# --- PROBE SOURCES ---
def probe_sources(self):
    sources_csv = self.window.lineedit_sources.text().strip() or "0"
    sources = parse_sources_csv(sources_csv)
    session = OpenCVCaptureSession(sources=sources, target_fps=20.0, max_frame_width=1280)
    try:
        session.open()
        print(f"Bronnen bereikbaar: {sources_csv}")
    except Exception as e:
        print(f"Probe mislukt: {e}")
    finally:
        session.close()

# --- CAPTURE SAMPLE ---
def capture_sample(self):
    sources_csv = self.window.lineedit_sources.text().strip() or "0"
    fps = float(self.window.spin_cap_fps.value())
    sources = parse_sources_csv(sources_csv)
    session = OpenCVCaptureSession(sources=sources, target_fps=fps, max_frame_width=1280)
    try:
        session.open()
        batch = session.read_batch()
        print(f"Sample captured: {len(batch.frames)} frames")
    except Exception as e:
        print(f"Capture mislukt: {e}")
    finally:
        session.close()

# --- SOLVE INTRINSICS ---
def solve_intrinsics(self):
    readiness = self._calib_manager.workflow_readiness()
    if not readiness.can_solve_intrinsics:
        print(f"Nog niet klaar: {' | '.join(readiness.notes)}")
        return
    result = self._calib_manager.solve_intrinsics()
    self._current_bundle = result.bundle
    print(f"Intrinsics opgelost: {result.sample_counts}")

# --- SOLVE EXTRINSICS ---
def solve_extrinsics(self):
    readiness = self._calib_manager.workflow_readiness()
    if not readiness.can_solve_extrinsics:
        print(f"Nog niet klaar: {' | '.join(readiness.notes)}")
        return
    result = self._calib_manager.solve_extrinsics()
    self._current_bundle = result.bundle
    print(f"Extrinsics opgelost.")

# --- LOAD PROFILE ---
def load_profile(self):
    path, _ = QtWidgets.QFileDialog.getOpenFileName(self.window, "Laad profiel", "", "JSON (*.json)")
    if path:
        self._current_bundle = self._calib_repo.load(Path(path))
        print(f"Profiel geladen: {path}")

# --- SAVE PROFILE ---
def save_profile(self):
    if self._current_bundle is None:
        print("Geen profiel om op te slaan.")
        return
    profile_path = self._active_project.default_profile_path if self._active_project else Path("calibration.json")
    self._calib_repo.save(self._current_bundle, profile_path)
    print(f"Profiel opgeslagen: {profile_path}")

# --- EXPORT PROFILE ---
def export_profile(self):
    if self._current_bundle is None or self._active_project is None:
        print("Geen profiel of project beschikbaar.")
        return
    from datetime import datetime
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_path = self._active_project.exports_dir / f"calibration_{stamp}.json"
    self._calib_repo.save(self._current_bundle, export_path)
    print(f"Profiel geëxporteerd: {export_path}")

# --- RESET SAMPLES ---
def reset_samples(self):
    self._calib_manager.reset_samples()
    print("Samples gereset.")

    def quit_application(self):
        """Sluit de applicatie af"""
        self.window.close()

    def open_documentation(self):
        webbrowser.open('https://github.com/MaxUntersalmberger/PhysioMotionTracker')  # Go to example.com
        print("Documentation opened in web browser.")
