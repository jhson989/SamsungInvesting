from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtCore import QTimer, Qt

from collector.stock_collector import StockCollector, SAMSUNG_TICKER


class MainWindow(QMainWindow):
    def __init__(self, db):
        super().__init__()
        self.db = db
        self.collector = StockCollector(db)
        self._setup_ui()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(60_000)
        self._refresh()

    def _setup_ui(self):
        self.setWindowTitle('삼성전자 1분 주가 수집기')
        self.setMinimumSize(860, 580)

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        # ── top bar ──────────────────────────────────────────────────────────
        bar = QHBoxLayout()

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

        # ── current price ─────────────────────────────────────────────────────
        self.price_lbl = QLabel('현재가: —')
        self.price_lbl.setStyleSheet('font-size:26px; font-weight:bold; color:#c62828;')
        layout.addWidget(self.price_lbl)

        # ── table ─────────────────────────────────────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(['시간', '시가', '고가', '저가', '종가', '거래량'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)

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

    def _refresh(self):
        rows = self.db.get_latest(SAMSUNG_TICKER, 60)
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            time_str = row['datetime'][-8:]  # HH:MM:SS
            self.table.setItem(i, 0, QTableWidgetItem(time_str))
            for col, key in enumerate(['open', 'high', 'low', 'close', 'volume'], start=1):
                val = row.get(key) or 0
                text = f'{val:,}'
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, col, item)

        if rows:
            self.price_lbl.setText(f"현재가: {rows[-1]['close']:,} 원")

    def closeEvent(self, event):
        self.collector.stop()
        event.accept()
