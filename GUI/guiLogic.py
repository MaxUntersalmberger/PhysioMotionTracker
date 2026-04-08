import cv2
from PyQt5 import QtCore, QtGui, QtWidgets

class Logic:
    def __init__(self, window):
        self.window = window
        self.cap = None
        self.timer = QtCore.QTimer()
        # Deze regel veroorzaakte de error; de functie 'display_frame' staat nu hieronder
        self.timer.timeout.connect(self.display_frame)
        
        # Pagina navigatie (Consistency)
        self.window.btn_main.clicked.connect(lambda: self.switch_page(0))
        self.window.btn_cameras.clicked.connect(lambda: self.switch_page(1))
        self.window.btn_settings.clicked.connect(lambda: self.switch_page(2))

        # Kalibratie knop (Hierarchy & Feedback)
        if hasattr(self.window, 'pushButton'):
            self.window.pushButton.clicked.connect(self.start_calibration_feedback)

        # Camera dropdown (Affordance)
        if hasattr(self.window, 'combo_cam_1'):
            self.refresh_camera_list()
            self.window.combo_cam_1.currentIndexChanged.connect(self.change_camera)

    def switch_page(self, index):
        self.window.stackedWidget.setCurrentIndex(index)

    def start_calibration_feedback(self):
        """Feedback principe: Gebruiker ziet direct dat er iets gebeurt"""
        self.window.pushButton.setText("Calibrating...")
        self.window.pushButton.setEnabled(False)
        # Simuleer een proces van 2 seconden
        QtCore.QTimer.singleShot(2000, self.reset_calibration_ui)

    def reset_calibration_ui(self):
        self.window.pushButton.setText("Start Calibration")
        self.window.pushButton.setEnabled(True)

    def refresh_camera_list(self):
        available_cameras = ["Geen Camera"]
        for i in range(5):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                available_cameras.append(f"Camera {i}")
                cap.release()
        self.window.combo_cam_1.clear()
        self.window.combo_cam_1.addItems(available_cameras)

    def change_camera(self):
        if self.cap is not None:
            self.timer.stop()
            self.cap.release()
            self.cap = None

        selection = self.window.combo_cam_1.currentText()
        if selection == "Geen Camera":
            if hasattr(self, 'video_label'):
                self.video_label.clear()
            # Feedback: Neutrale rand
            self.window.video_display_1.setStyleSheet("border: 2px solid #333; background-color: black;")
        else:
            try:
                cam_idx = int(selection.split(" ")[1])
                self.cap = cv2.VideoCapture(cam_idx, cv2.CAP_DSHOW)
                if self.cap.isOpened():
                    self.timer.start(30)
                    # Feedback: Actieve rand (groen)
                    self.window.video_display_1.setStyleSheet("border: 2px solid #00FF00; background-color: black;")
            except:
                print("Camera kon niet worden gestart.")

    def display_frame(self):
        """Deze functie ontbrak en veroorzaakte je error"""
        if self.cap is not None and self.cap.isOpened():
            ret, frame = self.cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                qt_image = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                
                if not hasattr(self, 'video_label'):
                    self.video_label = QtWidgets.QLabel()
                    self.video_label.setScaledContents(True)
                    self.video_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
                    layout = QtWidgets.QVBoxLayout(self.window.video_display_1)
                    layout.setContentsMargins(0, 0, 0, 0)
                    layout.addWidget(self.video_label)
                
                self.video_label.setPixmap(QtGui.QPixmap.fromImage(qt_image))