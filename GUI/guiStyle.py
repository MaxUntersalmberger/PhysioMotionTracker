def apply_styles(window):
    # knop stylen
    window.pushButton.setStyleSheet("""
        QPushButton {
            background-color: #4CAF50;
            color: white;
            font-size: 16px;
            border-radius: 10px;
            padding: 8px 16px;
        }
        QPushButton:hover { background-color: #45a049; }
        QPushButton:pressed { background-color: #3e8e41; }
    """)
    
    # label stylen
    window.label.setStyleSheet("""
        QLabel {
            font-size: 24px;
            color: #333333;
            font-weight: bold;
        }
    """)