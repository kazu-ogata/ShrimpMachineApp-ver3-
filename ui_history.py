import sys
import sqlite3
from PyQt5 import QtWidgets, QtGui, QtCore

COLOR_BG = "#FAF7F2"
COLOR_TEAL = "#0D3D45"

class HistoryScreen(QtWidgets.QWidget):
    def __init__(self, user_id, parent=None):
        super().__init__()
        self.user_id = user_id
        self.parent = parent  
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: {COLOR_TEAL};")
        self.init_ui()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        # Header with Back Button
        header = QtWidgets.QHBoxLayout()
        btn_back = QtWidgets.QPushButton()
        btn_back.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowLeft))
        btn_back.setIconSize(QtCore.QSize(30, 30)); btn_back.setFixedSize(50, 50)
        btn_back.setFlat(True); btn_back.clicked.connect(self.go_back)

        title = QtWidgets.QLabel("ACTIVITY HISTORY")
        title.setStyleSheet("font-size: 26px; font-weight: bold; letter-spacing: 1px; border: none;")
        
        header.addWidget(btn_back); header.addStretch(); header.addWidget(title)
        header.addStretch(); header.addSpacing(50)
        layout.addLayout(header)

        # List Widget with clean styling
        self.list_widget = QtWidgets.QListWidget()
        self.list_widget.setStyleSheet(f"""
            QListWidget {{
                background-color: white; border-radius: 20px; border: 1px solid #D1D1D1;
                padding: 15px; font-size: 18px;
            }}
            QListWidget::item {{
                padding: 20px; border-bottom: 1px solid #EEE;
            }}
            QListWidget::item:selected {{ background-color: #F0F4F4; color: {COLOR_TEAL}; border-radius: 10px; }}
        """)
        self.list_widget.itemClicked.connect(self.handle_item_click)
        layout.addWidget(self.list_widget)
        self.load_data()

    def load_data(self):
        self.list_widget.clear()
        from database import get_all_records
        records = get_all_records(self.user_id)
        
        if not records:
            self.list_widget.addItem("No previous records found.")
            return

        # Sort records by ID or Date descending (latest first)
        records.reverse()

        for r in records:
            # FIX 1: Robust Date Parsing
            # r[7] is usually the 'dateTime' column in your SQLite local.db
            raw_date = str(r[7]) 
            if "T" in raw_date or "-" in raw_date:
                # Extract Date and Time only
                clean_date = raw_date.split(".")[0].replace("T", " ")
            else:
                clean_date = "Unknown Date"

            display_text = f"DATE: {clean_date}\nCOUNT: {r[3]} pcs | FEED: {r[5]:.2f}g"
            
            item = QtWidgets.QListWidgetItem(display_text)
            item.setData(QtCore.Qt.UserRole, r) 
            self.list_widget.addItem(item)

    def handle_item_click(self, item):
        record = item.data(QtCore.Qt.UserRole)
        if not record: return

        # Format specific date for the popup header
        date_label = str(record[7]).split(".")[0].replace("T", " ")

        msg = QtWidgets.QMessageBox(self)
        msg.setWindowTitle("Options")
        msg.setText(f"Record Date: {date_label}\n\nWhat would you like to do?")
        resume_btn = msg.addButton("Resume Session", QtWidgets.QMessageBox.ActionRole)
        delete_btn = msg.addButton("Delete Record", QtWidgets.QMessageBox.DestructiveRole)
        msg.addButton("Cancel", QtWidgets.QMessageBox.RejectRole)
        
        msg.exec_()
        if msg.clickedButton() == resume_btn:
            self.parent.load_existing_session(record)
            self.go_back()
        elif msg.clickedButton() == delete_btn:
            self.delete_record(record[0])

    def delete_record(self, record_id):
        conn = sqlite3.connect('local.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM biomass_records WHERE id = ?", (record_id,))
        conn.commit(); conn.close()
        self.load_data() # Refresh the list immediately

    def go_back(self):
        self.parent.showFullScreen()
        self.close()