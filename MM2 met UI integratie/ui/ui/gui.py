# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'GUI.ui'
##
## Created by: Qt User Interface Compiler version 6.11.0
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QAction, QBrush, QColor, QConicalGradient,
    QCursor, QFont, QFontDatabase, QGradient,
    QIcon, QImage, QKeySequence, QLinearGradient,
    QPainter, QPalette, QPixmap, QRadialGradient,
    QTransform)
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMenuBar,
    QPlainTextEdit, QPushButton, QSizePolicy, QStackedWidget,
    QTextEdit, QVBoxLayout, QWidget)
import resources_rc

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.setEnabled(True)
        MainWindow.resize(914, 695)
        MainWindow.setMinimumSize(QSize(0, 0))
        MainWindow.setMaximumSize(QSize(16777215, 16777215))
        icon = QIcon()
        icon.addFile(u":/HU_Logo.png", QSize(), QIcon.Mode.Normal, QIcon.State.Off)
        MainWindow.setWindowIcon(icon)
        self.actionRun = QAction(MainWindow)
        self.actionRun.setObjectName(u"actionRun")
        self.actionNew_project = QAction(MainWindow)
        self.actionNew_project.setObjectName(u"actionNew_project")
        self.actionOpen_project = QAction(MainWindow)
        self.actionOpen_project.setObjectName(u"actionOpen_project")
        self.actionQuit = QAction(MainWindow)
        self.actionQuit.setObjectName(u"actionQuit")
        self.actionOpen_documentation = QAction(MainWindow)
        self.actionOpen_documentation.setObjectName(u"actionOpen_documentation")
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.centralwidget.setMaximumSize(QSize(16777215, 16777215))
        self.gridLayout = QGridLayout(self.centralwidget)
        self.gridLayout.setObjectName(u"gridLayout")
        self.frame_pages = QFrame(self.centralwidget)
        self.frame_pages.setObjectName(u"frame_pages")
        sizePolicy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.frame_pages.sizePolicy().hasHeightForWidth())
        self.frame_pages.setSizePolicy(sizePolicy)
        self.frame_pages.setFrameShape(QFrame.Shape.NoFrame)
        self.gridLayout_2 = QGridLayout(self.frame_pages)
        self.gridLayout_2.setObjectName(u"gridLayout_2")
        self.stackedWidget = QStackedWidget(self.frame_pages)
        self.stackedWidget.setObjectName(u"stackedWidget")
        self.page_home = QWidget()
        self.page_home.setObjectName(u"page_home")
        self.gridLayout_4 = QGridLayout(self.page_home)
        self.gridLayout_4.setObjectName(u"gridLayout_4")
        self.btn_newproject = QPushButton(self.page_home)
        self.btn_newproject.setObjectName(u"btn_newproject")
        sizePolicy1 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy1.setHorizontalStretch(0)
        sizePolicy1.setVerticalStretch(0)
        sizePolicy1.setHeightForWidth(self.btn_newproject.sizePolicy().hasHeightForWidth())
        self.btn_newproject.setSizePolicy(sizePolicy1)
        self.btn_newproject.setMinimumSize(QSize(0, 0))
        self.btn_newproject.setMaximumSize(QSize(16777215, 16777215))
        self.btn_newproject.setSizeIncrement(QSize(0, 0))
        self.btn_newproject.setBaseSize(QSize(0, 0))
        self.btn_newproject.setMouseTracking(True)
        self.btn_newproject.setIconSize(QSize(16, 16))

        self.gridLayout_4.addWidget(self.btn_newproject, 0, 0, 1, 1)

        self.btn_loadproject = QPushButton(self.page_home)
        self.btn_loadproject.setObjectName(u"btn_loadproject")
        sizePolicy1.setHeightForWidth(self.btn_loadproject.sizePolicy().hasHeightForWidth())
        self.btn_loadproject.setSizePolicy(sizePolicy1)
        self.btn_loadproject.setMouseTracking(True)

        self.gridLayout_4.addWidget(self.btn_loadproject, 1, 0, 1, 1)

        self.stackedWidget.addWidget(self.page_home)
        self.page_cameras = QWidget()
        self.page_cameras.setObjectName(u"page_cameras")
        self.gridLayout_3 = QGridLayout(self.page_cameras)
        self.gridLayout_3.setObjectName(u"gridLayout_3")
        self.frame = QFrame(self.page_cameras)
        self.frame.setObjectName(u"frame")
        sizePolicy2 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        sizePolicy2.setHorizontalStretch(0)
        sizePolicy2.setVerticalStretch(0)
        sizePolicy2.setHeightForWidth(self.frame.sizePolicy().hasHeightForWidth())
        self.frame.setSizePolicy(sizePolicy2)
        self.frame.setFrameShape(QFrame.Shape.NoFrame)
        self.gridLayout_9 = QGridLayout(self.frame)
        self.gridLayout_9.setObjectName(u"gridLayout_9")
        self.frame_2 = QFrame(self.frame)
        self.frame_2.setObjectName(u"frame_2")
        sizePolicy2.setHeightForWidth(self.frame_2.sizePolicy().hasHeightForWidth())
        self.frame_2.setSizePolicy(sizePolicy2)
        self.frame_2.setFrameShape(QFrame.Shape.NoFrame)
        self.gridLayout_10 = QGridLayout(self.frame_2)
        self.gridLayout_10.setObjectName(u"gridLayout_10")
        self.lab_cap_intrinsics = QLabel(self.frame_2)
        self.lab_cap_intrinsics.setObjectName(u"lab_cap_intrinsics")

        self.gridLayout_10.addWidget(self.lab_cap_intrinsics, 0, 0, 1, 1)

        self.btn_cap_calculate_intrinsics = QPushButton(self.frame_2)
        self.btn_cap_calculate_intrinsics.setObjectName(u"btn_cap_calculate_intrinsics")

        self.gridLayout_10.addWidget(self.btn_cap_calculate_intrinsics, 2, 0, 1, 1)

        self.btn_cap_intrinsics_start = QPushButton(self.frame_2)
        self.btn_cap_intrinsics_start.setObjectName(u"btn_cap_intrinsics_start")

        self.gridLayout_10.addWidget(self.btn_cap_intrinsics_start, 1, 0, 1, 1)


        self.gridLayout_9.addWidget(self.frame_2, 1, 0, 2, 1)

        self.frame_3 = QFrame(self.frame)
        self.frame_3.setObjectName(u"frame_3")
        sizePolicy1.setHeightForWidth(self.frame_3.sizePolicy().hasHeightForWidth())
        self.frame_3.setSizePolicy(sizePolicy1)
        self.frame_3.setFrameShape(QFrame.Shape.NoFrame)
        self.gridLayout_11 = QGridLayout(self.frame_3)
        self.gridLayout_11.setObjectName(u"gridLayout_11")
        self.btn_cap_calculate_extrinsics = QPushButton(self.frame_3)
        self.btn_cap_calculate_extrinsics.setObjectName(u"btn_cap_calculate_extrinsics")

        self.gridLayout_11.addWidget(self.btn_cap_calculate_extrinsics, 3, 0, 1, 1)

        self.lab_cap_extrinsics = QLabel(self.frame_3)
        self.lab_cap_extrinsics.setObjectName(u"lab_cap_extrinsics")
        sizePolicy1.setHeightForWidth(self.lab_cap_extrinsics.sizePolicy().hasHeightForWidth())
        self.lab_cap_extrinsics.setSizePolicy(sizePolicy1)

        self.gridLayout_11.addWidget(self.lab_cap_extrinsics, 1, 0, 1, 1)

        self.btn_cap_extrinsics_start = QPushButton(self.frame_3)
        self.btn_cap_extrinsics_start.setObjectName(u"btn_cap_extrinsics_start")

        self.gridLayout_11.addWidget(self.btn_cap_extrinsics_start, 2, 0, 1, 1)


        self.gridLayout_9.addWidget(self.frame_3, 1, 1, 2, 1)

        self.btn_cap_reset_calibration = QPushButton(self.frame)
        self.btn_cap_reset_calibration.setObjectName(u"btn_cap_reset_calibration")

        self.gridLayout_9.addWidget(self.btn_cap_reset_calibration, 7, 0, 1, 2)


        self.gridLayout_3.addWidget(self.frame, 0, 0, 1, 2)

        self.frame_cam = QFrame(self.page_cameras)
        self.frame_cam.setObjectName(u"frame_cam")
        self.frame_cam.setFrameShape(QFrame.Shape.NoFrame)
        self.gridLayout_6 = QGridLayout(self.frame_cam)
        self.gridLayout_6.setObjectName(u"gridLayout_6")

        self.gridLayout_3.addWidget(self.frame_cam, 1, 0, 1, 2)

        self.stackedWidget.addWidget(self.page_cameras)
        self.page_results = QWidget()
        self.page_results.setObjectName(u"page_results")
        self.gridLayout_8 = QGridLayout(self.page_results)
        self.gridLayout_8.setObjectName(u"gridLayout_8")
        self.stackedWidget_2 = QStackedWidget(self.page_results)
        self.stackedWidget_2.setObjectName(u"stackedWidget_2")
        self.page_results_tab = QWidget()
        self.page_results_tab.setObjectName(u"page_results_tab")
        self.gridLayout_13 = QGridLayout(self.page_results_tab)
        self.gridLayout_13.setObjectName(u"gridLayout_13")
        self.frame_res_intrinsic_results = QFrame(self.page_results_tab)
        self.frame_res_intrinsic_results.setObjectName(u"frame_res_intrinsic_results")
        sizePolicy3 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy3.setHorizontalStretch(6)
        sizePolicy3.setVerticalStretch(0)
        sizePolicy3.setHeightForWidth(self.frame_res_intrinsic_results.sizePolicy().hasHeightForWidth())
        self.frame_res_intrinsic_results.setSizePolicy(sizePolicy3)
        self.frame_res_intrinsic_results.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_res_intrinsic_results.setFrameShadow(QFrame.Shadow.Raised)

        self.gridLayout_13.addWidget(self.frame_res_intrinsic_results, 1, 1, 1, 1)

        self.lab_res_intrinsics_results = QLabel(self.page_results_tab)
        self.lab_res_intrinsics_results.setObjectName(u"lab_res_intrinsics_results")
        sizePolicy4 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        sizePolicy4.setHorizontalStretch(2)
        sizePolicy4.setVerticalStretch(0)
        sizePolicy4.setHeightForWidth(self.lab_res_intrinsics_results.sizePolicy().hasHeightForWidth())
        self.lab_res_intrinsics_results.setSizePolicy(sizePolicy4)

        self.gridLayout_13.addWidget(self.lab_res_intrinsics_results, 1, 0, 1, 1)

        self.lab_res_frames = QLabel(self.page_results_tab)
        self.lab_res_frames.setObjectName(u"lab_res_frames")

        self.gridLayout_13.addWidget(self.lab_res_frames, 7, 0, 1, 1)

        self.frame_4 = QFrame(self.page_results_tab)
        self.frame_4.setObjectName(u"frame_4")
        self.frame_4.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_4.setFrameShadow(QFrame.Shadow.Raised)
        self.gridLayout_12 = QGridLayout(self.frame_4)
        self.gridLayout_12.setObjectName(u"gridLayout_12")
        self.export_toml = QPushButton(self.frame_4)
        self.export_toml.setObjectName(u"export_toml")
        sizePolicy5 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Preferred)
        sizePolicy5.setHorizontalStretch(0)
        sizePolicy5.setVerticalStretch(0)
        sizePolicy5.setHeightForWidth(self.export_toml.sizePolicy().hasHeightForWidth())
        self.export_toml.setSizePolicy(sizePolicy5)

        self.gridLayout_12.addWidget(self.export_toml, 2, 1, 1, 1)

        self.btn_res_show_tmol = QPushButton(self.frame_4)
        self.btn_res_show_tmol.setObjectName(u"btn_res_show_tmol")
        sizePolicy5.setHeightForWidth(self.btn_res_show_tmol.sizePolicy().hasHeightForWidth())
        self.btn_res_show_tmol.setSizePolicy(sizePolicy5)

        self.gridLayout_12.addWidget(self.btn_res_show_tmol, 2, 0, 1, 1)


        self.gridLayout_13.addWidget(self.frame_4, 0, 0, 1, 2)

        self.frame_res_extrinsics_results = QFrame(self.page_results_tab)
        self.frame_res_extrinsics_results.setObjectName(u"frame_res_extrinsics_results")
        self.frame_res_extrinsics_results.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_res_extrinsics_results.setFrameShadow(QFrame.Shadow.Raised)

        self.gridLayout_13.addWidget(self.frame_res_extrinsics_results, 4, 1, 1, 1)

        self.frame_res_aantal_frames = QFrame(self.page_results_tab)
        self.frame_res_aantal_frames.setObjectName(u"frame_res_aantal_frames")
        self.frame_res_aantal_frames.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_res_aantal_frames.setFrameShadow(QFrame.Shadow.Raised)

        self.gridLayout_13.addWidget(self.frame_res_aantal_frames, 7, 1, 1, 1)

        self.lab_res_extrinsics_results = QLabel(self.page_results_tab)
        self.lab_res_extrinsics_results.setObjectName(u"lab_res_extrinsics_results")

        self.gridLayout_13.addWidget(self.lab_res_extrinsics_results, 4, 0, 1, 1)

        self.frame_res_camera_info = QFrame(self.page_results_tab)
        self.frame_res_camera_info.setObjectName(u"frame_res_camera_info")
        self.frame_res_camera_info.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_res_camera_info.setFrameShadow(QFrame.Shadow.Raised)

        self.gridLayout_13.addWidget(self.frame_res_camera_info, 6, 1, 1, 1)

        self.lab_res_cam_info = QLabel(self.page_results_tab)
        self.lab_res_cam_info.setObjectName(u"lab_res_cam_info")

        self.gridLayout_13.addWidget(self.lab_res_cam_info, 6, 0, 1, 1)

        self.lab_res_error = QLabel(self.page_results_tab)
        self.lab_res_error.setObjectName(u"lab_res_error")

        self.gridLayout_13.addWidget(self.lab_res_error, 8, 0, 1, 1)

        self.frame_res_error = QFrame(self.page_results_tab)
        self.frame_res_error.setObjectName(u"frame_res_error")
        self.frame_res_error.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_res_error.setFrameShadow(QFrame.Shadow.Raised)

        self.gridLayout_13.addWidget(self.frame_res_error, 8, 1, 1, 1)

        self.stackedWidget_2.addWidget(self.page_results_tab)
        self.page_preview_TMOL = QWidget()
        self.page_preview_TMOL.setObjectName(u"page_preview_TMOL")
        self.gridLayout_14 = QGridLayout(self.page_preview_TMOL)
        self.gridLayout_14.setObjectName(u"gridLayout_14")
        self.pushButton = QPushButton(self.page_preview_TMOL)
        self.pushButton.setObjectName(u"pushButton")
        sizePolicy6 = QSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        sizePolicy6.setHorizontalStretch(0)
        sizePolicy6.setVerticalStretch(0)
        sizePolicy6.setHeightForWidth(self.pushButton.sizePolicy().hasHeightForWidth())
        self.pushButton.setSizePolicy(sizePolicy6)
        self.pushButton.setAutoDefault(False)

        self.gridLayout_14.addWidget(self.pushButton, 1, 1, 1, 1)

        self.frame_res_preview_tmol = QFrame(self.page_preview_TMOL)
        self.frame_res_preview_tmol.setObjectName(u"frame_res_preview_tmol")
        sizePolicy7 = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Minimum)
        sizePolicy7.setHorizontalStretch(0)
        sizePolicy7.setVerticalStretch(0)
        sizePolicy7.setHeightForWidth(self.frame_res_preview_tmol.sizePolicy().hasHeightForWidth())
        self.frame_res_preview_tmol.setSizePolicy(sizePolicy7)
        self.frame_res_preview_tmol.setFrameShape(QFrame.Shape.StyledPanel)
        self.frame_res_preview_tmol.setFrameShadow(QFrame.Shadow.Raised)

        self.gridLayout_14.addWidget(self.frame_res_preview_tmol, 2, 0, 1, 2)

        self.label = QLabel(self.page_preview_TMOL)
        self.label.setObjectName(u"label")

        self.gridLayout_14.addWidget(self.label, 1, 0, 1, 1)

        self.stackedWidget_2.addWidget(self.page_preview_TMOL)

        self.gridLayout_8.addWidget(self.stackedWidget_2, 0, 0, 1, 1)

        self.stackedWidget.addWidget(self.page_results)
        self.page_directory = QWidget()
        self.page_directory.setObjectName(u"page_directory")
        self.gridLayout_7 = QGridLayout(self.page_directory)
        self.gridLayout_7.setObjectName(u"gridLayout_7")
        self.frame_directory = QFrame(self.page_directory)
        self.frame_directory.setObjectName(u"frame_directory")
        self.frame_directory.setFrameShape(QFrame.Shape.NoFrame)

        self.gridLayout_7.addWidget(self.frame_directory, 0, 0, 1, 1)

        self.stackedWidget.addWidget(self.page_directory)
        self.page_diagnostics = QWidget()
        self.page_diagnostics.setObjectName(u"page_diagnostics")
        self.gridLayout_5 = QGridLayout(self.page_diagnostics)
        self.gridLayout_5.setObjectName(u"gridLayout_5")
        self.text_diag_current_fps = QTextEdit(self.page_diagnostics)
        self.text_diag_current_fps.setObjectName(u"text_diag_current_fps")

        self.gridLayout_5.addWidget(self.text_diag_current_fps, 1, 2, 1, 2)

        self.text_diag_dropped_frames = QTextEdit(self.page_diagnostics)
        self.text_diag_dropped_frames.setObjectName(u"text_diag_dropped_frames")

        self.gridLayout_5.addWidget(self.text_diag_dropped_frames, 0, 2, 1, 2)

        self.lab_diag_current_fps = QLabel(self.page_diagnostics)
        self.lab_diag_current_fps.setObjectName(u"lab_diag_current_fps")

        self.gridLayout_5.addWidget(self.lab_diag_current_fps, 1, 0, 1, 1)

        self.lab_diag_intrinsics_time = QLabel(self.page_diagnostics)
        self.lab_diag_intrinsics_time.setObjectName(u"lab_diag_intrinsics_time")

        self.gridLayout_5.addWidget(self.lab_diag_intrinsics_time, 4, 0, 1, 1)

        self.text_diag_used_cams = QTextEdit(self.page_diagnostics)
        self.text_diag_used_cams.setObjectName(u"text_diag_used_cams")

        self.gridLayout_5.addWidget(self.text_diag_used_cams, 3, 2, 1, 2)

        self.lab_diag_dropped_frames = QLabel(self.page_diagnostics)
        self.lab_diag_dropped_frames.setObjectName(u"lab_diag_dropped_frames")

        self.gridLayout_5.addWidget(self.lab_diag_dropped_frames, 0, 0, 1, 1)

        self.lab_diag_extrinsics_time = QLabel(self.page_diagnostics)
        self.lab_diag_extrinsics_time.setObjectName(u"lab_diag_extrinsics_time")

        self.gridLayout_5.addWidget(self.lab_diag_extrinsics_time, 5, 0, 1, 1)

        self.lab_diag_used_cams = QLabel(self.page_diagnostics)
        self.lab_diag_used_cams.setObjectName(u"lab_diag_used_cams")

        self.gridLayout_5.addWidget(self.lab_diag_used_cams, 3, 0, 1, 1)

        self.lab_diag_total_time = QLabel(self.page_diagnostics)
        self.lab_diag_total_time.setObjectName(u"lab_diag_total_time")

        self.gridLayout_5.addWidget(self.lab_diag_total_time, 7, 0, 1, 1)

        self.text_diag_Intrinsics_time = QTextEdit(self.page_diagnostics)
        self.text_diag_Intrinsics_time.setObjectName(u"text_diag_Intrinsics_time")

        self.gridLayout_5.addWidget(self.text_diag_Intrinsics_time, 4, 2, 1, 2)

        self.text_diag_extrinsics_time = QTextEdit(self.page_diagnostics)
        self.text_diag_extrinsics_time.setObjectName(u"text_diag_extrinsics_time")

        self.gridLayout_5.addWidget(self.text_diag_extrinsics_time, 5, 2, 1, 2)

        self.text_diag_total_time = QTextEdit(self.page_diagnostics)
        self.text_diag_total_time.setObjectName(u"text_diag_total_time")

        self.gridLayout_5.addWidget(self.text_diag_total_time, 7, 2, 1, 2)

        self.stackedWidget.addWidget(self.page_diagnostics)
        self.page_advanced_settings = QWidget()
        self.page_advanced_settings.setObjectName(u"page_advanced_settings")
        self.gridLayout_15 = QGridLayout(self.page_advanced_settings)
        self.gridLayout_15.setObjectName(u"gridLayout_15")
        self.stackedWidget.addWidget(self.page_advanced_settings)

        self.gridLayout_2.addWidget(self.stackedWidget, 0, 0, 1, 1)


        self.gridLayout.addWidget(self.frame_pages, 1, 3, 1, 2)

        self.plaintextedit_console = QPlainTextEdit(self.centralwidget)
        self.plaintextedit_console.setObjectName(u"plaintextedit_console")
        sizePolicy8 = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        sizePolicy8.setHorizontalStretch(150)
        sizePolicy8.setVerticalStretch(0)
        sizePolicy8.setHeightForWidth(self.plaintextedit_console.sizePolicy().hasHeightForWidth())
        self.plaintextedit_console.setSizePolicy(sizePolicy8)
        self.plaintextedit_console.setMinimumSize(QSize(2, 0))

        self.gridLayout.addWidget(self.plaintextedit_console, 6, 3, 1, 2)

        self.frame_menu = QFrame(self.centralwidget)
        self.frame_menu.setObjectName(u"frame_menu")
        sizePolicy9 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy9.setHorizontalStretch(50)
        sizePolicy9.setVerticalStretch(0)
        sizePolicy9.setHeightForWidth(self.frame_menu.sizePolicy().hasHeightForWidth())
        self.frame_menu.setSizePolicy(sizePolicy9)
        self.frame_menu.setMaximumSize(QSize(160000, 160000))
        self.frame_menu.setFrameShape(QFrame.Shape.NoFrame)
        self.verticalLayout = QVBoxLayout(self.frame_menu)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.label_logo = QLabel(self.frame_menu)
        self.label_logo.setObjectName(u"label_logo")
        sizePolicy10 = QSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        sizePolicy10.setHorizontalStretch(0)
        sizePolicy10.setVerticalStretch(10)
        sizePolicy10.setHeightForWidth(self.label_logo.sizePolicy().hasHeightForWidth())
        self.label_logo.setSizePolicy(sizePolicy10)
        self.label_logo.setMinimumSize(QSize(0, 0))
        self.label_logo.setMaximumSize(QSize(160000, 160000))
        self.label_logo.setFrameShape(QFrame.Shape.NoFrame)
        self.label_logo.setPixmap(QPixmap(u":/HuMoCap groot.png"))
        self.label_logo.setScaledContents(True)
        self.label_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.verticalLayout.addWidget(self.label_logo)

        self.btn_home = QPushButton(self.frame_menu)
        self.btn_home.setObjectName(u"btn_home")
        self.btn_home.setEnabled(True)
        sizePolicy11 = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sizePolicy11.setHorizontalStretch(100)
        sizePolicy11.setVerticalStretch(10)
        sizePolicy11.setHeightForWidth(self.btn_home.sizePolicy().hasHeightForWidth())
        self.btn_home.setSizePolicy(sizePolicy11)
        self.btn_home.setMinimumSize(QSize(0, 0))
        self.btn_home.setMaximumSize(QSize(16777215, 16777215))
        self.btn_home.setMouseTracking(True)

        self.verticalLayout.addWidget(self.btn_home)

        self.btn_cameras = QPushButton(self.frame_menu)
        self.btn_cameras.setObjectName(u"btn_cameras")
        sizePolicy11.setHeightForWidth(self.btn_cameras.sizePolicy().hasHeightForWidth())
        self.btn_cameras.setSizePolicy(sizePolicy11)
        self.btn_cameras.setMinimumSize(QSize(0, 0))
        self.btn_cameras.setMaximumSize(QSize(16777215, 16777215))
        self.btn_cameras.setMouseTracking(True)

        self.verticalLayout.addWidget(self.btn_cameras)

        self.btn_results = QPushButton(self.frame_menu)
        self.btn_results.setObjectName(u"btn_results")
        sizePolicy11.setHeightForWidth(self.btn_results.sizePolicy().hasHeightForWidth())
        self.btn_results.setSizePolicy(sizePolicy11)
        self.btn_results.setMinimumSize(QSize(0, 0))
        self.btn_results.setMaximumSize(QSize(16777215, 16777215))
        self.btn_results.setSizeIncrement(QSize(0, 0))
        self.btn_results.setMouseTracking(True)

        self.verticalLayout.addWidget(self.btn_results)

        self.btn_directory = QPushButton(self.frame_menu)
        self.btn_directory.setObjectName(u"btn_directory")
        sizePolicy11.setHeightForWidth(self.btn_directory.sizePolicy().hasHeightForWidth())
        self.btn_directory.setSizePolicy(sizePolicy11)
        self.btn_directory.setMinimumSize(QSize(0, 0))
        self.btn_directory.setMaximumSize(QSize(16777215, 16777215))
        self.btn_directory.setSizeIncrement(QSize(0, 0))
        self.btn_directory.setMouseTracking(True)

        self.verticalLayout.addWidget(self.btn_directory)

        self.btn_diagnostics = QPushButton(self.frame_menu)
        self.btn_diagnostics.setObjectName(u"btn_diagnostics")
        sizePolicy11.setHeightForWidth(self.btn_diagnostics.sizePolicy().hasHeightForWidth())
        self.btn_diagnostics.setSizePolicy(sizePolicy11)
        self.btn_diagnostics.setMinimumSize(QSize(0, 0))
        self.btn_diagnostics.setMaximumSize(QSize(16777215, 16777215))
        self.btn_diagnostics.setMouseTracking(True)

        self.verticalLayout.addWidget(self.btn_diagnostics)

        self.btn_advanced_settings = QPushButton(self.frame_menu)
        self.btn_advanced_settings.setObjectName(u"btn_advanced_settings")
        sizePolicy11.setHeightForWidth(self.btn_advanced_settings.sizePolicy().hasHeightForWidth())
        self.btn_advanced_settings.setSizePolicy(sizePolicy11)
        self.btn_advanced_settings.setMinimumSize(QSize(0, 0))
        self.btn_advanced_settings.setMaximumSize(QSize(16777215, 16777215))

        self.verticalLayout.addWidget(self.btn_advanced_settings)


        self.gridLayout.addWidget(self.frame_menu, 1, 0, 7, 1)

        self.lineedit_console_input = QLineEdit(self.centralwidget)
        self.lineedit_console_input.setObjectName(u"lineedit_console_input")

        self.gridLayout.addWidget(self.lineedit_console_input, 7, 3, 1, 2)

        MainWindow.setCentralWidget(self.centralwidget)
        self.menuBar = QMenuBar(MainWindow)
        self.menuBar.setObjectName(u"menuBar")
        self.menuBar.setGeometry(QRect(0, 0, 914, 33))
        self.menuFile = QMenu(self.menuBar)
        self.menuFile.setObjectName(u"menuFile")
        self.menuRun = QMenu(self.menuBar)
        self.menuRun.setObjectName(u"menuRun")
        self.menuHelp = QMenu(self.menuBar)
        self.menuHelp.setObjectName(u"menuHelp")
        MainWindow.setMenuBar(self.menuBar)

        self.menuBar.addAction(self.menuFile.menuAction())
        self.menuBar.addAction(self.menuRun.menuAction())
        self.menuBar.addAction(self.menuHelp.menuAction())
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionNew_project)
        self.menuFile.addAction(self.actionOpen_project)
        self.menuFile.addAction(self.actionQuit)
        self.menuHelp.addAction(self.actionOpen_documentation)

        self.retranslateUi(MainWindow)

        self.stackedWidget.setCurrentIndex(1)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.actionRun.setText(QCoreApplication.translate("MainWindow", u"Run", None))
        self.actionNew_project.setText(QCoreApplication.translate("MainWindow", u"New project", None))
        self.actionOpen_project.setText(QCoreApplication.translate("MainWindow", u"Open project", None))
        self.actionQuit.setText(QCoreApplication.translate("MainWindow", u"Quit", None))
        self.actionOpen_documentation.setText(QCoreApplication.translate("MainWindow", u"Open documentation", None))
        self.btn_newproject.setText(QCoreApplication.translate("MainWindow", u"New Project", None))
        self.btn_loadproject.setText(QCoreApplication.translate("MainWindow", u"Load Project", None))
        self.lab_cap_intrinsics.setText(QCoreApplication.translate("MainWindow", u"Intrinsics", None))
        self.btn_cap_calculate_intrinsics.setText(QCoreApplication.translate("MainWindow", u"Calculate", None))
        self.btn_cap_intrinsics_start.setText(QCoreApplication.translate("MainWindow", u"Start", None))
        self.btn_cap_calculate_extrinsics.setText(QCoreApplication.translate("MainWindow", u"Calculate", None))
        self.lab_cap_extrinsics.setText(QCoreApplication.translate("MainWindow", u"Extrinsics", None))
        self.btn_cap_extrinsics_start.setText(QCoreApplication.translate("MainWindow", u"Start", None))
        self.btn_cap_reset_calibration.setText(QCoreApplication.translate("MainWindow", u"Reset Calibration", None))
        self.lab_res_intrinsics_results.setText(QCoreApplication.translate("MainWindow", u"Intrinsics results", None))
        self.lab_res_frames.setText(QCoreApplication.translate("MainWindow", u"Frames", None))
        self.export_toml.setText(QCoreApplication.translate("MainWindow", u"Export TOML", None))
        self.btn_res_show_tmol.setText(QCoreApplication.translate("MainWindow", u"Preview TMOL", None))
        self.lab_res_extrinsics_results.setText(QCoreApplication.translate("MainWindow", u"Extrinsics results", None))
        self.lab_res_cam_info.setText(QCoreApplication.translate("MainWindow", u"Camera Info", None))
        self.lab_res_error.setText(QCoreApplication.translate("MainWindow", u"Error:", None))
        self.pushButton.setText(QCoreApplication.translate("MainWindow", u"x", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u"Preview TMOL", None))
        self.lab_diag_current_fps.setText(QCoreApplication.translate("MainWindow", u"Current FPS", None))
        self.lab_diag_intrinsics_time.setText(QCoreApplication.translate("MainWindow", u"Intrinsics Time", None))
        self.lab_diag_dropped_frames.setText(QCoreApplication.translate("MainWindow", u"Dropped Frames", None))
        self.lab_diag_extrinsics_time.setText(QCoreApplication.translate("MainWindow", u"Extrinsics Time", None))
        self.lab_diag_used_cams.setText(QCoreApplication.translate("MainWindow", u"Used Camera's", None))
        self.lab_diag_total_time.setText(QCoreApplication.translate("MainWindow", u"Total Time", None))
        self.label_logo.setText("")
        self.btn_home.setText(QCoreApplication.translate("MainWindow", u"Home", None))
        self.btn_cameras.setText(QCoreApplication.translate("MainWindow", u"Camera's /\n"
"Kalibratie", None))
        self.btn_results.setText(QCoreApplication.translate("MainWindow", u"Results /\n"
"Export", None))
        self.btn_directory.setText(QCoreApplication.translate("MainWindow", u"Directory", None))
        self.btn_diagnostics.setText(QCoreApplication.translate("MainWindow", u"Diagnostics", None))
        self.btn_advanced_settings.setText(QCoreApplication.translate("MainWindow", u"Geavanceerde\n"
"instellingen", None))
        self.menuFile.setTitle(QCoreApplication.translate("MainWindow", u"&File", None))
        self.menuRun.setTitle(QCoreApplication.translate("MainWindow", u"Run", None))
        self.menuHelp.setTitle(QCoreApplication.translate("MainWindow", u"Help", None))
    # retranslateUi

