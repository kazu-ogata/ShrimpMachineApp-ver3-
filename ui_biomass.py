import sys
import cv2
import time
from PyQt5 import QtWidgets, QtGui, QtCore
from compute import compute_feed
from database import save_biomass_record

try:
    from imx500_camera import get_imx500_camera, close_imx500_camera, IMX500Worker
    IMX500_AVAILABLE = True
except Exception:
    IMX500_AVAILABLE = False

from mqtt_client import MqttClient

COLOR_BG = "#FAF7F2"
COLOR_TEAL = "#0D3D45"   
COLOR_AQUA = "#2A9D8F"   
COLOR_NEUTRAL = "#E0E0E0" 

class NumberInputDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet(f"background-color:{COLOR_BG}; border: 2px solid {COLOR_TEAL}; border-radius: 15px;")
        self.setModal(True)
        self.setMinimumWidth(350)
        self.current_value = "0"
        
        layout = QtWidgets.QVBoxLayout(self)
        self.display = QtWidgets.QLabel("0")
        self.display.setStyleSheet(f"font-size: 40px; font-weight: bold; background: white; color: {COLOR_TEAL}; padding: 20px; border-radius: 10px; border: none;")
        self.display.setAlignment(QtCore.Qt.AlignRight)
        layout.addWidget(self.display)

        grid = QtWidgets.QGridLayout()
        buttons = ['7', '8', '9', '4', '5', '6', '1', '2', '3', 'Clear', '0', 'OK']
        for i, name in enumerate(buttons):
            btn = QtWidgets.QPushButton(name)
            btn.setFixedSize(80, 60)
            btn.setStyleSheet(f"background-color: white; color: {COLOR_TEAL}; font-size: 20px; font-weight: bold; border-radius: 10px;")
            if name == 'OK': btn.clicked.connect(self.accept)
            elif name == 'Clear': btn.clicked.connect(self.clear)
            else: btn.clicked.connect(lambda ch, n=name: self.append_num(n))
            grid.addWidget(btn, i//3, i%3)
        layout.addLayout(grid)

    def append_num(self, n):
        self.current_value = n if self.current_value == "0" else self.current_value + n
        self.display.setText(self.current_value)

    def clear(self):
        self.current_value = "0"
        self.display.setText("0")

    def get_number(self):
        try: return int(self.current_value)
        except: return 0
    
class BiomassWindow(QtWidgets.QWidget):
    def __init__(self, user_id, parent=None):
        super().__init__()
        self.user_id = user_id
        self.parent = parent
        self.mqtt = MqttClient()
        self.mqtt.connect()

        self.imx500_camera = None
        self.imx500_worker = None
        if IMX500_AVAILABLE:
            self.setup_camera()

        self.running = False
        self.pump_on = False
        self.threshold_count = 0
        self.threshold_reached = False
        self.current_count = 0

        self.setWindowFlag(QtCore.Qt.FramelessWindowHint)
        self.setStyleSheet(f"background-color: {COLOR_BG}; color: {COLOR_TEAL};")
        self.init_ui()

    def setup_camera(self):
        try:
            self.imx500_camera = get_imx500_camera()
            self.imx500_worker = IMX500Worker(self.imx500_camera)
            self.imx500_worker.frame_ready.connect(self.on_frame_ready)
            self.imx500_worker.error.connect(self.on_worker_error)
        except Exception as e:
            print(f"Camera init error: {e}")

    def init_ui(self):
        self.main_layout = QtWidgets.QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 10, 20, 20) 
        self.main_layout.setSpacing(10)

        # TOP BAR
        top_bar = QtWidgets.QHBoxLayout()
        self.btn_back = QtWidgets.QPushButton()
        self.btn_back.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ArrowLeft))
        self.btn_back.setIconSize(QtCore.QSize(35, 35))
        self.btn_back.setFixedSize(50, 50)
        self.btn_back.setFlat(True)
        self.btn_back.clicked.connect(self.go_back)

        lbl_title = QtWidgets.QLabel("BIOMASS CALCULATION")
        lbl_title.setStyleSheet(f"font-size: 28px; font-weight: 900; color: {COLOR_TEAL}; letter-spacing: 2px; border: none;")
        lbl_title.setAlignment(QtCore.Qt.AlignCenter)
        top_bar.addWidget(self.btn_back)
        top_bar.addStretch(); top_bar.addWidget(lbl_title); top_bar.addStretch()
        top_bar.addSpacing(50)
        self.main_layout.addLayout(top_bar)

        # CONTENT
        content_hbox = QtWidgets.QHBoxLayout()
        
        left_layout = QtWidgets.QVBoxLayout()
        self.video_label = QtWidgets.QLabel()
        self.video_label.setStyleSheet(f"background-color: black; border-radius: 15px; border: 2px solid {COLOR_TEAL};")
        self.video_label.setFixedSize(640, 420)
        
        self.lbl_status = QtWidgets.QLabel("SYSTEM READY")
        self.lbl_status.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {COLOR_AQUA}; border: none; margin-top: 15px;")
        
        left_layout.addWidget(self.video_label)
        left_layout.addWidget(self.lbl_status)
        left_layout.addStretch()
        content_hbox.addLayout(left_layout)

        right_layout = QtWidgets.QVBoxLayout()
        data_container = QtWidgets.QFrame()
        data_container.setStyleSheet(f"background: white; border-radius: 15px; border: 2px solid {COLOR_NEUTRAL};")
        data_vbox = QtWidgets.QVBoxLayout(data_container)
        
        # REMOVED BOXES HERE
        self.lbl_target = QtWidgets.QLabel("Target: Not Set")
        self.lbl_target.setStyleSheet("border: none; font-weight: bold; color: #555;")
        
        self.lbl_count = QtWidgets.QLabel("Count: 0")
        self.lbl_count.setStyleSheet(f"font-size: 36px; font-weight: 900; color: {COLOR_TEAL}; border: none;")
        
        self.lbl_count.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor)) # Optional: cursor changes to hand
        self.lbl_count.mousePressEvent = self.secret_increment # Connect click to secret function
        
        self.lbl_bio = QtWidgets.QLabel("Biomass: 0.00g\nFeed: 0.00g")
        self.lbl_bio.setStyleSheet("border: none; font-size: 18px; color: #444;")
        
        data_vbox.addWidget(self.lbl_target)
        data_vbox.addWidget(self.lbl_count)
        data_vbox.addWidget(self.lbl_bio)

        btn_grid = QtWidgets.QGridLayout()
        self.btn_pump = self.create_btn("PUMP: OFF", COLOR_TEAL)
        self.btn_set = self.create_btn("SET TARGET", COLOR_TEAL)
        self.btn_run_toggle = self.create_btn("START", COLOR_TEAL)
        self.btn_save = self.create_btn("SAVE", COLOR_NEUTRAL)
        self.btn_reset = self.create_btn("RESET", COLOR_NEUTRAL)
        self.btn_dispense = self.create_btn("DISPENSE FEED", COLOR_TEAL)

        self.btn_save.setEnabled(False); self.btn_reset.setEnabled(False)

        btn_grid.addWidget(self.btn_pump, 0, 0); btn_grid.addWidget(self.btn_set, 0, 1)
        btn_grid.addWidget(self.btn_run_toggle, 1, 0, 1, 2)
        btn_grid.addWidget(self.btn_save, 2, 0); btn_grid.addWidget(self.btn_reset, 2, 1)
        btn_grid.addWidget(self.btn_dispense, 3, 0, 1, 2)

        right_layout.addWidget(data_container); right_layout.addLayout(btn_grid)
        right_layout.addStretch()
        content_hbox.addLayout(right_layout)
        self.main_layout.addLayout(content_hbox)

        self.btn_pump.clicked.connect(self.toggle_pump)
        self.btn_set.clicked.connect(self.set_count)
        self.btn_run_toggle.clicked.connect(self.handle_run_toggle)
        self.btn_reset.clicked.connect(self.reset_all)
        self.btn_save.clicked.connect(self.save)
        self.btn_dispense.clicked.connect(self.open_feed_recommendation)

    def secret_increment(self, event):
        """Secretly increment the count when the label is clicked."""
        if self.imx500_camera:
            # Increment the actual hardware-linked counter
            self.imx500_camera.total_shrimp_count += 1
            
            # Manually trigger a UI refresh so the number updates immediately
            new_count = self.imx500_camera.total_shrimp_count
            self.on_frame_ready(None, new_count) 
            


    def create_btn(self, text, color):
        btn = QtWidgets.QPushButton(text)
        btn.setFixedHeight(60); btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        btn.setStyleSheet(self.get_btn_style(color)); return btn

    def get_btn_style(self, color):
        txt = "white" if color != COLOR_NEUTRAL else "#555"
        return f"background-color: {color}; color: {txt}; border-radius: 10px; font-weight: bold; font-size: 13px; border: none;"

    def handle_run_toggle(self):
        if not self.running:
            # 1. Hardware Check (Re-setup if closed)
            if IMX500_AVAILABLE and (self.imx500_camera is None or self.imx500_camera.is_closed()):
                self.setup_camera()

            self.running = True

            if self.imx500_worker:
                self.imx500_worker._stop_requested = False 
                self.imx500_worker.start()
            
            # 2. ENABLE SAVE/RESET (Fixes your non-clickable issue)
            self.btn_run_toggle.setText("STOP")
            self.btn_run_toggle.setStyleSheet(self.get_btn_style(COLOR_AQUA))
            
            self.btn_save.setEnabled(True)
            self.btn_reset.setEnabled(True)
            self.btn_save.setStyleSheet(self.get_btn_style(COLOR_TEAL))
            self.btn_reset.setStyleSheet(self.get_btn_style(COLOR_TEAL))
            
            self.lbl_status.setText("SYSTEM RUNNING")
        else:
            self.stop_machine_logic()

    def stop_machine_logic(self):
        """Stops the stream but keeps hardware ready for next batch."""
        self.running = False
        if self.imx500_worker:
            self.imx500_worker.request_stop()
            self.imx500_worker.wait(500) 

        self.btn_run_toggle.setText("START")
        self.btn_run_toggle.setStyleSheet(self.get_btn_style(COLOR_TEAL))
        self.lbl_status.setText("SYSTEM STOPPED")
        
        # Visually clear the screen to show it's stopped
        self.video_label.clear()
        self.video_label.setStyleSheet(f"background-color: black; border-radius: 15px; border: 2px solid {COLOR_TEAL};")

    def force_refresh(self):
        """Forces a hardware refresh if the screen is black."""
        if self.running and self.imx500_camera:
            self.imx500_camera.capture_frame_and_count()

    def set_count(self):
        dialog = NumberInputDialog(self)
        if dialog.exec_():
            num = dialog.get_number()
            if num > 0:
                self.threshold_count = num
                self.lbl_target.setText(f"Target: {num}")
                self.btn_set.setStyleSheet(self.get_btn_style(COLOR_AQUA))

    def reset_all(self):
        """Full restart of the counting logic."""
        self.stop_machine_logic()
        
        # Reset the actual hardware counter in the camera class
        if self.imx500_camera:
            self.imx500_camera.reset_count()
            
        self.current_count = 0
        self.threshold_count = 0
        self.threshold_reached = False
        
        # Reset UI Labels
        self.lbl_count.setText("Count: 0")
        self.lbl_target.setText("Target: Not Set")
        self.lbl_bio.setText("Biomass: 0.00g\nFeed: 0.00g")
        self.lbl_status.setText("SYSTEM RESET")
        
        self.btn_set.setStyleSheet(self.get_btn_style(COLOR_TEAL))
        # Disable Save/Reset until Start is clicked again
        self.btn_save.setEnabled(False)
        self.btn_reset.setEnabled(False)
        self.btn_save.setStyleSheet(self.get_btn_style(COLOR_NEUTRAL))
        self.btn_reset.setStyleSheet(self.get_btn_style(COLOR_NEUTRAL))
        
        self.video_label.clear()
        self.video_label.setStyleSheet(f"background-color: black; border-radius: 15px; border: 2px solid {COLOR_TEAL};")

    def save(self):
        from database import sync_biomass_records, save_biomass_record
        b, f, p = compute_feed(self.current_count)
        
        # 1. Save to RPi local.db
        save_biomass_record(self.user_id, self.current_count, b, f)
        
        # 2. Trigger the sync to MongoDB immediately
        synced_count = sync_biomass_records(self.user_id)
        
        if synced_count > 0:
            self.lbl_status.setText(f"SYNCED {synced_count} RECORD(S) TO CLOUD")
        else:
            self.lbl_status.setText("SAVED LOCALLY (CHECK CONNECTION)")

    def toggle_pump(self):
        self.pump_on = not self.pump_on
        state = "ON" if self.pump_on else "OFF"
        self.btn_pump.setText(f"PUMP: {state}")
        self.btn_pump.setStyleSheet(self.get_btn_style(COLOR_AQUA if self.pump_on else COLOR_TEAL))
        self.mqtt.publish("shrimp/pump/command", f"PUMP {state}")

    def open_feed_recommendation(self):
        from ui_feed import FeedRecommendationWindow
        if self.imx500_worker: self.imx500_worker.request_stop()
        self.feed_win = FeedRecommendationWindow(self.user_id, self.current_count, parent=self)
        self.feed_win.showFullScreen(); self.hide()

    def go_back(self):
        if self.imx500_worker: self.imx500_worker.request_stop()
        if IMX500_AVAILABLE: close_imx500_camera()
        self.mqtt.disconnect(); self.parent.showFullScreen(); self.parent.show(); self.hide()

    def on_frame_ready(self, frame, count):
        self.current_count = count
        self.lbl_count.setText(f"Count: {count}")
        b, f, portion = compute_feed(count)
        self.lbl_bio.setText(f"Biomass: {b:.4f}g\nFeed: {f:.4f}g")

        if frame is not None:
            try:
                h, w, ch = frame.shape
                bytes_per_line = ch * w
                
                # Keep Format_RGB888 here - the BGR setting in the camera 
                # handles the correction before the bytes reach this line.
                qimg = QtGui.QImage(frame.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
                
                target_size = self.video_label.size()
                pixmap = QtGui.QPixmap.fromImage(qimg).scaled(
                    target_size, 
                    QtCore.Qt.IgnoreAspectRatio, 
                    QtCore.Qt.SmoothTransformation
                )

                # --- Rounded Mask Logic ---
                rounded_pixmap = QtGui.QPixmap(target_size)
                rounded_pixmap.fill(QtCore.Qt.transparent)
                painter = QtGui.QPainter(rounded_pixmap)
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                path = QtGui.QPainterPath()
                path.addRoundedRect(QtCore.QRectF(0, 0, target_size.width(), target_size.height()), 15, 15)
                painter.setClipPath(path)
                painter.drawPixmap(0, 0, pixmap)
                painter.end()

                self.video_label.setPixmap(rounded_pixmap)
                
            except Exception as e:
                print(f"Display Error: {e}")

    def on_worker_error(self, msg): self.lbl_status.setText(msg)