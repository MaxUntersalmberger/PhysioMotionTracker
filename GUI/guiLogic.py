import cv2
from PyQt5 import QtCore, QtGui, QtWidgets

class Logic:
    def __init__(self, window):
        self.window = window
        self.camera_units = []  
        
        # Sla de navigatieknoppen op in een lijst voor makkelijke styling
        self.nav_buttons = [self.window.btn_main, self.window.btn_cameras, self.window.btn_settings]
        
        # Pagina navigatie koppelen
        self.window.btn_main.clicked.connect(lambda: self.switch_page(0))
        self.window.btn_cameras.clicked.connect(lambda: self.switch_page(1))
        self.window.btn_settings.clicked.connect(lambda: self.switch_page(2))

        # Verberg de sjabloon container
        if hasattr(self.window, 'cam_container'):
            self.window.cam_container.hide()
        
        self.window.btn_cam_add.clicked.connect(self.add_camera_unit)
        
        # Start op de eerste pagina met de juiste styling
        self.add_camera_unit()
        self.switch_page(0) 

    def switch_page(self, index):
        """Wisselt van pagina en update de knopkleuren"""
        self.window.stackedWidget.setCurrentIndex(index)
        self.update_button_styles(index)

    def update_button_styles(self, active_index):
        """Reset alle knoppen en geeft de actieve knop een accentkleur"""
        # Standaard stijl voor niet-actieve knoppen
        normal_style = "background-color: #2D2D2D; color: white; border: 1px solid #444;"
        # Stijl voor de actieve knop (bijv. blauw accent)
        active_style = "background-color: #0078D4; color: white; border: 1px solid #005A9E; font-weight: bold;"

        for i, btn in enumerate(self.nav_buttons):
            if i == active_index:
                btn.setStyleSheet(active_style)
            else:
                btn.setStyleSheet(normal_style)

    # --- De rest van je camera logica blijft hetzelfde ---
    def add_camera_unit(self):
        unit_frame = QtWidgets.QFrame()
        unit_frame.setMinimumSize(250, 200)
        unit_frame.setStyleSheet("background-color: #1E1E1E; border: 1px solid #333; border-radius: 8px;")
        layout = QtWidgets.QGridLayout(unit_frame)

        combo = QtWidgets.QComboBox()
        combo.addItems(["Selecteer Camera", "0", "1", "2", "3"])
        btn_set = QtWidgets.QPushButton("⚙️")
        btn_set.setFixedSize(30, 30)
        btn_del = QtWidgets.QPushButton("X")
        btn_del.setFixedSize(30, 30)
        btn_del.setStyleSheet("background-color: #A03030; color: white;")
        
        video_label = QtWidgets.QLabel("Geen Beeld")
        video_label.setAlignment(QtCore.Qt.AlignCenter)
        video_label.setStyleSheet("background-color: black;")
        video_label.setScaledContents(True)

        layout.addWidget(combo, 0, 0)
        layout.addWidget(btn_set, 0, 1)
        layout.addWidget(btn_del, 0, 2)
        layout.addWidget(video_label, 1, 0, 1, 3)

        unit_data = {'frame': unit_frame, 'cap': None, 'label': video_label, 'timer': QtCore.QTimer()}
        btn_del.clicked.connect(lambda: self.delete_camera_unit(unit_data))
        combo.currentIndexChanged.connect(lambda: self.toggle_camera(unit_data, combo))
        unit_data['timer'].timeout.connect(lambda: self.update_frame(unit_data))
        
        self.camera_units.append(unit_data)
        self.reorganize_grid()

    def delete_camera_unit(self, unit_data):
        if unit_data['cap']: unit_data['cap'].release()
        unit_data['timer'].stop()
        unit_data['frame'].deleteLater()
        self.camera_units.remove(unit_data)
        self.reorganize_grid()

    def reorganize_grid(self):
        layout = self.window.gridLayout_3
        max_columns = 3 
        layout.removeWidget(self.window.btn_cam_add)
        for i, unit in enumerate(self.camera_units):
            layout.addWidget(unit['frame'], (i // max_columns) + 1, i % max_columns)
        
        idx = len(self.camera_units)
        layout.addWidget(self.window.btn_cam_add, (idx // max_columns) + 1, idx % max_columns)

    def toggle_camera(self, unit_data, combo):
        selection = combo.currentText()
        if selection.isdigit():
            if unit_data['cap']: unit_data['cap'].release()
            unit_data['cap'] = cv2.VideoCapture(int(selection), cv2.CAP_DSHOW)
            unit_data['timer'].start(30)
        else:
            if unit_data['cap']: unit_data['cap'].release()
            unit_data['timer'].stop()
            unit_data['label'].setText("Geen Beeld")

    def update_frame(self, unit_data):
        if unit_data['cap'] and unit_data['cap'].isOpened():
            ret, frame = unit_data['cap'].read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                qt_img = QtGui.QImage(frame.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
                unit_data['label'].setPixmap(QtGui.QPixmap.fromImage(qt_img))