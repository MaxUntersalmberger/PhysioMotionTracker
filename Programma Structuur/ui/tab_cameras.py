import cv2
import time
from PyQt5 import QtCore, QtGui, QtWidgets

class CameraThread(QtCore.QThread):
    """Thread die beelden ophaalt en instellingen live toepast."""
    change_pixmap_signal = QtCore.pyqtSignal(QtGui.QImage)

    def __init__(self, camera_index=0, fps=30, width=640, height=480):
        super().__init__()
        self.camera_index = camera_index
        self.fps = fps
        self.width = width
        self.height = height
        self._run_flag = True

    def run(self):
        # Gebruik CAP_DSHOW op Windows voor snellere initialisatie
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
        
        # Initialiseer resolutie
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        while self._run_flag:
            start_time = time.time()
            
            # Update resolutie als deze tussentijds is veranderd
            if cap.get(cv2.CAP_PROP_FRAME_WIDTH) != self.width:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

            ret, frame = cap.read()
            if ret:
                # Conversie naar Qt formaat
                rgb_image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = rgb_image.shape
                bytes_per_line = ch * w
                qt_img = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                
                # .copy() is cruciaal om geheugencrashes te voorkomen
                self.change_pixmap_signal.emit(qt_img.copy())

            # FPS timing: wacht precies lang genoeg
            sleep_time = max(1/self.fps - (time.time() - start_time), 0.001)
            time.sleep(sleep_time)

        cap.release()

    def update_params(self, fps, res_str):
        """Update de parameters die in de loop worden gebruikt."""
        self.fps = fps
        w, h = map(int, res_str.split('x'))
        self.width, self.height = w, h

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
        
        # Layout
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)

        # --- Controls (Bovenbalk) ---
        self.controls_layout = QtWidgets.QHBoxLayout()
        
        self.combo_select_cam = QtWidgets.QComboBox()
        self.combo_select_cam.addItems(["Geen Camera", "0", "1", "2"])
        self.combo_select_cam.currentIndexChanged.connect(self.manage_thread)
        
        self.btn_settings = QtWidgets.QPushButton("⋮")
        self.btn_settings.setFixedSize(30, 30)
        self.btn_settings.setCheckable(True)
        self.btn_settings.clicked.connect(self.toggle_view)

        self.btn_delete = QtWidgets.QPushButton("X")
        self.btn_delete.setFixedSize(30, 30)
        self.btn_delete.setStyleSheet("background-color: #ff4d4d; color: white;")
        self.btn_delete.clicked.connect(self.full_cleanup)

        self.controls_layout.addWidget(self.combo_select_cam, 1)
        self.controls_layout.addWidget(self.btn_settings)
        self.controls_layout.addWidget(self.btn_delete)
        self.main_layout.addLayout(self.controls_layout)

        # --- Inhoud (Stack) ---
        self.stacked = QtWidgets.QStackedWidget()
        
        # Pagina 0: Live View
        self.video_label = QtWidgets.QLabel("Selecteer een camera")
        self.video_label.setAlignment(QtCore.Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: black; color: white;")
        
        # Pagina 1: Settings
        self.settings_frame = QtWidgets.QFrame()
        self.settings_layout = QtWidgets.QFormLayout(self.settings_frame)
        
        self.spin_fps = QtWidgets.QSpinBox()
        self.spin_fps.setRange(1, 60)
        self.spin_fps.setValue(30)
        self.spin_fps.valueChanged.connect(self.apply_settings)
        
        self.combo_res = QtWidgets.QComboBox()
        self.combo_res.addItems(["640x480", "1280x720", "1920x1080"])
        self.combo_res.currentIndexChanged.connect(self.apply_settings)
        
        self.settings_layout.addRow("Preview FPS:", self.spin_fps)
        self.settings_layout.addRow("Resolutie:", self.combo_res)
        
        self.stacked.addWidget(self.video_label)
        self.stacked.addWidget(self.settings_frame)
        self.main_layout.addWidget(self.stacked)

    def manage_thread(self, index):
        """Start of stopt de camera thread."""
        if self.thread:
            self.thread.stop()
            self.thread = None

        if index > 0:
            cam_idx = int(self.combo_select_cam.currentText())
            self.thread = CameraThread(
                camera_index=cam_idx, 
                fps=self.spin_fps.value(),
                width=int(self.combo_res.currentText().split('x')[0]),
                height=int(self.combo_res.currentText().split('x')[1])
            )
            self.thread.change_pixmap_signal.connect(self.update_frame)
            self.thread.start()
        else:
            self.video_label.clear()
            self.video_label.setText("Selecteer een camera")

    def apply_settings(self):
        """Geef instellingen direct door aan de thread."""
        if self.thread:
            self.thread.update_params(self.spin_fps.value(), self.combo_res.currentText())

    def update_frame(self, img):
        """Toon het beeld op de QLabel (behalve als we in settings zitten)."""
        if not self.btn_settings.isChecked():
            pixmap = QtGui.QPixmap.fromImage(img)
            self.video_label.setPixmap(pixmap.scaled(
                self.video_label.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation
            ))

    def toggle_view(self):
        self.stacked.setCurrentIndex(1 if self.btn_settings.isChecked() else 0)

    def full_cleanup(self):
        if self.thread:
            self.thread.stop()
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
        new_cam = CameraFrame(self.remove_camera)
        self.camera_frames.append(new_cam)
        self.update_grid()

    def remove_camera(self, frame_to_remove):
        if frame_to_remove in self.camera_frames:
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