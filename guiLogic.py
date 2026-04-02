class Logic:
    def __init__(self, window):
        self.window = window
        self.hello_visible = False
        self.window.pushButton.clicked.connect(self.toggle_hello)

    def toggle_hello(self):
        if self.hello_visible:
            self.window.label.setText("")
        else:
            self.window.label.setText("Hello World")
        self.hello_visible = not self.hello_visible