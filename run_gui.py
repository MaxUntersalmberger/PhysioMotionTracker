#!/usr/bin/env python3
"""
PhysioMotionTracker GUI Launcher
Starts the GUI application with proper path setup and error handling
"""
import sys
import traceback
from pathlib import Path

# Setup the path to find calibration_app package
calibratie_path = Path(__file__).parent / "Calibratie Programma"
sys.path.insert(0, str(calibratie_path))

print(f"Python version: {sys.version}")
print(f"Working directory: {Path.cwd()}")
print(f"Added to sys.path: {calibratie_path}")

try:
    print("\n1. Importing PyQt5...")
    from PyQt5.QtWidgets import QApplication
    print("   ✓ PyQt5 imported")
    
    print("\n2. Importing calibration_app.ui.guiMain...")
    from calibration_app.ui.guiMain import MainWindow
    print("   ✓ MainWindow imported")
    
    print("\n3. Creating QApplication...")
    app = QApplication(sys.argv)
    print("   ✓ QApplication created")
    
    print("\n4. Creating and showing MainWindow...")
    window = MainWindow()
    window.showMaximized()
    print("   ✓ MainWindow displayed")
    
    print("\n5. Starting event loop...")
    print("   (GUI is now running. Close the window to exit.)\n")
    
    exit_code = app.exec_()
    print(f"\nGUI closed with exit code: {exit_code}")
    sys.exit(exit_code)
    
except Exception as e:
    print(f"\n✗ ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)
