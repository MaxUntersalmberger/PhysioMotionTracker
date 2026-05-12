import cv2
import time
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtMultimedia import QCameraInfo

class CameraThread(QtCore.QThread):
    change_pixmap_signal = QtCore.pyqtSignal(QtGui.QImage)

    def __init__(self, camera_index=0, width=640, height=480):
        super().__init__()
        self.camera_index = camera_index
        self.fps = 30 # We zetten FPS vast op een stabiele waarde
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

            # Update hardware ALLEEN als het echt veranderd is
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

            # Gebruik FastTransformation voor betere performance tijdens UI scaling
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
        
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setMinimumSize(250, 200)
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        # --- Controls ---
        self.controls_layout = QtWidgets.QHBoxLayout()
        self.combo_select_cam = QtWidgets.QComboBox()
        self.refresh_camera_list() 
        self.combo_select_cam.currentIndexChanged.connect(self.manage_thread)
        
        self.btn_settings = QtWidgets.QPushButton("⋮")
        self.btn_settings.setFixedSize(30, 30)
        self.btn_settings.setCheckable(True)
        self.btn_settings.clicked.connect(self.toggle_view)

        self.btn_delete = QtWidgets.QPushButton("X")
        self.btn_delete.setFixedSize(30, 30)
        self.btn_delete.clicked.connect(self.full_cleanup)

        self.controls_layout.addWidget(self.combo_select_cam, 1)
        self.controls_layout.addWidget(self.btn_settings)
        self.controls_layout.addWidget(self.btn_delete)
        self.main_layout.addLayout(self.controls_layout)

        # --- Inhoud (Stack) ---
        self.stacked = QtWidgets.QStackedWidget()
        
        self.video_label = QtWidgets.QLabel("Selecteer een camera")
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black;")
        
        # Settings Pagina
        self.settings_frame = QtWidgets.QFrame()
        self.settings_layout = QtWidgets.QFormLayout(self.settings_frame)
        
        # Resolutie velden (FPS verwijderd)
        self.spin_width = QtWidgets.QSpinBox()
        self.spin_width.setRange(160, 3840); self.spin_width.setValue(640)
        self.spin_height = QtWidgets.QSpinBox()
        self.spin_height.setRange(120, 2160); self.spin_height.setValue(480)

        self.combo_rotate = QtWidgets.QComboBox()
        self.combo_rotate.addItems(["0", "90", "180", "270"])
        self.check_mirror = QtWidgets.QCheckBox("Mirror Image")

        self.spin_exposure = QtWidgets.QSpinBox()
        self.spin_exposure.setRange(-13, 0); self.spin_exposure.setValue(-5)

        # DE APPLY KNOP
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

    def refresh_camera_list(self):
        self.combo_select_cam.blockSignals(True)
        self.combo_select_cam.clear()
        # "Geen Camera" krijgt index -1 als marker
        self.combo_select_cam.addItem("Geen Camera", -1)
        cameras = QCameraInfo.availableCameras()
        for i, cam in enumerate(cameras):
            self.combo_select_cam.addItem(cam.description(), i)
        self.combo_select_cam.blockSignals(False)

    def manage_thread(self, index):
        opencv_idx = self.combo_select_cam.currentData()

        # Check op dubbele camera (alleen als het handmatig gewisseld wordt naar een bezette camera)
        if opencv_idx is not None and opencv_idx != -1:
            cam_name = self.combo_select_cam.currentText()
            if self.parent_tab and self.parent_tab.is_camera_in_use(cam_name, self):
                QtWidgets.QMessageBox.warning(self, "Camera Bezet", f"'{cam_name}' is al in gebruik.")
                self.combo_select_cam.blockSignals(True)
                self.combo_select_cam.setCurrentIndex(0) 
                self.combo_select_cam.blockSignals(False)
                opencv_idx = -1 

        if self.thread:
            self.thread.stop()
            self.thread = None

        if opencv_idx is not None and opencv_idx != -1:
            # Maak de thread aan met de geselecteerde index
            self.thread = CameraThread(camera_index=opencv_idx, width=self.spin_width.value(), height=self.spin_height.value())
            self.apply_settings()
            self.thread.change_pixmap_signal.connect(self.update_frame)
            self.thread.start()
        else:
            self.video_label.clear()
            self.video_label.setPixmap(QtGui.QPixmap())
            self.video_label.setText("Selecteer een camera")

    def apply_settings(self):
        """Wordt nu alleen aangeroepen via de Apply knop of bij start."""
        if self.thread and self.thread.isRunning():
            self.thread.update_params(
                width=self.spin_width.value(),
                height=self.spin_height.value(),
                rotate=int(self.combo_rotate.currentText()),
                mirror=self.check_mirror.isChecked(),
                exposure=self.spin_exposure.value()
            )

    def update_frame(self, img):
        if not self.btn_settings.isChecked():
            pixmap = QtGui.QPixmap.fromImage(img)
            # Gebruik FastTransformation om CPU-lag in de UI te voorkomen
            self.video_label.setPixmap(pixmap.scaled(
                self.video_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation
            ))

    def toggle_view(self):
        self.stacked.setCurrentIndex(1 if self.btn_settings.isChecked() else 0)

    def full_cleanup(self):
        if self.thread: self.thread.stop()
        self.on_delete_callback(self)

    def resizeEvent(self, event):
        self.setFixedHeight(int(self.width() * 0.75))
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
        # 1. Haal alle aangesloten camera's op
        available_cameras = QCameraInfo.availableCameras()
        
        # 2. Zoek naar de eerste camera die nog NIET in gebruik is
        camera_to_use_idx = -1
        for i, cam in enumerate(available_cameras):
            if not self.is_camera_in_use(cam.description(), None):
                camera_to_use_idx = i
                break
        
        # 3. Als er geen camera meer vrij is, geef een melding
        if camera_to_use_idx == -1:
            QtWidgets.QMessageBox.information(self.ui, "Geen Camera's Beschikbaar", 
                "Alle aangesloten camera's zijn al in gebruik.")
            return

        # 4. Voeg het frame toe en selecteer direct de gevonden camera
        new_cam = CameraFrame(self.remove_camera)
        new_cam.parent_tab = self
        self.camera_frames.append(new_cam)
        
        # Selecteer de camera in de combobox (index + 1 omdat 0 'Geen Camera' is)
        new_cam.combo_select_cam.setCurrentIndex(camera_to_use_idx + 1)
        
        self.update_grid()

    def is_camera_in_use(self, camera_name, calling_frame):
        # "Geen Camera" is nooit "in gebruik", dus die checken we niet
        if camera_name == "Geen Camera":
            return False
        for frame in self.camera_frames:
            if frame != calling_frame and frame.combo_select_cam.currentText() == camera_name:
                return True
        return False

    def remove_camera(self, frame_to_remove):
        if frame_to_remove in self.camera_frames:
            # Zorg dat de thread eerst stopt
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