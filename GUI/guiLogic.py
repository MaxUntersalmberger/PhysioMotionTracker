import cv2
from PyQt5 import QtCore, QtGui, QtWidgets

class Logic:
    def __init__(self, window):
        self.window = window
        self.camera_units = []  
        
        # Sla de navigatieknoppen op voor styling
        self.nav_buttons = [self.window.btn_main, self.window.btn_cameras, self.window.btn_settings]
        
        # Pagina navigatie koppelen
        self.window.btn_main.clicked.connect(lambda: self.switch_page(0))
        self.window.btn_cameras.clicked.connect(lambda: self.switch_page(1))
        self.window.btn_settings.clicked.connect(lambda: self.switch_page(2))

        # Verberg de sjabloon container uit de Designer (voorkomt dubbele elementen)
        if hasattr(self.window, 'cam_container'):
            self.window.cam_container.hide()
        
        # Koppel de "Add" knop uit je nieuwe GUI
        self.window.btn_cam_add.clicked.connect(self.add_camera_unit)
        
        # Start op de eerste pagina en voeg direct de eerste camera toe
        self.add_camera_unit()
        self.switch_page(0) 

    def switch_page(self, index):
        """Wisselt pagina en verandert de kleur van de actieve knop"""
        self.window.stackedWidget.setCurrentIndex(index)
        
        # Styling: Actieve knop wordt blauw (#0078D4)
        active_style = "background-color: #0078D4; color: white; border: 1px solid #005A9E; font-weight: bold;"
        normal_style = "background-color: #2D2D2D; color: white; border: 1px solid #444;"

        for i, btn in enumerate(self.nav_buttons):
            btn.setStyleSheet(active_style if i == index else normal_style)

    def add_camera_unit(self):
        """Maakt een nieuwe camera unit met Dropdowns voor resolutie en FPS SpinBox"""
        unit_frame = QtWidgets.QFrame()
        unit_frame.setMinimumSize(300, 260)
        unit_frame.setStyleSheet("background-color: #1E1E1E; border: 1px solid #333; border-radius: 8px;")
        
        layout = QtWidgets.QGridLayout(unit_frame)

        # 1. Widgets aanmaken
        combo_cam = QtWidgets.QComboBox()
        combo_cam.addItems(["Selecteer Cam", "0", "1", "2", "3"])
        
        combo_res = QtWidgets.QComboBox()
        combo_res.addItems(["640x480", "1280x720", "1920x1080"])
        
        # FPS Label en Spinbox
        fps_label = QtWidgets.QLabel("FPS:")
        fps_label.setStyleSheet("border: none; color: #888;")
        
        spin_fps = QtWidgets.QSpinBox()
        spin_fps.setRange(1, 120)
        spin_fps.setValue(30)
        spin_fps.setSuffix(" fps")
        
        btn_del = QtWidgets.QPushButton("X")
        btn_del.setFixedSize(30, 30)
        btn_del.setStyleSheet("background-color: #A03030; color: white; font-weight: bold;")
        
        video_label = QtWidgets.QLabel("Geen Beeld")
        video_label.setAlignment(QtCore.Qt.AlignCenter)
        video_label.setStyleSheet("background-color: black; border-radius: 4px;")
        video_label.setScaledContents(True)

        # 2. Widgets in grid plaatsen
        layout.addWidget(combo_cam, 0, 0)
        layout.addWidget(combo_res, 0, 1)
        layout.addWidget(fps_label, 0, 2)
        layout.addWidget(spin_fps, 0, 3)
        layout.addWidget(btn_del, 0, 4)
        layout.addWidget(video_label, 1, 0, 1, 5)

        unit_data = {
            'frame': unit_frame,
            'cap': None,
            'label': video_label,
            'timer': QtCore.QTimer(),
            'spin_fps': spin_fps,
            'combo_res': combo_res
        }
        
        # 3. Events koppelen
        btn_del.clicked.connect(lambda: self.delete_camera_unit(unit_data))
        combo_cam.currentIndexChanged.connect(lambda: self.toggle_camera(unit_data, combo_cam))
        combo_res.currentIndexChanged.connect(lambda: self.update_resolution(unit_data))
        spin_fps.valueChanged.connect(lambda val: self.update_timer_speed(unit_data, val))
        unit_data['timer'].timeout.connect(lambda: self.update_frame(unit_data))
        
        self.camera_units.append(unit_data)
        self.reorganize_grid()

    def delete_camera_unit(self, unit_data):
        if unit_data['cap']:
            unit_data['cap'].release()
        unit_data['timer'].stop()
        unit_data['frame'].deleteLater()
        self.camera_units.remove(unit_data)
        self.reorganize_grid()

    def toggle_camera(self, unit_data, combo):
        selection = combo.currentText()
        if selection.isdigit():
            if unit_data['cap']: unit_data['cap'].release()
            
            cap = cv2.VideoCapture(int(selection), cv2.CAP_DSHOW)
            unit_data['cap'] = cap
            
            # Detecteer hardware FPS limiet
            hw_fps = int(cap.get(cv2.CAP_PROP_FPS))
            if hw_fps <= 0 or hw_fps > 120: hw_fps = 30
            
            unit_data['spin_fps'].setRange(1, hw_fps)
            unit_data['spin_fps'].setValue(hw_fps)
            
            self.update_resolution(unit_data)
            unit_data['timer'].start(1000 // hw_fps)
        else:
            if unit_data['cap']: unit_data['cap'].release()
            unit_data['timer'].stop()
            unit_data['label'].setText("Geen Beeld")

    def update_resolution(self, unit_data):
        if unit_data['cap'] and unit_data['cap'].isOpened():
            res_text = unit_data['combo_res'].currentText()
            w, h = map(int, res_text.split('x'))
            unit_data['cap'].set(cv2.CAP_PROP_FRAME_WIDTH, w)
            unit_data['cap'].set(cv2.CAP_PROP_FRAME_HEIGHT, h)

    def update_timer_speed(self, unit_data, fps_val):
        if fps_val > 0 and unit_data['timer'].isActive():
            unit_data['timer'].setInterval(1000 // fps_val)

    def update_frame(self, unit_data):
        if unit_data['cap'] and unit_data['cap'].isOpened():
            ret, frame = unit_data['cap'].read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                qt_img = QtGui.QImage(frame.data, w, h, ch * w, QtGui.QImage.Format_RGB888)
                unit_data['label'].setPixmap(QtGui.QPixmap.fromImage(qt_img))

    def reorganize_grid(self):
        """Plaats camera's en de Add-knop in het gridLayout_3"""
        layout = self.window.gridLayout_3
        max_cols = 3
        
        # Verwijder de knop tijdelijk om hem naar het einde te kunnen verplaatsen
        layout.removeWidget(self.window.btn_cam_add)
        
        for i, unit in enumerate(self.camera_units):
            # We beginnen op rij 1 omdat label_2 (titel) op rij 0 staat
            layout.addWidget(unit['frame'], (i // max_cols) + 1, i % max_cols)
        
        # Plaats de add-knop op de volgende positie
        next_pos = len(self.camera_units)
        layout.addWidget(self.window.btn_cam_add, (next_pos // max_cols) + 1, next_pos % max_cols)