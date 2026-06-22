from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
)
from PyQt5.QtCore import QUrl, QTimer
from PyQt5.QtWebEngineWidgets import QWebEngineView

from collector.stock_collector import StockCollector

DASHBOARD_URL = 'http://localhost:5000/'


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.collector = StockCollector(db)
        self._setup_ui()

    def _setup_ui(self):
        self.setWindowTitle('삼성전자 1분 주가 수집기')
        self.setMinimumSize(860, 580)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── native control bar (collector start/stop) ────────────────────────
        bar = QHBoxLayout()
        bar.setContentsMargins(12, 8, 12, 8)

        self.status_lbl = QLabel('중지됨')
        self.status_lbl.setStyleSheet('font-size:13px; font-weight:bold; color:gray;')

        self.toggle_btn = QPushButton('수집 시작')
        self.toggle_btn.setFixedWidth(110)
        self.toggle_btn.clicked.connect(self._toggle)

        web_lbl = QLabel('웹 대시보드: http://localhost:5000')
        web_lbl.setStyleSheet('color:#555; font-size:12px;')

        bar.addWidget(self.status_lbl)
        bar.addStretch()
        bar.addWidget(web_lbl)
        bar.addWidget(self.toggle_btn)
        layout.addLayout(bar)

        # ── shared dashboard (same HTML the browser sees) ────────────────────
        self.web_view = QWebEngineView()
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.load(QUrl(DASHBOARD_URL))
        layout.addWidget(self.web_view)

    def _on_load_finished(self, ok):
        # Retry once shortly if the view loaded before Flask was ready.
        if not ok:
            QTimer.singleShot(500, lambda: self.web_view.load(QUrl(DASHBOARD_URL)))

    def _toggle(self):
        if self.collector.running:
            self.collector.stop()
            self.toggle_btn.setText('수집 시작')
            self.status_lbl.setText('중지됨')
            self.status_lbl.setStyleSheet('font-size:13px; font-weight:bold; color:gray;')
        else:
            self.collector.start()
            self.toggle_btn.setText('수집 중지')
            self.status_lbl.setText('수집 중…')
            self.status_lbl.setStyleSheet('font-size:13px; font-weight:bold; color:green;')

    def closeEvent(self, event):
        self.collector.stop()
        event.accept()
