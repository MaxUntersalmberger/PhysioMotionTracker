from PyQt5 import QtCore, QtGui, QtWidgets

class CameraFrame(QtWidgets.QFrame):
    """Een camera-frame met een verwijder-knop linksboven (4:3 verhouding)."""
    def __init__(self, on_delete_callback):
        super().__init__()
        self.on_delete_callback = on_delete_callback
        
        # Basis styling
        self.setFrameShape(QtWidgets.QFrame.Box)
        self.setMinimumSize(200, 150)
        
        # Layout voor de knop
        self.layout = QtWidgets.QGridLayout(self)
        self.layout.setContentsMargins(5, 5, 5, 5)

        # 1. Verwijder knop (X) linksboven
        self.btn_delete = QtWidgets.QPushButton("X", self) # 'self' toevoegen als parent helpt bij events
        self.btn_delete.setFixedSize(30, 30)
        self.btn_delete.clicked.connect(lambda: self.on_delete_callback(self))
        
        # Zorg dat de knop altijd bovenop ligt
        self.btn_delete.raise_()
        self.layout.addWidget(self.btn_delete, 0, 0, QtCore.Qt.AlignTop | QtCore.Qt.AlignRight)

    def resizeEvent(self, event):
        # 4:3 Verhouding (Breedte / 4 * 3)
        new_height = int((self.width() / 4) * 3)
        self.setFixedHeight(new_height)
        super().resizeEvent(event)

class TabCameras:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.ui = logic_instance.window
        self.camera_frames = []

    def setup(self):
        """Initialiseert de Cameras tab binnen gridLayout_6 van frame_cam."""
        self.main_layout = self.ui.gridLayout_6
        
        self.scroll_area = QtWidgets.QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QtWidgets.QFrame.NoFrame)
        
        self.scroll_content = QtWidgets.QWidget()
        self.grid_layout = QtWidgets.QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        
        # Grid kolom stretch instellen voor 3 kolommen
        for i in range(3):
            self.grid_layout.setColumnStretch(i, 1)
        
        self.scroll_area.setWidget(self.scroll_content)
        self.main_layout.addWidget(self.scroll_area)

        self.setup_add_button()

    def setup_add_button(self):
        """Maakt de grote '+' box aan het einde van het grid."""
        self.add_frame = QtWidgets.QFrame()
        
        layout = QtWidgets.QVBoxLayout(self.add_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn_plus = QtWidgets.QPushButton("+ Camera Toevoegen")
        self.btn_plus.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.btn_plus.clicked.connect(self.add_new_camera)
        
        layout.addWidget(self.btn_plus)
        self.update_grid()

    def add_new_camera(self):
        """Voegt een nieuw frame toe zonder tekst."""
        # CORRECTIE: CameraFrame verwacht nu alleen de callback
        new_cam = CameraFrame(self.remove_camera)
        self.camera_frames.append(new_cam)
        self.update_grid()

    def remove_camera(self, frame_to_remove):
        """Verwijdert het geselecteerde frame."""
        if frame_to_remove in self.camera_frames:
            self.camera_frames.remove(frame_to_remove)
            frame_to_remove.setParent(None)
            frame_to_remove.deleteLater()
            self.update_grid()

    def update_grid(self):
        """Ververst de posities van alle frames en de toevoeg-knop."""
        # Haal alles veilig uit de layout
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

        # Voeg camera frames toe
        for index, frame in enumerate(self.camera_frames):
            row, col = divmod(index, 3)
            self.grid_layout.addWidget(frame, row, col)

        # Plaats de 'Toevoegen' knop op de volgende positie
        row, col = divmod(len(self.camera_frames), 3)
        self.grid_layout.addWidget(self.add_frame, row, col)
        
        # Hoogte synchronisatie
        if self.camera_frames:
            self.add_frame.setFixedHeight(self.camera_frames[0].height())
        else:
            self.add_frame.setFixedHeight(150)