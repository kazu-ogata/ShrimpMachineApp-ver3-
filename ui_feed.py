import sys
from PyQt5 import QtWidgets, QtGui, QtCore
from compute import compute_feed
from database import get_all_records
from ui_history import HistoryScreen
from mqtt_client import MqttClient

COLOR_BG = "#FAF7F2"
COLOR_TEAL = "#0D3D45"
COLOR_AQUA = "#2A9D8F"
COLOR_NEUTRAL = "#E0E0E0"

class FeedRecommendationWindow(QtWidgets.QWidget):
    def __init__(self, user_id, initial_count, parent=None):
        super().__init__()
        self.user_id = user_id
        self.parent = parent
        self.current_count = initial_count
        
        # --- MQTT INITIALIZATION ---
        self.mqtt = MqttClient()
        self.mqtt.connect()
        
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: {COLOR_TEAL};")
        self.init_ui()
        self.update_calculations()

    def init_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(30, 20, 30, 30)

        # --- HEADER ---
        header = QtWidgets.QHBoxLayout()
        self.btn_back = QtWidgets.QPushButton()
        self.btn_back.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowLeft))
        self.btn_back.setIconSize(QtCore.QSize(35, 35))
        self.btn_back.setFixedSize(50, 50)
        self.btn_back.setFlat(True)
        self.btn_back.clicked.connect(self.go_back)

        lbl_title = QtWidgets.QLabel("FEED RECOMMENDATION")
        lbl_title.setStyleSheet("font-size: 28px; font-weight: 900; letter-spacing: 2px; border: none;")
        lbl_title.setAlignment(QtCore.Qt.AlignCenter)

        header.addWidget(self.btn_back)
        header.addStretch()
        header.addWidget(lbl_title)
        header.addStretch()
        header.addSpacing(50)
        layout.addLayout(header)

        # --- DATA CARD ---
        data_card = QtWidgets.QFrame()
        data_card.setStyleSheet(f"background: white; border-radius: 20px; border: 1px solid {COLOR_NEUTRAL};")
        card_layout = QtWidgets.QGridLayout(data_card)

        self.lbl_count = QtWidgets.QLabel(f"COUNT: {self.current_count}")
        self.lbl_count.setStyleSheet("font-size: 24px; font-weight: bold; border: none;")
        
        self.btn_edit_count = QtWidgets.QPushButton("NEW")
        self.btn_edit_count.setFixedSize(80, 40)
        self.btn_edit_count.setStyleSheet(f"background: {COLOR_TEAL}; color: white; border-radius: 8px; border: none;")
        self.btn_edit_count.setVisible(False) 
        self.btn_edit_count.clicked.connect(self.edit_manual_count)

        self.lbl_biomass = QtWidgets.QLabel("BIOMASS: 0.0000g")
        self.lbl_biomass.setStyleSheet("font-size: 18px; border: none; color: #444; background: transparent;")
        
        self.lbl_feed_day = QtWidgets.QLabel("FEED PER DAY: 0.00g")
        self.lbl_feed_day.setStyleSheet("font-size: 18px; border: none; color: #444; background: transparent;")
        
        self.btn_dispense_total = QtWidgets.QPushButton("DISPENSE TOTAL")
        self.btn_dispense_total.setFixedSize(160, 45)
        self.btn_dispense_total.setStyleSheet(f"background: {COLOR_TEAL}; color: white; border-radius: 10px; border: none;")
        self.btn_dispense_total.clicked.connect(self.dispense_daily_total)

        card_layout.addWidget(self.lbl_count, 0, 0)
        card_layout.addWidget(self.btn_edit_count, 0, 1)
        card_layout.addWidget(self.lbl_biomass, 1, 0)
        card_layout.addWidget(self.lbl_feed_day, 2, 0)
        card_layout.addWidget(self.btn_dispense_total, 2, 1)
        layout.addWidget(data_card)

        # --- SCHEDULE SECTION ---
        layout.addSpacing(10)
        lbl_sched_title = QtWidgets.QLabel("SCHEDULED FEEDING DISTRIBUTION")
        lbl_sched_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #0D3D45; border: none;")
        layout.addWidget(lbl_sched_title, alignment=QtCore.Qt.AlignLeft)
        
        self.schedule_labels = {}
        self.schedule_btns = {}
        for t in ["6am", "10am", "2pm", "6pm", "10pm"]:
            row = QtWidgets.QHBoxLayout()
            lbl = QtWidgets.QLabel(f"{t}: 0.00g")
            lbl.setStyleSheet("font-size: 16px; font-weight: bold; border: none;")
            
            btn = QtWidgets.QPushButton("DISPENSE")
            btn.setFixedSize(140, 35)
            btn.setStyleSheet(f"background: {COLOR_TEAL}; color: white; border-radius: 8px; border: none;")
            btn.clicked.connect(lambda ch, s=t: self.dispense_slot(s))
            
            self.schedule_labels[t] = lbl
            self.schedule_btns[t] = btn
            
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(btn)
            layout.addLayout(row)

        self.lbl_status = QtWidgets.QLabel("STATUS: IDLE")
        self.lbl_status.setStyleSheet(f"color: {COLOR_AQUA}; font-weight: bold; border: none;")
        layout.addWidget(self.lbl_status)

        # --- FOOTER BUTTONS ---
        footer = QtWidgets.QHBoxLayout()
        for name in ["NEW", "RESET", "SAVE", "HISTORY"]:
            btn = QtWidgets.QPushButton(name)
            btn.setFixedHeight(50)
            btn.setStyleSheet(f"background: {COLOR_TEAL}; color: white; border-radius: 10px; font-weight: bold; border: none;")
            if name == "NEW": btn.clicked.connect(self.enable_edit_mode)
            if name == "RESET": btn.clicked.connect(self.reset_schedule)
            if name == "SAVE": btn.clicked.connect(self.save_current_state)
            if name == "HISTORY": btn.clicked.connect(self.show_history)
            footer.addWidget(btn)
        layout.addLayout(footer)

    def update_calculations(self):
        """Updates the internal calculations and UI text only."""
        b, f_day, portion = compute_feed(self.current_count)
        self.lbl_count.setText(f"COUNT: {self.current_count}") 
        self.lbl_biomass.setText(f"BIOMASS: {b:.4f}g")
        self.lbl_feed_day.setText(f"FEED PER DAY: {f_day:.4f}g")
        for t, lbl in self.schedule_labels.items():
            lbl.setText(f"{t}: {portion:.4f}g")

    def dispense_daily_total(self):
        """Dispenses the full daily amount based on weight feedback."""
        b, f_day, portion = compute_feed(self.current_count)
        
        self.btn_dispense_total.setEnabled(False)
        self.btn_dispense_total.setStyleSheet(f"background: {COLOR_NEUTRAL}; color: #888; border-radius: 10px; border: none;")
        for btn in self.schedule_btns.values():
            btn.setEnabled(False)
            btn.setStyleSheet(f"background: {COLOR_NEUTRAL}; color: #888; border-radius: 8px; border: none;")
        
        # SEND TARGET WEIGHT TO DISPENSER
        self.mqtt.publish("shrimp/dispenser/target", str(round(f_day, 2)))
        self.lbl_status.setText(f"STATUS: DISPENSING DAILY TOTAL ({f_day:.4f}g)")

    def show_history(self):
        self.history_win = HistoryScreen(self.user_id, self)
        self.history_win.showFullScreen()

    def load_existing_session(self, record):
        self.current_count = record[3]
        self.update_calculations()
        if len(record) > 8 and record[8]:
            dispensed_slots = record[8].split(",")
            for slot in dispensed_slots:
                if slot in self.schedule_btns:
                    self.schedule_btns[slot].setEnabled(False)
                    self.schedule_btns[slot].setStyleSheet(f"background: {COLOR_NEUTRAL}; color: #888; border-radius: 8px; border: none;")
        self.lbl_status.setText(f"STATUS: RESUMED SESSION")

    def enable_edit_mode(self): 
        self.btn_edit_count.setVisible(True)

    def edit_manual_count(self):
        from ui_biomass import NumberInputDialog
        dialog = NumberInputDialog(self)
        if dialog.exec_():
            self.current_count = dialog.get_number()
            self.update_calculations()
            self.btn_edit_count.setVisible(False)

    def dispense_slot(self, slot):
        """Dispenses for a specific slot and saves the state immediately."""
        self.schedule_btns[slot].setEnabled(False)
        self.schedule_btns[slot].setStyleSheet(f"background: {COLOR_NEUTRAL}; color: #888; border-radius: 8px; border: none;")
        
        # 1. Calculate Target
        b, f_day, portion = compute_feed(self.current_count)
        
        # 2. Publish target weight to the correct topic
        self.mqtt.publish("shrimp/dispenser/target", str(round(portion, 2)))
        self.lbl_status.setText(f"STATUS: DISPENSING {slot.upper()} ({portion:.4f}g)")
        
        # 3. Persistence Logic
        dispensed_list = [t for t, btn in self.schedule_btns.items() if not btn.isEnabled()]
        slots_str = ",".join(dispensed_list)
        
        from database import get_last_record, update_dispense_status
        last_rec = get_last_record(self.user_id)
        if last_rec:
            update_dispense_status(last_rec[0], slots_str)

    def save_current_state(self):
        dispensed = [t for t, btn in self.schedule_btns.items() if not btn.isEnabled()]
        slots_str = ",".join(dispensed)
        from database import get_last_record, update_dispense_status
        last_rec = get_last_record(self.user_id)
        if last_rec:
            update_dispense_status(last_rec[0], slots_str)
            self.lbl_status.setText("STATUS: PROGRESS SAVED")
            QtWidgets.QMessageBox.information(self, "Saved", "Feeding progress has been saved.")
        else:
            self.lbl_status.setText("STATUS: NO RECORD TO UPDATE")

    def reset_schedule(self):
        self.btn_dispense_total.setEnabled(True)
        self.btn_dispense_total.setStyleSheet(f"background: {COLOR_TEAL}; color: white; border-radius: 10px; border: none;")
        for btn in self.schedule_btns.values():
            btn.setEnabled(True)
            btn.setStyleSheet(f"background: {COLOR_TEAL}; color: white; border-radius: 8px; border: none;")
        self.btn_edit_count.setVisible(False)
        self.lbl_status.setText("STATUS: RESET")

    def go_back(self): 
        self.mqtt.disconnect() 
        self.parent.showFullScreen()
        self.parent.show()
        self.close()