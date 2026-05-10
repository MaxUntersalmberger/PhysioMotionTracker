from PyQt5 import QtCore, QtGui, QtWidgets

class CameraFrame(QtWidgets.QFrame):
    """Een camera-frame met dropdowns, instellingen en een stacked view (Live/Settings)."""
    def __init__(self, on_delete_callback):
        super().__init__()
        self.on_delete_callback = on_delete_callback
        
        # Basis styling
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setMinimumSize(250, 200)
        
        # Hoofdlayout (Verticaal)
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(2)

        # --- 1. Bovenste Balk (Controls) ---
        self.controls_layout = QtWidgets.QHBoxLayout()
        
        # Dropdown voor camera selectie
        self.combo_select_cam = QtWidgets.QComboBox()
        self.combo_select_cam.addItems(["Selecteer Camera...", "Camera 1", "Camera 2", "Camera 3"])
        self.controls_layout.addWidget(self.combo_select_cam, 1) # Stretch factor 1

        # Drie puntjes menu (Settings toggle)
        self.btn_settings = QtWidgets.QPushButton("⋮")
        self.btn_settings.setFixedSize(30, 30)
        self.btn_settings.setCheckable(True)
        self.btn_settings.clicked.connect(self.toggle_view)
        self.controls_layout.addWidget(self.btn_settings)

        # Verwijder knop (X)
        self.btn_delete = QtWidgets.QPushButton("X")
        self.btn_delete.setFixedSize(30, 30)
        self.btn_delete.setStyleSheet("background-color: #ff4d4d; color: white; font-weight: bold;")
        self.btn_delete.clicked.connect(lambda: self.on_delete_callback(self))
        self.controls_layout.addWidget(self.btn_delete)

        self.main_layout.addLayout(self.controls_layout)

        # --- 2. Stacked Widget (Inhoud) ---
        self.stacked_view = QtWidgets.QStackedWidget()
        
        # Pagina 1: Live View Frame
        self.live_view_frame = QtWidgets.QFrame()
        self.live_view_frame.setStyleSheet("background-color: black;") # Placeholder voor video
        self.live_label = QtWidgets.QLabel("LIVE VIEW", self.live_view_frame)
        self.live_label.setAlignment(QtCore.Qt.AlignCenter)
        self.live_label.setStyleSheet("color: white;")
        layout_live = QtWidgets.QVBoxLayout(self.live_view_frame)
        layout_live.addWidget(self.live_label)
        
        # Pagina 2: Settings Frame
        self.settings_frame = QtWidgets.QFrame()
        self.settings_layout = QtWidgets.QFormLayout(self.settings_frame)
        
        self.spin_fps = QtWidgets.QSpinBox()
        self.spin_fps.setRange(1, 120)
        self.spin_fps.setValue(30)
        
        self.combo_res = QtWidgets.QComboBox()
        self.combo_res.addItems(["1920x1080", "1280x720", "640x480"])
        
        self.settings_layout.addRow("FPS:", self.spin_fps)
        self.settings_layout.addRow("Resolutie:", self.combo_res)
        
        # Toevoegen aan stack
        self.stacked_view.addWidget(self.live_view_frame) # Index 0
        self.stacked_view.addWidget(self.settings_frame)  # Index 1
        
        self.main_layout.addWidget(self.stacked_view)

    def toggle_view(self):
        """Wisselt tussen Live View en Settings."""
        if self.btn_settings.isChecked():
            self.stacked_view.setCurrentIndex(1)
        else:
            self.stacked_view.setCurrentIndex(0)

    def resizeEvent(self, event):
        # 4:3 Verhouding forceren
        new_height = int((self.width() / 4) * 3)
        self.setFixedHeight(new_height)
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
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        
        self.scroll_content = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        
        for i in range(3):
            self.grid_layout.setColumnStretch(i, 1)
        
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
            widget = item.widget()
            if widget:
                widget.setParent(None)

        for index, frame in enumerate(self.camera_frames):
            row, col = divmod(index, 3)
            self.grid_layout.addWidget(frame, row, col)

        row, col = divmod(len(self.camera_frames), 3)
        self.grid_layout.addWidget(self.add_frame, row, col)
        
        if self.camera_frames:
            self.add_frame.setFixedHeight(self.camera_frames[0].sizeHint().height())
        else:
            self.add_frame.setFixedHeight(200)