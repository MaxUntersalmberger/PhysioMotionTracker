from PyQt5 import QtCore, QtWidgets
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QLineEdit, QLabel, QFileDialog
from PyQt5.QtCore import Qt
from pathlib import Path


# Configuratie: maximale diepte voor mappenstructuur in de tree
MAX_TREE_DEPTH = 10


class TabDirectory:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.window = logic_instance.window
        self.current_directory = None
        self.tree_widget = None
        self.path_input = None
        
    def setup(self):
        """Initialiseert de directory tab met een file explorer"""
        # Haal de huidige project locatie op
        try:
            from core.config import AppConfig
            self.app_config = AppConfig.load()
            self.current_directory = self.app_config.default_sessions_dir
        except ImportError:
            # Fallback naar de huidige werkdirectory
            self.current_directory = Path.cwd()
        
        # Maak de layout voor de frame_directory
        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(0, 0, 0, 0)
        
        # Bovenste toolbar met path en buttons
        toolbar_layout = QHBoxLayout()
        
        # Label "Huidge Pad:"
        path_label = QLabel("Huidig pad:")
        toolbar_layout.addWidget(path_label)
        
        # Input veld voor het pad
        self.path_input = QLineEdit()
        self.path_input.setText(str(self.current_directory))
        self.path_input.setReadOnly(False)
        self.path_input.returnPressed.connect(self.load_directory_from_input)
        toolbar_layout.addWidget(self.path_input)
        
        # Knop om pad te vernieuwen
        refresh_btn = QPushButton("Vernieuwen")
        refresh_btn.clicked.connect(self.refresh_directory)
        toolbar_layout.addWidget(refresh_btn)
        
        # Knop om map te kiezen via dialoog
        browse_btn = QPushButton("Bladeren...")
        browse_btn.clicked.connect(self.browse_directory)
        toolbar_layout.addWidget(browse_btn)
        
        # Knop om standaard locatie in te stellen
        set_default_btn = QPushButton("Als standaard instellen")
        set_default_btn.clicked.connect(self.set_as_default)
        toolbar_layout.addWidget(set_default_btn)
        
        frame_layout.addLayout(toolbar_layout)
        
        # File tree widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Naam", "Type", "Gewijzigd"])
        self.tree_widget.setColumnCount(3)
        self.tree_widget.setMinimumHeight(400)
        frame_layout.addWidget(self.tree_widget)
        
        # Set layout to frame_directory
        self.window.frame_directory.setLayout(frame_layout)
        
        # Laad de standaard directory
        self.load_directory(self.current_directory)
    
    def load_directory(self, directory_path):
        """Laadt de directory structuur in de tree widget"""
        directory_path = Path(directory_path)
        
        if not directory_path.exists():
            QtWidgets.QMessageBox.warning(self.window, "Fout", f"Directory niet gevonden: {directory_path}")
            return
        
        if not directory_path.is_dir():
            QtWidgets.QMessageBox.warning(self.window, "Fout", f"Pad is geen directory: {directory_path}")
            return
        
        self.current_directory = directory_path
        self.path_input.setText(str(directory_path))
        
        # Clear tree
        self.tree_widget.clear()
        
        # Voeg root item toe
        root_item = QTreeWidgetItem(self.tree_widget)
        root_item.setText(0, directory_path.name or str(directory_path))
        root_item.setData(0, Qt.UserRole, str(directory_path))
        
        # Populate tree recursively
        self._populate_tree_item(root_item, directory_path, MAX_TREE_DEPTH)
        
        # Expand root
        root_item.setExpanded(True)
    
    def _populate_tree_item(self, parent_item, directory_path, max_depth, current_depth=0):
        """Recursief vullen van tree items"""
        if current_depth >= max_depth:
            return
        
        try:
            items = sorted(directory_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item_path in items:
                # Skip hidden files on Linux/Mac
                if item_path.name.startswith('.'):
                    continue
                
                item = QTreeWidgetItem(parent_item)
                item.setText(0, item_path.name)
                item.setData(0, Qt.UserRole, str(item_path))
                
                # Type
                if item_path.is_dir():
                    item.setText(1, "Map")
                else:
                    item.setText(1, "Bestand")
                
                # Modified time
                try:
                    mod_time = item_path.stat().st_mtime
                    from datetime import datetime
                    mod_date = datetime.fromtimestamp(mod_time).strftime("%d-%m-%Y %H:%M")
                    item.setText(2, mod_date)
                except:
                    item.setText(2, "-")
                
                # Recursively populate directories
                if item_path.is_dir():
                    self._populate_tree_item(item, item_path, max_depth, current_depth + 1)
        except PermissionError:
            pass
    
    def load_directory_from_input(self):
        """Laadt directory uit het input veld"""
        path_text = self.path_input.text().strip()
        if path_text:
            self.load_directory(path_text)
    
    def refresh_directory(self):
        """Vernieuwt de huidige directory"""
        self.load_directory(self.current_directory)
    
    def browse_directory(self):
        """Opent een dialoog om een directory te kiezen"""
        selected_dir = QFileDialog.getExistingDirectory(
            self.window,
            "Selecteer een directory",
            str(self.current_directory)
        )
        if selected_dir:
            self.load_directory(selected_dir)
    
    def set_as_default(self):
        """Stelt de huidige directory in als standaard"""
        try:
            from core.config import AppConfig
            
            config = AppConfig.load()
            config.default_sessions_dir = self.current_directory
            config.save()
            
            QtWidgets.QMessageBox.information(
                self.window,
                "Succes",
                f"Standaard locatie ingesteld op:\n{self.current_directory}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.window,
                "Fout",
                f"Kon standaard locatie niet instellen:\n{str(e)}"
            )
