import cv2
from PyQt5 import QtCore, QtGui, QtWidgets


def get_available_cameras():
    """Scant beschikbare camera's met een fallback naar MSMF"""
    available_indices = []
    # Probeer eerst DSHOW (vaak sneller voor simpele webcams)
    for i in range(4):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            available_indices.append(f"Camera {i}")
            cap.release()
            continue # Volgende index

        # Fallback naar MSMF als DSHOW niet werkt
        cap = cv2.VideoCapture(i, cv2.CAP_MSMF)
        if cap.isOpened():
            available_indices.append(f"Camera {i}")
            cap.release()

    return available_indices


class AspectButton(QtWidgets.QPushButton):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Ook hier 0.75 voor de 4:3 verhouding
        self.setFixedHeight(int(self.width() * 0.75))


class CameraWidget(QtWidgets.QFrame):
    def __init__(self, logic_instance):
        super().__init__()
        self.logic = logic_instance
        self.cap = None  # Hier bewaren we de OpenCV verbinding

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_frame)

        # --- Bestaande UI setup ---
        self.setMinimumWidth(200)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.setStyleSheet("QFrame { background-color: #1e1e1e; border: 1px solid #333; border-radius: 8px; }")

        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.top_bar_layout = QtWidgets.QHBoxLayout()

        self.combo_cam_selector = QtWidgets.QComboBox(self)
        self.combo_cam_selector.setStyleSheet("background-color: #333; color: white; padding: 5px;")

        cameras = get_available_cameras()
        if cameras:
            self.combo_cam_selector.addItems(cameras)
            # Start direct de eerste camera in de lijst
            self.start_camera()
        else:
            self.combo_cam_selector.addItem("Geen camera gevonden")
            self.combo_cam_selector.setEnabled(False) # Blokkeer als er niets is

        self.combo_cam_selector.currentIndexChanged.connect(self.start_camera)

        self.btn_cam_del = QtWidgets.QPushButton("✕", self)
        self.btn_cam_del.setFixedSize(30, 30)
        self.btn_cam_del.clicked.connect(self.remove_self)

        self.top_bar_layout.addWidget(self.combo_cam_selector)
        self.top_bar_layout.addWidget(self.btn_cam_del)

        self.label_cam_view = QtWidgets.QLabel("Camera Feed", self)
        self.label_cam_view.setAlignment(QtCore.Qt.AlignCenter)
        self.label_cam_view.setScaledContents(False)
        self.label_cam_view.setStyleSheet("background-color: black; border-radius: 4px; color: #555;")

        self.main_layout.addLayout(self.top_bar_layout)
        self.main_layout.addWidget(self.label_cam_view)

    def start_camera(self):
        """Stopt oude stream en start de nieuwe op basis van de geselecteerde index"""
        if self.cap is not None:
            self.timer.stop()
            self.cap.release()
            self.cap = None

        selection = self.combo_cam_selector.currentText()

        # We splitsen alleen als het woord 'Camera' erin staat (veiligheid voor 'Geen camera gevonden')
        if "Camera" in selection:
            try:
                index = int(selection.split(" ")[1])
                self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                if self.cap.isOpened():
                    self.timer.start(30)
                else:
                    self.label_cam_view.setText("Fout: Camera bezet")
            except (IndexError, ValueError):
                pass

    def update_frame(self):
        """Haalt frame op, converteert het en zet het op het label zonder stretching"""
        if self.cap and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                # 1. Conversie naar RGB
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # 2. Maak de QImage
                height, width, channel = frame.shape
                bytes_per_line = channel * width
                q_img = QtGui.QImage(frame.data, width, height, bytes_per_line, QtGui.QImage.Format_RGB888)

                # 3. Maak een Pixmap van de afbeelding
                pixmap = QtGui.QPixmap.fromImage(q_img)

                # 4. SCHALEN MET BEHOUD VAN VERHOUDING (Aspect Ratio)
                # We schalen de pixmap naar de huidige grootte van het label
                scaled_pixmap = pixmap.scaled(
                    self.label_cam_view.size(),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation
                )

                # 5. Toon de geschaalde pixmap
                self.label_cam_view.setPixmap(scaled_pixmap)

    def remove_self(self):
        """Zorg dat de camera ook echt afgesloten wordt bij verwijderen"""
        self.timer.stop()
        if self.cap:
            self.cap.release()
        self.setParent(None)
        self.deleteLater()
        self.logic.tab_cameras.reorganize_layout()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Bereken hoogte op basis van 4:3 verhouding (3 / 4 = 0.75)
        target_height = int(self.width() * 0.75)
        self.setFixedHeight(target_height)


class TabCameras:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.window = logic_instance.window
        self.cam_layout = None
        self.btn_add_cam = None

    def setup(self):
        """Initialiseert de camera's tab"""
        if hasattr(self.window, 'gridLayout_6'):
            self.cam_layout = self.window.gridLayout_6
        else:
            # Fallback voor als de naam in Designer toch anders is
            print("Waarschuwing: gridLayout_6 niet gevonden, controleer de naam in Qt Designer")
            return

        self.cam_layout.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignLeft)
        
        # Zorg dat de MainWindow grootte niet verandert
        self.window.setMinimumSize(self.window.size())
        self.window.setMaximumSize(self.window.size())

        # Verwijder de oude statische elementen uit de UI (als ze nog bestaan)
        if hasattr(self.window, 'cam_container'): self.window.cam_container.deleteLater()
        if hasattr(self.window, 'btn_cam_add'): self.window.btn_cam_add.deleteLater()

        # Maak de nieuwe dynamische 'Toevoegen' knop
        self.btn_add_cam = AspectButton("+ Camera Toevoegen")
        self.btn_add_cam.setFixedWidth(200)
        self.btn_add_cam.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        self.btn_add_cam.setStyleSheet("""
            QPushButton {
                background-color: #252525;
                color: #0078D4;
                border: 2px dashed #0078D4;
                border-radius: 8px;
            }
        """)
        self.btn_add_cam.clicked.connect(self.add_camera_card)

        # Voeg de knop toe aan gridLayout_6 binnen frame_cam
        self.cam_layout.addWidget(self.btn_add_cam, 0, 0)

    def add_camera_card(self):
        """Plaatst een nieuwe kaart en geeft de logic-referentie mee"""
        new_cam = CameraWidget(self.logic)
        self.reorganize_layout(new_widget=new_cam)

    def reorganize_layout(self, new_widget=None):
        """Verplaatst alle widgets en reset de stretch om gaten en schaalproblemen te voorkomen"""
        layout = self.cam_layout
        widgets = []

        # 1. Verzamel actieve camera's
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item and item.widget() and item.widget() != self.btn_add_cam:
                widgets.append(item.widget())

        if new_widget:
            widgets.append(new_widget)

        # --- NIEUW: RESET STRETCH ---
        # We moeten de stretch van de kolommen en rijen terug op 0 zetten
        # zodat een enkele camera weer de volle breedte kan pakken.
        for i in range(layout.columnCount()):
            layout.setColumnStretch(i, 0)
        for i in range(layout.rowCount()):
            layout.setRowStretch(i, 0)

        # 2. Haal alles uit de grid
        for w in widgets:
            layout.removeWidget(w)
        layout.removeWidget(self.btn_add_cam)

        # 3. Deel opnieuw in (max 3 kolommen breed)
        max_cols = 3
        # Als er maar 1 widget is (camera of alleen de knop),
        # willen we niet dat hij vastzit in een 3-kolom grid stretch.
        current_num_widgets = len(widgets) + 1 # +1 voor de add_cam knop

        for i, w in enumerate(widgets):
            row, col = i // max_cols, i % max_cols
            layout.addWidget(w, row, col)
            # Voeg alleen stretch toe als er daadwerkelijk meer kolommen nodig zijn
            layout.setColumnStretch(col, 1)
            layout.setRowStretch(row, 1)

        # 4. Zet de 'add' knop aan het einde
        last_idx = len(widgets)
        last_row, last_col = last_idx // max_cols, last_idx % max_cols
        layout.addWidget(self.btn_add_cam, last_row, last_col)

        # Geef de kolom waar de knop in staat ook stretch
        layout.setColumnStretch(last_col, 1)
        layout.setRowStretch(last_row, 1)
