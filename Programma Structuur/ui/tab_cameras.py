import cv2
from PyQt5 import QtCore, QtGui, QtWidgets

def get_available_cameras():
    """Scant beschikbare camera's via DSHOW over een groter bereik[cite: 10]."""
    available_indices = []
    for i in range(10):  
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            available_indices.append(f"Camera {i}")
            cap.release()
    return available_indices

class CameraWidget(QtWidgets.QFrame):
    def __init__(self, logic_instance, widget_width=None):
        super().__init__()
        self.logic = logic_instance
        self.cap = None
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)

        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.setStyleSheet("QFrame { background-color: #1e1e1e; border: 1px solid #333; border-radius: 8px; }")
        
        self.main_layout = QtWidgets.QVBoxLayout(self)
        
        # UI Elementen
        self.combo_cam_selector = QtWidgets.QComboBox()
        self.combo_cam_selector.setStyleSheet("background-color: #333; color: white; padding: 5px;")
        
        self.btn_cam_del = QtWidgets.QPushButton("✕")
        self.btn_cam_del.setFixedSize(30, 30)
        self.btn_cam_del.clicked.connect(self.remove_self)
        
        top_layout = QtWidgets.QHBoxLayout()
        top_layout.addWidget(self.combo_cam_selector)
        top_layout.addWidget(self.btn_cam_del)
        
        self.label_cam_view = QtWidgets.QLabel("Initialiseren...")
        self.label_cam_view.setAlignment(QtCore.Qt.AlignCenter)
        self.label_cam_view.setMinimumSize(240, 180)
        self.label_cam_view.setStyleSheet("background-color: black; color: #555;")
        
        self.main_layout.addLayout(top_layout)
        self.main_layout.addWidget(self.label_cam_view)

        # Koppel de centrale GUI instellingen aan deze camera[cite: 10]
        self.logic.window.spin_pre_fps.valueChanged.connect(self.apply_camera_settings)
        self.logic.window.combo_res_fps.currentIndexChanged.connect(self.apply_camera_settings)

        cameras = get_available_cameras()
        self.combo_cam_selector.addItems(cameras)
        self.combo_cam_selector.currentIndexChanged.connect(self.start_camera)

    def apply_camera_settings(self):
        """Past de resolutie en FPS van de camera aan op basis van de GUI[cite: 10]."""
        if self.cap and self.cap.isOpened():
            # 1. FPS instellen
            fps = self.logic.window.spin_pre_fps.value()
            if fps > 0:
                self.cap.set(cv2.CAP_PROP_FPS, fps)
                self.timer.setInterval(int(1000 / fps)) # Update timer interval

            # 2. Resolutie instellen
            res_text = self.logic.window.combo_res_fps.currentText()
            if "x" in res_text:
                width, height = map(int, res_text.split("x"))
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    def start_camera(self):
        """Initialiseert de camera en past direct de gekozen instellingen toe[cite: 10]."""
        if self.cap is not None:
            self.timer.stop()
            self.cap.release()

        selection = self.combo_cam_selector.currentText()
        if "Camera" in selection:
            try:
                index = int(selection.split(" ")[1])
                self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if self.cap.isOpened():
                    self.apply_camera_settings() # Direct settings toepassen bij start
                    self.timer.start() 
                else:
                    self.label_cam_view.setText("Fout: Camera bezet")
            except Exception as e:
                print(f"Fout bij starten camera: {e}")

    def update_frame(self):
        """Haalt frames op en toont ze in de GUI[cite: 10]."""
        if self.cap and self.cap.isOpened():
            if self.label_cam_view.width() <= 1:
                return

            ret, frame = self.cap.read()
            if ret and frame is not None:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                q_img = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                
                pixmap = QtGui.QPixmap.fromImage(q_img)
                scaled_pixmap = pixmap.scaled(
                    self.label_cam_view.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )
                self.label_cam_view.setPixmap(scaled_pixmap)

    def remove_self(self):
        """Sluit de camera en schoont de layout op[cite: 10]."""
        self.timer.stop()
        if self.cap:
            self.cap.release()
        self.setParent(None)
        self.deleteLater()
        self.logic.tab_cameras.reorganize_layout()

class TabCameras:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.window = logic_instance.window
        self.cam_layout = None
        self.btn_add_cam = None
        self.MAX_CAMERAS = 10 

    def setup(self):
        """Initialiseert de camera tab instellingen[cite: 10]."""
        self.window.spin_cap_fps.setRange(0, 120)
        self.window.spin_cap_fps.setValue(30)
        self.window.spin_pre_fps.setRange(1, 120) # Minimaal 1 FPS
        self.window.spin_pre_fps.setValue(30)

        resolutions = ["1920x1080", "1280x720", "640x480", "320x240"]
        self.window.combo_cap_res.clear()
        self.window.combo_cap_res.addItems(resolutions)
        self.window.combo_res_fps.clear()
        self.window.combo_res_fps.addItems(resolutions)

        self.cam_layout = self.window.gridLayout_6 
        self.btn_add_cam = QtWidgets.QPushButton("+ Voeg Camera Toe")
        self.btn_add_cam.setMinimumSize(150, 100)
        self.btn_add_cam.clicked.connect(self.add_camera_card)
        
        self.cam_layout.addWidget(self.btn_add_cam, 0, 0)

    def add_camera_card(self):
        """Voegt een nieuwe camera kaart toe[cite: 10]."""
        current_cam_count = sum(1 for i in range(self.cam_layout.count()) 
                               if isinstance(self.cam_layout.itemAt(i).widget(), CameraWidget))

        if current_cam_count < self.MAX_CAMERAS:
            new_cam = CameraWidget(self.logic)
            self.reorganize_layout(new_widget=new_cam)
            QtWidgets.QApplication.processEvents() 
            new_cam.start_camera()
            
            if current_cam_count + 1 >= self.MAX_CAMERAS:
                self.btn_add_cam.setEnabled(False)
                self.btn_add_cam.setText("Maximum (10) bereikt")

    def reorganize_layout(self, new_widget=None):
        """Deelt de grid opnieuw in[cite: 10]."""
        widgets = []
        for i in range(self.cam_layout.count()):
            item = self.cam_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), CameraWidget):
                widgets.append(item.widget())

        if new_widget:
            widgets.append(new_widget)

        for w in widgets:
            self.cam_layout.removeWidget(w)
        self.cam_layout.removeWidget(self.btn_add_cam)

        max_cols = 3
        for i, w in enumerate(widgets):
            row, col = i // max_cols, i % max_cols
            self.cam_layout.addWidget(w, row, col)

        last_idx = len(widgets)
        self.cam_layout.addWidget(self.btn_add_cam, last_idx // max_cols, last_idx % max_cols)