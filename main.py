import sys
import socket
import threading
import logging

from PyQt5 import QtWebEngineWidgets  # noqa: F401  (must import before QApplication)
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt

from database.db import Database
from gui.main_window import MainWindow
from web.server import create_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s'
)

def _run_flask(db):
    app = create_app(db)
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)

def _wait_for_server(port=5000, timeout=5.0):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.1)
    return False

def main():
    db = Database()
    db.setup()

    flask_thread = threading.Thread(target=_run_flask, args=(db,), daemon=True)
    flask_thread.start()
    _wait_for_server()

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
    qt_app = QApplication(sys.argv)
    window = MainWindow(db)
    window.show()
    sys.exit(qt_app.exec_())

if __name__ == '__main__':
    main()
