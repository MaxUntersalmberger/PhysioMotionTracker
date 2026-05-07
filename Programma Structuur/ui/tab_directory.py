from PyQt5 import QtCore, QtWidgets, QtGui
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QLineEdit, QLabel, QFileDialog, QFileIconProvider
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon
from pathlib import Path


# Configuratie: maximale diepte voor mappenstructuur in de tree
MAX_TREE_DEPTH = 10


class TabDirectory:
    def __init__(self, logic_instance):
        self.logic = logic_instance
        self.window = logic_instance.window
        self.root_directory = None
        self.tree_widget = None
        self.path_input = None
        self.icon_provider = None
        
    def setup(self):
        """Initialiseert de directory tab met een file explorer"""
        # Haal de huidige project locatie op
        try:
            from core.config import AppConfig
            self.app_config = AppConfig.load()
            self.root_directory = self.app_config.default_sessions_dir
        except ImportError:
            # Fallback naar de huidige werkdirectory
            self.root_directory = Path.cwd()
        
        # Icon provider voor bestandstypes
        self.icon_provider = QFileIconProvider()
        
        # Maak de layout voor de frame_directory
        frame_layout = QVBoxLayout()
        frame_layout.setContentsMargins(0, 0, 0, 0)
        
        # Bovenste toolbar met path en buttons
        toolbar_layout = QHBoxLayout()
        
        # Knop om omhoog te gaan
        up_btn = QPushButton("📁 ↑ Omhoog")
        up_btn.clicked.connect(self.go_up_directory)
        toolbar_layout.addWidget(up_btn)
        
        # Label "Huidig Pad:"
        path_label = QLabel("Startpad:")
        toolbar_layout.addWidget(path_label)
        
        # Input veld voor het pad
        self.path_input = QLineEdit()
        self.path_input.setText(str(self.root_directory))
        self.path_input.setReadOnly(True)
        toolbar_layout.addWidget(self.path_input)
        
        # Knop om pad te vernieuwen
        refresh_btn = QPushButton("Vernieuwen")
        refresh_btn.clicked.connect(self.refresh_directory)
        toolbar_layout.addWidget(refresh_btn)
        
        # Knop om map te kiezen via dialoog
        browse_btn = QPushButton("Bladeren...")
        browse_btn.clicked.connect(self.browse_directory)
        toolbar_layout.addWidget(browse_btn)

        
        frame_layout.addLayout(toolbar_layout)
        
        # File tree widget
        self.tree_widget = QTreeWidget()
        self.tree_widget.setHeaderLabels(["Naam", "Type", "Gewijzigd"])
        self.tree_widget.setColumnCount(3)
        self.tree_widget.setMinimumHeight(400)
        # Verbind expand event voor lazy loading
        self.tree_widget.itemExpanded.connect(self.on_tree_item_expanded)
        frame_layout.addWidget(self.tree_widget)
        
        # Set layout to frame_directory
        self.window.frame_directory.setLayout(frame_layout)
        
        # Laad de standaard directory
        self.load_root_directory(self.root_directory)
    
    def load_root_directory(self, directory_path):
        """Laadt de directory structuur in de tree widget met lazy loading"""
        directory_path = Path(directory_path)
        
        if not directory_path.exists():
            QtWidgets.QMessageBox.warning(self.window, "Fout", f"Directory niet gevonden: {directory_path}")
            return
        
        if not directory_path.is_dir():
            QtWidgets.QMessageBox.warning(self.window, "Fout", f"Pad is geen directory: {directory_path}")
            return
        
        self.root_directory = directory_path
        self.path_input.setText(str(directory_path))
        
        # Clear tree
        self.tree_widget.clear()
        
        # Voeg root item toe
        root_item = QTreeWidgetItem(self.tree_widget)
        root_item.setText(0, directory_path.name or str(directory_path))
        root_item.setData(0, Qt.UserRole, str(directory_path))
        
        # Icon voor root
        icon = self.icon_provider.icon(QFileIconProvider.Folder)
        root_item.setIcon(0, icon)
        root_item.setText(1, "Map")
        
        # Laad direct één niveau (lazy loading voor rest)
        self._populate_tree_item_lazy(root_item, directory_path, 1)
        
        # Expand root
        root_item.setExpanded(True)
    
    def _populate_tree_item_lazy(self, parent_item, directory_path, depth_level):
        """Laadt items met lazy loading - volgende level wordt geladen wanneer item wordt uitgeklapt"""
        # Wis eerst dummy items als die bestaan
        while parent_item.childCount() > 0:
            parent_item.removeChild(parent_item.child(0))
        
        try:
            items = sorted(directory_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item_path in items:
                # Skip hidden files
                if item_path.name.startswith('.'):
                    continue
                
                item = QTreeWidgetItem(parent_item)
                item.setText(0, item_path.name)
                item.setData(0, Qt.UserRole, str(item_path))
                
                # Voeg icon toe gebaseerd op bestandstype
                if item_path.is_dir():
                    icon = self.icon_provider.icon(QFileIconProvider.Folder)
                    item.setText(1, "Map")
                else:
                    icon = self.icon_provider.icon(item_path)
                    item.setText(1, "Bestand")
                
                item.setIcon(0, icon)
                
                # Modified time
                try:
                    mod_time = item_path.stat().st_mtime
                    from datetime import datetime
                    mod_date = datetime.fromtimestamp(mod_time).strftime("%d-%m-%Y %H:%M")
                    item.setText(2, mod_date)
                except:
                    item.setText(2, "-")
                
                # Als het een map is en we nog niet op max depth zijn, voeg een dummy child toe
                if item_path.is_dir() and depth_level < MAX_TREE_DEPTH:
                    # Voeg dummy item toe zodat pijltje verschijnt
                    dummy = QTreeWidgetItem(item)
                    dummy.setText(0, "Laden...")
                    item.setData(0, Qt.UserRole + 1, False)  # Mark as not loaded
                    
        except PermissionError:
            pass
    
    def on_tree_item_expanded(self, item):
        """Wordt aangeroepen wanneer een item wordt uitgeklapt - laadt submappen"""
        item_path_str = item.data(0, Qt.UserRole)
        if not item_path_str:
            return
        
        item_path = Path(item_path_str)
        
        # Check if already loaded
        if item.data(0, Qt.UserRole + 1) is False:
            # Laad de submappen
            self._populate_tree_item_lazy(item, item_path, self._get_depth_level(item) + 1)
    
    def _get_depth_level(self, item):
        """Bepaal de depth level van een tree item"""
        depth = 0
        current = item
        while current.parent() is not None:
            depth += 1
            current = current.parent()
        return depth
    
    def go_up_directory(self):
        """Gaat één niveau omhoog in de directory structuur"""
        parent_path = self.root_directory.parent
        
        if parent_path != self.root_directory:
            self.load_root_directory(parent_path)
        else:
            QtWidgets.QMessageBox.information(
                self.window,
                "Info",
                "U bent al in de root directory"
            )
    
    def load_directory_from_input(self):
        """Laadt directory uit het input veld"""
        path_text = self.path_input.text().strip()
        if path_text:
            self.load_root_directory(path_text)
    
    def refresh_directory(self):
        """Vernieuwt de huidige directory"""
        self.load_root_directory(self.root_directory)
    
    def browse_directory(self):
        """Opent een dialoog om een directory te kiezen"""
        selected_dir = QFileDialog.getExistingDirectory(
            self.window,
            "Selecteer een directory",
            str(self.root_directory)
        )
        if selected_dir:
            self.load_root_directory(selected_dir)
    
    def set_as_default(self):
        """Stelt de huidige directory in als standaard"""
        try:
            from core.config import AppConfig
            
            config = AppConfig.load()
            config.default_sessions_dir = self.root_directory
            config.save()
            
            QtWidgets.QMessageBox.information(
                self.window,
                "Succes",
                f"Standaard locatie ingesteld op:\n{self.root_directory}"
            )
        except Exception as e:
            QtWidgets.QMessageBox.critical(
                self.window,
                "Fout",
                f"Kon standaard locatie niet instellen:\n{str(e)}"
            )
