import sys
import threading
import logging

from PyQt5.QtWidgets import QApplication
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

def main():
    db = Database()
    db.setup()

    flask_thread = threading.Thread(target=_run_flask, args=(db,), daemon=True)
    flask_thread.start()

    qt_app = QApplication(sys.argv)
    window = MainWindow(db)
    window.show()
    sys.exit(qt_app.exec_())

if __name__ == '__main__':
    main()
