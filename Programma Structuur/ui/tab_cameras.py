import cv2
import time
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimedia import QCameraInfo

class CameraThread(QtCore.QThread):
    change_pixmap_signal = QtCore.pyqtSignal(QtGui.QImage)

    def __init__(self, camera_index=0, width=640, height=480, fps=30): # FPS toegevoegd aan init
        super().__init__()
        self.camera_index = camera_index
        self.fps = fps 
        self.width = width
        self.height = height
        self._run_flag = True
        self.rotate = 0  
        self.mirror = False
        self.exposure = -5 

    def run(self):
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        current_w, current_h = 0, 0
        current_exp = None

        while self._run_flag:
            start_time = time.time()
            if not cap.isOpened():
                time.sleep(0.1)
                continue

            if current_w != self.width or current_h != self.height:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                current_w, current_h = self.width, self.height
            
            if current_exp != self.exposure:
                cap.set(cv2.CAP_PROP_EXPOSURE, self.exposure)
                current_exp = self.exposure

            ret, frame = cap.read()
            if ret:
                if self.mirror:
                    frame = cv2.flip(frame, 1)

                if self.rotate == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif self.rotate == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                elif self.rotate == 270:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_img = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                self.change_pixmap_signal.emit(qt_img.copy())

            # De FPS bepaalt de slaaptijd
            sleep_time = max(1/self.fps - (time.time() - start_time), 0.001)
            time.sleep(sleep_time)

        cap.release()

    def update_params(self, width, height, rotate, mirror, exposure):
        self.width = width
        self.height = height
        self.rotate = rotate
        self.mirror = mirror
        self.exposure = exposure

    def stop(self):
        self._run_flag = False
        self.wait()

class CameraFrame(QtWidgets.QFrame):
    def __init__(self, on_delete_callback):
        super().__init__()
        self.on_delete_callback = on_delete_callback
        self.thread = None
        self.parent_tab = None # Wordt later gezet

        self.intrinsic_captures = 0
        # Status of deze camera momenteel gemaximaliseerd is
        self.is_maximized = False
        self.popout_window = None
        
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setMinimumSize(250, 200)
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        # --- Controls ---
        self.controls_layout = QtWidgets.QHBoxLayout()
        self.combo_select_cam = QtWidgets.QComboBox()
        self.refresh_camera_list() 
        self.combo_select_cam.currentIndexChanged.connect(self.manage_thread)

        self.btn_maximize = QtWidgets.QPushButton("⛶")
        self.btn_maximize.setFixedSize(30, 30)
        self.btn_maximize.setToolTip("Vergroot / Verklein deze camera")
        self.btn_maximize.clicked.connect(self.toggle_maximize)
        
        self.btn_settings = QtWidgets.QPushButton("⋮")
        self.btn_settings.setFixedSize(30, 30)
        self.btn_settings.setCheckable(True)
        self.btn_settings.clicked.connect(self.toggle_view)

        self.btn_delete = QtWidgets.QPushButton("X")
        self.btn_delete.setFixedSize(30, 30)
        self.btn_delete.clicked.connect(self.full_cleanup)

        self.controls_layout.addWidget(self.combo_select_cam, 1)
        self.controls_layout.addWidget(self.btn_maximize)
        self.controls_layout.addWidget(self.btn_settings)
        self.controls_layout.addWidget(self.btn_delete)
        self.main_layout.addLayout(self.controls_layout)

        # --- Inhoud ---
        self.stacked = QtWidgets.QStackedWidget()
        self.video_label = QtWidgets.QLabel("Selecteer een camera")
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: white;")
        
        self.settings_frame = QtWidgets.QFrame()
        self.settings_layout = QtWidgets.QFormLayout(self.settings_frame)
        
        self.spin_width = QtWidgets.QSpinBox(); self.spin_width.setRange(160, 3840); self.spin_width.setValue(640)
        self.spin_height = QtWidgets.QSpinBox(); self.spin_height.setRange(120, 2160); self.spin_height.setValue(480)
        self.combo_rotate = QtWidgets.QComboBox(); self.combo_rotate.addItems(["0", "90", "180", "270"])
        self.check_mirror = QtWidgets.QCheckBox("Mirror Image")
        self.spin_exposure = QtWidgets.QSpinBox(); self.spin_exposure.setRange(-13, 0); self.spin_exposure.setValue(-5)

        self.btn_apply = QtWidgets.QPushButton("Apply Settings")
        self.btn_apply.clicked.connect(self.apply_settings)
        self.btn_apply.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")

        self.settings_layout.addRow("Width (px):", self.spin_width)
        self.settings_layout.addRow("Height (px):", self.spin_height)
        self.settings_layout.addRow("Rotate (°):", self.combo_rotate)
        self.settings_layout.addRow("Mirror:", self.check_mirror)
        self.settings_layout.addRow("Exposure:", self.spin_exposure)
        self.settings_layout.addRow("", self.btn_apply)
        
        self.stacked.addWidget(self.video_label)
        self.stacked.addWidget(self.settings_frame)
        self.main_layout.addWidget(self.stacked)

        # --- Progressiebalk voor Intrinsics Captures (NIEUW) ---
        self.progress_intrinsics = QtWidgets.QProgressBar()
        self.progress_intrinsics.setRange(0, 100)
        self.progress_intrinsics.setValue(0)
        self.progress_intrinsics.setAlignment(QtCore.Qt.AlignCenter)
        self.update_progress_text() # Zet de initiële tekst naar "0/100"
        self.main_layout.addWidget(self.progress_intrinsics)

    def update_progress_text(self):
        """Zorgt dat de tekst altijd 'aantal/100' toont, ook boven de 100."""
        self.progress_intrinsics.setFormat(f"{self.intrinsic_captures}/100")

    def add_intrinsic_capture(self):
        """Hoog de capture teller op en update de progressiebalk."""
        self.intrinsic_captures += 1
        
        # De balk vult tot max 100%, maar de waarde blijft intern stijgen
        visual_value = min(self.intrinsic_captures, 100)
        self.progress_intrinsics.setValue(visual_value)
        self.update_progress_text()

    def refresh_camera_list(self):
        self.combo_select_cam.blockSignals(True)
        self.combo_select_cam.clear()
        self.combo_select_cam.addItem("Geen Camera", -1)
        cameras = QCameraInfo.availableCameras()
        for i, cam in enumerate(cameras):
            self.combo_select_cam.addItem(cam.description(), i)
        self.combo_select_cam.blockSignals(False)

    def manage_thread(self):
        # Stop bestaande thread als die er al is
        if self.thread:
            self.thread.stop()
            self.thread = None

        opencv_idx = self.combo_select_cam.currentData()
        if opencv_idx is not None and opencv_idx != -1:
            # Haal direct de FPS op uit de spinbox in de GUI
            global_fps = self.parent_tab.ui.spin_cap_fps.value()
            
            # Maak de thread aan en start hem direct
            self.thread = CameraThread(
                camera_index=opencv_idx, 
                width=self.spin_width.value(), 
                height=self.spin_height.value(),
                fps=global_fps
            )
            self.apply_settings()
            self.thread.change_pixmap_signal.connect(self.update_frame)
            self.thread.start()
        else:
            self.video_label.setText("Selecteer een camera")

    def apply_settings(self):
        if self.thread and self.thread.isRunning():
            self.thread.update_params(
                width=self.spin_width.value(),
                height=self.spin_height.value(),
                rotate=int(self.combo_rotate.currentText()),
                mirror=self.check_mirror.isChecked(),
                exposure=self.spin_exposure.value()
            )

    def toggle_view(self):
        self.stacked.setCurrentIndex(1 if self.btn_settings.isChecked() else 0)

    def full_cleanup(self):
        if self.thread: self.thread.stop()
        self.on_delete_callback(self)

    def reset_intrinsic_captures(self):
        """Zet de intrinsics teller en de progressiebalk volledig terug naar 0."""
        self.intrinsic_captures = 0
        self.progress_intrinsics.setValue(0)
        self.update_progress_text()

    def toggle_maximize(self):
        """Opent een nieuw los venster voor deze camera met een live feed."""
        if not self.is_maximized:
            # Controleer eerst of er wel een camera is geselecteerd
            if self.combo_select_cam.currentData() == -1 or not self.thread:
                QtWidgets.QMessageBox.warning(self, "Geen actieve camera", 
                    "Selecteer eerst een werkende camera voordat je deze vergroot.")
                return

            self.is_maximized = True
            
            # Maak een nieuw los venster aan
            self.popout_window = QtWidgets.QDialog(self)
            cam_title = self.combo_select_cam.currentText()
            self.popout_window.setWindowTitle(f"Live Feed - {cam_title}")
            self.popout_window.resize(800, 600)
            
            # Maak de layout voor het losse venster
            layout = QtWidgets.QVBoxLayout(self.popout_window)
            layout.setContentsMargins(0, 0, 0, 0)
            
            # Maak het videolabel aan
            self.popout_window.label_video = QtWidgets.QLabel("Live video stream start...")
            self.popout_window.label_video.setAlignment(QtCore.Qt.AlignCenter)
            self.popout_window.label_video.setStyleSheet("background-color: black;")
            
            # CRUCIALE FIX: Sta toe dat het label krimpt naar 1x1 pixel. 
            # Hierdoor kun je het venster te allen tijde kleiner slepen!
            self.popout_window.label_video.setMinimumSize(1, 1)
            
            layout.addWidget(self.popout_window.label_video)
            
            # We slaan het laatste QImage frame op in de class om te gebruiken bij resizen
            self.last_img_frame = None
            
            # Zorg dat het beeld direct vloeiend meeschaalt (zowel groter als kleiner)
            def popout_resize_event(event):
                if hasattr(self, 'last_img_frame') and self.last_img_frame:
                    pixmap = QtGui.QPixmap.fromImage(self.last_img_frame)
                    self.popout_window.label_video.setPixmap(pixmap.scaled(
                        self.popout_window.label_video.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation
                    ))
                QtWidgets.QDialog.resizeEvent(self.popout_window, event)
                
            self.popout_window.resizeEvent = popout_resize_event
            
            # Koppel het sluit-signaal
            self.popout_window.rejected.connect(self.window_closed)
            
            # Toon het venster
            self.popout_window.show()
            
            if self.parent_tab:
                self.parent_tab.log_to_console(f"Systeem: Camera ({cam_title}) geopend in los venster.")
        else:
            if self.popout_window:
                self.popout_window.close()

    def update_frame(self, img):
        """Verwerkt het binnenkomende OpenCV frame en toont deze op de juiste plek."""
        # Sla het originele frame op voor de resizeEvent van het grote venster
        self.last_img_frame = img
        pixmap = QtGui.QPixmap.fromImage(img)
        
        # Als het pop-out venster openstaat, sturen we het beeld daarheen
        if self.is_maximized and self.popout_window and hasattr(self.popout_window, 'label_video'):
            self.popout_window.label_video.setPixmap(pixmap.scaled(
                self.popout_window.label_video.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation
            ))
            
            # Laat in het kleine frame achterblijven dat hij gemaximaliseerd is
            if self.video_label.text() != "Gemaximaliseerd...":
                self.video_label.setText("Gemaximaliseerd...")
                
        elif not self.btn_settings.isChecked():
            # Anders sturen we het beeld gewoon naar het normale kleine frame in de GUI
            self.video_label.setPixmap(pixmap.scaled(
                self.video_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation
            ))

    def window_closed(self):
        """Wordt aangeroepen als het losse venster wordt gesloten."""
        self.is_maximized = False
        self.popout_window = None
        self.video_label.setText("Video herstelt...")
        if self.parent_tab:
            self.parent_tab.log_to_console("Systeem: Los venster gesloten, video hersteld naar grid.")

    def resizeEvent(self, event):
        self.setFixedHeight(int(self.width() * 0.80))
        super().resizeEvent(event)

class TabCameras:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.ui = logic_instance.window
        self.camera_frames = []

    def setup(self):
        self.main_layout = self.ui.gridLayout_6
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_content = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        
        for i in range(3): self.grid_layout.setColumnStretch(i, 1)
        
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)

        # --- NIEUW: Maak de Intrinsics & Extrinsics knoppen checkable ---
        self.ui.btn_cap_intrinsics_start.setCheckable(True)
        self.ui.btn_cap_extrinsics_start.setCheckable(True)
        
        # --- NIEUW: Koppel de functies aan de knoppen ---
        self.ui.btn_cap_intrinsics_start.clicked.connect(self.toggle_intrinsics)
        self.ui.btn_cap_extrinsics_start.clicked.connect(self.toggle_extrinsics)
        self.ui.btn_cap_reset_calibration.clicked.connect(self.reset_calibration_buttons)

        # --- NIEUW: Koppel de Calculate knoppen ---
        self.ui.btn_cap_calculate_intrinsics.clicked.connect(self.calculate_intrinsics)
        self.ui.btn_cap_calculate_extrinsics.clicked.connect(self.calculate_extrinsics)
        
        self.setup_add_button()

    def setup_add_button(self):
        self.add_frame = QtWidgets.QFrame()
        layout = QtWidgets.QVBoxLayout(self.add_frame)
        self.btn_plus = QtWidgets.QPushButton("+ Camera Toevoegen")
        self.btn_plus.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.btn_plus.clicked.connect(self.add_new_camera)
        layout.addWidget(self.btn_plus)
        self.update_grid()

    def add_new_camera(self):
        available_cameras = QCameraInfo.availableCameras()
        camera_to_use_idx = -1
        for i, cam in enumerate(available_cameras):
            if not self.is_camera_in_use(cam.description(), None):
                camera_to_use_idx = i
                break
        
        if camera_to_use_idx == -1:
            QtWidgets.QMessageBox.information(self.ui, "Geen Camera's Beschikbaar", 
                "Alle aangesloten camera's zijn al in gebruik.")
            return

        new_cam = CameraFrame(self.remove_camera)
        new_cam.parent_tab = self
        self.camera_frames.append(new_cam)
        
        new_cam.combo_select_cam.setCurrentIndex(camera_to_use_idx + 1)
        
        # Start de nieuwe camera direct op zonder ergens op te wachten
        new_cam.manage_thread()
            
        self.update_grid()

    def is_camera_in_use(self, camera_name, calling_frame):
        if camera_name == "Geen Camera": return False
        for frame in self.camera_frames:
            if frame != calling_frame and frame.combo_select_cam.currentText() == camera_name:
                return True
        return False

    def remove_camera(self, frame_to_remove):
        if frame_to_remove in self.camera_frames:
            if frame_to_remove.thread:
                frame_to_remove.thread.stop()
            self.camera_frames.remove(frame_to_remove)
            frame_to_remove.setParent(None)
            frame_to_remove.deleteLater()
            self.update_grid()

    def update_grid(self):
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            if item.widget(): item.widget().setParent(None)
        for i, frame in enumerate(self.camera_frames):
            self.grid_layout.addWidget(frame, i // 3, i % 3)
        self.grid_layout.addWidget(self.add_frame, len(self.camera_frames) // 3, len(self.camera_frames) % 3)

    def toggle_intrinsics(self):
        """Beheert de status en het uiterlijk van de Intrinsics Start/Stop knop."""
        if self.ui.btn_cap_intrinsics_start.isChecked():
            # Knop is ingedrukt (Actief) -> Blauw maken en tekst veranderen naar Stop
            self.ui.btn_cap_intrinsics_start.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
            self.ui.btn_cap_intrinsics_start.setText("Stop")
            # TIP: Voeg hier eventueel je code toe om de intrinsieke kalibratie te STARTEN
        else:
            # Knop is weer uitgeschakeld -> Terug naar standaard
            self.ui.btn_cap_intrinsics_start.setStyleSheet("")
            self.ui.btn_cap_intrinsics_start.setText("Start")
            # TIP: Voeg hier eventueel je code toe om de intrinsieke kalibratie te STOPPEN

    def toggle_extrinsics(self):
        """Beheert de status en het uiterlijk van de Extrinsics Start/Stop knop."""
        if self.ui.btn_cap_extrinsics_start.isChecked():
            # Knop is ingedrukt (Actief) -> Blauw maken en tekst veranderen naar Stop
            self.ui.btn_cap_extrinsics_start.setStyleSheet("background-color: #0078d7; color: white; font-weight: bold;")
            self.ui.btn_cap_extrinsics_start.setText("Stop")
            # TIP: Voeg hier eventueel je code toe om de extrinsieke kalibratie te STARTEN
        else:
            # Knop is weer uitgeschakeld -> Terug naar standaard
            self.ui.btn_cap_extrinsics_start.setStyleSheet("")
            self.ui.btn_cap_extrinsics_start.setText("Start")
            # TIP: Voeg hier eventueel je code toe om de extrinsieke kalibratie te STOPPEN

    def reset_calibration_buttons(self):
        """Zet beide kalibratieknoppen terug in hun originele (niet-ingedrukte) staat."""
        # Zet de check-status terug naar False
        self.ui.btn_cap_intrinsics_start.setChecked(False)
        self.ui.btn_cap_extrinsics_start.setChecked(False)
        
        # Herstel de stylesheet naar standaard (leeg)
        self.ui.btn_cap_intrinsics_start.setStyleSheet("")
        self.ui.btn_cap_extrinsics_start.setStyleSheet("")
        
        # Herstel de tekst naar 'Start'
        self.ui.btn_cap_intrinsics_start.setText("Start")
        self.ui.btn_cap_extrinsics_start.setText("Start")

        for frame in self.camera_frames:
            frame.reset_intrinsic_captures()

    def log_to_console(self, text):
        """Hulpfunctie om tekst met een tijdstempel naar de console te sturen."""
        import datetime
        timestamp = datetime.datetime.now().strftime("[%H:%M:%S]")
        self.ui.plaintextedit_console.appendPlainText(f"{timestamp} {text}")

    def calculate_intrinsics(self):
        """Wordt uitgevoerd als je op Calculate bij Intrinsics drukt."""
        # Log het startbericht naar de console
        self.log_to_console("Systeem: Starten van berekening intrinsieke kalibratie...")
        
        # --- HIER KOMT DE ECHTE BEREKENING (OpenCV code) ---
        # Bijvoorbeeld:
        # success = self.logic.perform_intrinsics_math()
        
        # Voor nu simuleren we dat het gelukt is:
        self.log_to_console("Systeem: Intrinsieke kalibratie succesvol afgerond!")

    def calculate_extrinsics(self):
        """Wordt uitgevoerd als je op Calculate bij Extrinsics drukt."""
        # Log het startbericht naar de console
        self.log_to_console("Systeem: Starten van berekening extrinsieke kalibratie...")
        
        # --- HIER KOMT DE ECHTE BEREKENING (OpenCV code) ---
        
        # Voor nu simuleren we dat het gelukt is:
        self.log_to_console("Systeem: Extrinsieke kalibratie succesvol afgerond!")

    def capture_intrinsics_for_camera(self, cam_idx):
        """
        Voegt een intrinsics capture toe aan een specifieke camera op basis van de index 
        in de lijst van actieve cameraframes.
        """
        # Filter eerst de frames die daadwerkelijk een gekoppelde camera hebben (niet op 'Geen Camera' staan)
        active_frames = [f for f in self.camera_frames if f.combo_select_cam.currentData() != -1]
        
        if not active_frames:
            self.log_to_console("Systeem: Er zijn momenteel geen actieve camera's geopend.")
            return

        # Controleer of het opgevraagde nummer binnen het bereik van actieve camera's valt
        if 0 <= cam_idx < len(active_frames):
            target_frame = active_frames[cam_idx]
            target_frame.add_intrinsic_capture()
            
            # Haal de naam van de camera op voor een duidelijke log
            cam_name = target_frame.combo_select_cam.currentText()
            self.log_to_console(f"Systeem: Intrinsics capture toegevoegd aan camera {cam_idx} ({cam_name})!")
        else:
            self.log_to_console(f"Fout: Camera index {cam_idx} bestaat niet. Actieve indexen zijn 0 tot {len(active_frames)-1}.")