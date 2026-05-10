from PyQt5 import QtCore, QtGui, QtWidgets

class AspectRatioFrame(QtWidgets.QFrame):
    """Een QFrame dat altijd een 3:4 (breedte:hoogte) verhouding aanhoudt."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setStyleSheet("background-color: #f0f0f0; border: 1px solid #333; border-radius: 5px;")
        
    def resizeEvent(self, event):
        # Bereken de nieuwe hoogte op basis van de breedte (verhouding 4:3)
        # Formule: Hoogte = (Breedte / 4) * 3
        new_width = self.width()
        new_height = int((new_width / 4) * 3)
        
        # Forceer de hoogte
        self.setFixedHeight(new_height)
        super().resizeEvent(event)

class TabCameras:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.ui = logic_instance.window
        self.camera_frames = []

    def setup(self):
        """Initialiseert de Cameras tab"""
        self.main_layout = self.ui.gridLayout_6
        
        # 1. Knoppen
        self.button_layout = QtWidgets.QHBoxLayout()
        self.btn_add_cam = QtWidgets.QPushButton("Camera Toevoegen")
        self.btn_add_cam.clicked.connect(self.add_camera_frame)
        self.btn_remove_cam = QtWidgets.QPushButton("Laatste Verwijderen")
        self.btn_remove_cam.clicked.connect(self.remove_last_camera_frame)
        
        self.button_layout.addWidget(self.btn_add_cam)
        self.button_layout.addWidget(self.btn_remove_cam)
        self.button_layout.addStretch()
        self.main_layout.addLayout(self.button_layout, 0, 0)

        # 2. Scroll Area
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        
        self.scroll_content = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop)
        
        # Zorg dat kolommen gelijkmatig verdelen
        for i in range(3):
            self.grid_layout.setColumnStretch(i, 1)
        
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area, 1, 0)

    def add_camera_frame(self):
        """Voegt een frame toe met de AspectRatioFrame klasse"""
        # Gebruik de nieuwe klasse in plaats van QFrame
        new_frame = AspectRatioFrame()
        
        # Grid positie
        index = len(self.camera_frames)
        row = index // 3
        col = index % 3
        
        self.grid_layout.addWidget(new_frame, row, col)
        self.camera_frames.append(new_frame)

    def remove_last_camera_frame(self):
        if self.camera_frames:
            frame_to_remove = self.camera_frames.pop()
            self.grid_layout.removeWidget(frame_to_remove)
            frame_to_remove.setParent(None)
            frame_to_remove.deleteLater()