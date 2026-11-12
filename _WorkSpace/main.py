import sys
import os
from PySide6.QtWidgets import QApplication
from views.main_window import MainWindow

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    
    initial_path = ""
    if len(sys.argv) > 1:
        initial_path = sys.argv[1]
        # Strip wrapping quotes if present
        if initial_path.startswith('"') and initial_path.endswith('"'):
            initial_path = initial_path[1:-1]
            
    window = MainWindow(initial_path=initial_path)
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
