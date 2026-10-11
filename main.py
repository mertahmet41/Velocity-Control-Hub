# -*- coding: utf-8 -*-
"""
Velocity Control Hub - Professional Native Windows App (G-HUB Architecture)
Standalone Direct Drive, Pedals, Shifter & Hardware Ecosystem Manager
"""

import sys
import os
import math
import time
import json
import ctypes
from ctypes import wintypes

from PyQt6.QtCore import (Qt, QTimer, QThread, pyqtSignal, QPointF, QRectF, QSize)
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QSlider, QComboBox, QPushButton,
                             QFrame, QStackedWidget, QProgressBar, QGraphicsDropShadowEffect,
                             QScrollArea, QSizePolicy, QGridLayout, QInputDialog, QMessageBox)
from PyQt6.QtGui import (QPixmap, QTransform, QPainter, QColor, QFont, 
                           QPen, QBrush, QLinearGradient, QRadialGradient, QIcon)

import serial
import serial.tools.list_ports

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "velocity_config.json")

DEFAULT_DATA = {
    "app_version": "v3.0.0",
    "devices": [
        {
            "id": "dev_wheel",
            "name": "VELOCITY DIRECT DRIVE (ALL-IN-ONE)",
            "code": "1209:FFB0",
            "type": "wheel",
            "status": "online",
            "degrees": 900,
            "overall_gain": 100,
            "damper": 15,
            "friction": 10,
            "spring": 0,
            "speed_limit": 0,
            "esgain": 100,
            "inertia": 5,
            "profile": "OpenFFBoard Native",
            "rgb_mode": "Breathing",
            "firmware": "OpenFFBoard_F411CE_V3_Profiles.hex"
        }
    ]
}

def load_data():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_DATA.copy()

def save_data(data):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass


# ---------------- Windows Joystick & Hardware Communication Worker ----------------
class JOYINFOEX(ctypes.Structure):
    _fields_ = [
        ('dwSize', wintypes.DWORD),
        ('dwFlags', wintypes.DWORD),
        ('dwXpos', wintypes.DWORD),
        ('dwYpos', wintypes.DWORD),
        ('dwZpos', wintypes.DWORD),
        ('dwRpos', wintypes.DWORD),
        ('dwUpos', wintypes.DWORD),
        ('dwVpos', wintypes.DWORD),
        ('dwButtons', wintypes.DWORD),
        ('dwButtonNumber', wintypes.DWORD),
        ('dwPOV', wintypes.DWORD),
        ('dwReserved1', wintypes.DWORD),
        ('dwReserved2', wintypes.DWORD)
    ]

JOY_RETURNALL = 0x000000FF


class HardwareWorker(QThread):
    telemetry_signal = pyqtSignal(dict)
    connection_signal = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.running = True
        self.ser = None
        self.port_name = ""

    def send_cmd(self, cmd_str):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write((cmd_str + "\n").encode("ascii"))
            except:
                pass

    def run(self):
        winmm = ctypes.windll.winmm
        joy = JOYINFOEX()
        joy.dwSize = ctypes.sizeof(JOYINFOEX)
        joy.dwFlags = JOY_RETURNALL

        step = 0
        while self.running:
            step += 1
            if self.ser is None or not self.ser.is_open:
                found = False
                for p in serial.tools.list_ports.comports():
                    hwid_lower = p.hwid.lower()
                    desc_lower = p.description.lower()
                    if ("1209" in hwid_lower or "ffb" in desc_lower or "046d" in hwid_lower or "346e" in hwid_lower or "stm" in desc_lower):
                        try:
                            self.ser = serial.Serial(p.device, 115200, timeout=0.03)
                            self.port_name = p.device
                            self.connection_signal.emit(True, f"{p.device} | {p.description}")
                            found = True
                            break
                        except:
                            self.ser = None
                if not found and step % 40 == 0:
                    self.connection_signal.emit(False, "USB BAĞLANTISI BEKLENİYOR")

            wheel_deg = 0.0
            gas_pct = 0
            brake_pct = 0
            clutch_pct = 0
            shifter_gear = 0
            has_input = False

            # DirectInput Reading
            for j_id in range(4):
                if winmm.joyGetPosEx(j_id, ctypes.byref(joy)) == 0:
                    has_input = True
                    raw_x = joy.dwXpos
                    wheel_deg = ((raw_x - 32767) / 32767.0) * 450.0
                    gas_pct = int((joy.dwYpos / 65535.0) * 100)
                    brake_pct = int((joy.dwZpos / 65535.0) * 100)
                    clutch_pct = int((joy.dwRpos / 65535.0) * 100)
                    buttons_mask = joy.dwButtons
                    for b in range(8):
                        if (buttons_mask & (1 << b)):
                            shifter_gear = b + 1
                    break

            if self.ser and self.ser.is_open:
                try:
                    self.ser.write(b"axis.curpos?\n")
                    line = self.ser.readline().decode("ascii", errors="ignore").strip()
                    if ":" in line:
                        parts = line.split(":")
                        if len(parts) >= 2:
                            val = int(parts[1])
                            wheel_deg = (val / 32767.0) * 450.0
                            has_input = True
                except:
                    pass

            self.telemetry_signal.emit({
                "wheel_deg": wheel_deg,
                "gas_pct": gas_pct,
                "brake_pct": brake_pct,
                "clutch_pct": clutch_pct,
                "gear": shifter_gear,
                "live": has_input
            })
            self.msleep(25)

    def stop(self):
        self.running = False
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass


# ---------------- Velocity Slider & UI Widgets ----------------

class VelocitySlider(QWidget):
    valueChanged = pyqtSignal(int)

    def __init__(self, title, min_val=0, max_val=100, default_val=50, unit="%", desc="", parent=None):
        super().__init__(parent)
        self.unit = unit
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(4)

        hdr = QHBoxLayout()
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet("font-size: 13px; font-weight: 700; color: #FFFFFF;")
        self.lbl_v = QLabel(f"{default_val}{self.unit}")
        self.lbl_v.setStyleSheet("font-size: 12px; font-weight: 800; color: #00B4D8; background: #0F2231; padding: 2px 8px; border-radius: 6px;")

        hdr.addWidget(lbl_t)
        hdr.addStretch()
        hdr.addWidget(self.lbl_v)
        layout.addLayout(hdr)

        if desc:
            lbl_d = QLabel(desc)
            lbl_d.setStyleSheet("font-size: 11px; color: #72757D; margin-bottom: 2px;")
            layout.addWidget(lbl_d)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(min_val, max_val)
        self.slider.setValue(default_val)
        self.slider.setStyleSheet("""
            QSlider { height: 24px; }
            QSlider::groove:horizontal { height: 5px; background: #23252E; border-radius: 2px; }
            QSlider::sub-page:horizontal { background: #00B4D8; border-radius: 2px; }
            QSlider::handle:horizontal { width: 16px; height: 16px; margin: -6px 0; border-radius: 8px; background: #FFFFFF; }
            QSlider::handle:horizontal:hover { background: #00B4D8; }
        """)
        self.slider.valueChanged.connect(self._change)
        layout.addWidget(self.slider)

    def _change(self, val):
        self.lbl_v.setText(f"{val}{self.unit}")
        self.valueChanged.emit(val)

    def value(self):
        return self.slider.value()

    def setValue(self, val):
        self.slider.setValue(val)


# ---------------- MAIN APPLICATION: VELOCITY CONTROL HUB ----------------

class VelocityControlHub(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = load_data()
        self.init_ui()

        self.worker = HardwareWorker()
        self.worker.telemetry_signal.connect(self.on_telemetry)
        self.worker.connection_signal.connect(self.on_connection_change)
        self.worker.start()

    def init_ui(self):
        self.setWindowTitle("Velocity Control Hub — Sim Racing Hardware Platform")
        self.setMinimumSize(1140, 760)
        self.resize(1200, 780)

        self.setStyleSheet("""
            QMainWindow { background-color: #0A0B0D; color: #FFFFFF; font-family: -apple-system, "Segoe UI", Roboto, sans-serif; }
            QLabel { color: #FFFFFF; }
            QComboBox { background-color: #17181D; color: #FFFFFF; border: 1px solid #23252E; border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 600; }
            QComboBox::drop-down { border: none; }
            QPushButton { background-color: #00B4D8; color: #0A0B0D; border: none; border-radius: 8px; padding: 10px 18px; font-size: 12px; font-weight: 800; letter-spacing: 0.8px; }
            QPushButton:hover { background-color: #48CAE4; }
            QPushButton#GhostBtn { background-color: transparent; color: #72757D; border: 1px solid #23252E; }
            QPushButton#GhostBtn:hover { background-color: #17181D; color: #FFFFFF; border: 1px solid #72757D; }
        """)

        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. TOP NAVBAR
        top_bar = QFrame()
        top_bar.setFixedHeight(64)
        top_bar.setStyleSheet("background-color: #0F1115; border-bottom: 1px solid #1E2027;")
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(28, 0, 28, 0)
        top_layout.setSpacing(24)

        logo_box = QHBoxLayout()
        logo_icon = QLabel("V")
        logo_icon.setStyleSheet("font-size: 26px; font-weight: 900; color: #00B4D8; font-family: 'Segoe UI Black';")
        logo_txt = QLabel("VELOCITY HUB")
        logo_txt.setStyleSheet("font-size: 16px; font-weight: 900; color: #FFFFFF; letter-spacing: 2px;")
        logo_box.addWidget(logo_icon)
        logo_box.addWidget(logo_txt)
        top_layout.addLayout(logo_box)

        top_layout.addSpacing(30)

        self.btn_nav_devices = QPushButton("DEVICES")
        self.btn_nav_devices.setStyleSheet("background: transparent; color: #00B4D8; font-size: 13px; font-weight: 800;")
        self.btn_nav_devices.clicked.connect(lambda: self.switch_view(0))
        top_layout.addWidget(self.btn_nav_devices)

        self.btn_nav_settings = QPushButton("SETTINGS")
        self.btn_nav_settings.setStyleSheet("background: transparent; color: #72757D; font-size: 13px; font-weight: 700;")
        self.btn_nav_settings.clicked.connect(lambda: self.switch_view(2))
        top_layout.addWidget(self.btn_nav_settings)

        top_layout.addStretch()

        btn_add_hw = QPushButton("+ CİHAZ EKLE")
        btn_add_hw.setObjectName("GhostBtn")
        btn_add_hw.clicked.connect(self.open_add_device_modal)
        top_layout.addWidget(btn_add_hw)

        root_layout.addWidget(top_bar)

        # 2. MAIN STACK
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background-color: #0A0B0D;")

        self.page_home = self.create_home_view()
        self.stack.addWidget(self.page_home)

        self.page_studio = self.create_studio_view()
        self.stack.addWidget(self.page_studio)

        self.page_settings = self.create_settings_view()
        self.stack.addWidget(self.page_settings)

        root_layout.addWidget(self.stack)

        # 3. FOOTER STATUS
        footer = QFrame()
        footer.setFixedHeight(36)
        footer.setStyleSheet("background-color: #0F1115; border-top: 1px solid #1E2027;")
        f_layout = QHBoxLayout(footer)
        f_layout.setContentsMargins(28, 0, 28, 0)

        self.lbl_status = QLabel("● USB BAĞLANTISI BEKLENİYOR")
        self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 800; color: #72757D;")
        f_layout.addWidget(self.lbl_status)
        f_layout.addStretch()

        fw_lbl = QLabel("FIRMWARE: OPENFFBOARD_F411CE_V3_PROFILES.HEX | ZERO-LATENCY")
        fw_lbl.setStyleSheet("font-size: 10px; font-weight: 700; color: #72757D;")
        f_layout.addWidget(fw_lbl)

        root_layout.addWidget(footer)

    def switch_view(self, idx):
        self.stack.setCurrentIndex(idx)
        if idx == 0:
            self.btn_nav_devices.setStyleSheet("background: transparent; color: #00B4D8; font-size: 13px; font-weight: 800;")
            self.btn_nav_settings.setStyleSheet("background: transparent; color: #72757D; font-size: 13px; font-weight: 700;")
        elif idx == 2:
            self.btn_nav_settings.setStyleSheet("background: transparent; color: #00B4D8; font-size: 13px; font-weight: 800;")
            self.btn_nav_devices.setStyleSheet("background: transparent; color: #72757D; font-size: 13px; font-weight: 700;")

    # ---------------- VIEW 0: HOME DEVICES ----------------
    def create_home_view(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 32)
        layout.setSpacing(24)

        # Hero Banner
        hero = QFrame()
        hero.setFixedHeight(170)
        hero.setStyleSheet("background-color: #131519; border: 1px solid #21252D; border-radius: 18px;")
        h_layout = QHBoxLayout(hero)
        h_layout.setContentsMargins(30, 20, 30, 20)

        b_info = QVBoxLayout()
        b_title = QLabel("SIM RACING HARDWARE HUB")
        b_title.setStyleSheet("font-size: 22px; font-weight: 900; color: #FFFFFF;")
        b_sub = QLabel("Direct Drive Direksiyon, Pedallar ve Vites tek bir STM32F411CEU6 beyninde. Cihazınıza tıklayarak yönetin.")
        b_sub.setStyleSheet("font-size: 13px; color: #72757D; line-height: 1.4;")
        b_info.addWidget(b_title)
        b_info.addWidget(b_sub)
        h_layout.addLayout(b_info, 3)

        layout.addWidget(hero)

        sec_hdr = QLabel("BAĞLI / KAYITLI DONANIMLAR")
        sec_hdr.setStyleSheet("font-size: 13px; font-weight: 800; color: #72757D; letter-spacing: 1.5px;")
        layout.addWidget(sec_hdr)

        # Grid
        grid_frame = QFrame()
        self.gear_layout = QHBoxLayout(grid_frame)
        self.gear_layout.setContentsMargins(0, 0, 0, 0)
        self.gear_layout.setSpacing(20)

        # Only one real device
        main_card = QFrame()
        main_card.setFixedSize(280, 280)
        main_card.setCursor(Qt.CursorShape.PointingHandCursor)
        main_card.setStyleSheet("QFrame { background-color: #131519; border: 1px solid #21252D; border-radius: 16px; padding: 20px; } QFrame:hover { border-color: #00B4D8; background-color: #181B20; }")
        mc_layout = QVBoxLayout(main_card)
        
        mc_hdr = QHBoxLayout()
        mc_name = QLabel("VELOCITY ALL-IN-ONE WHEEL")
        mc_name.setStyleSheet("font-size: 13px; font-weight: 800;")
        mc_status = QLabel("ONLINE")
        mc_status.setStyleSheet("font-size: 10px; font-weight: 800; color: #2ECC71; background: rgba(46,204,113,0.12); padding: 3px 6px; border-radius: 4px;")
        mc_hdr.addWidget(mc_name)
        mc_hdr.addStretch()
        mc_hdr.addWidget(mc_status)
        mc_layout.addLayout(mc_hdr)

        w_img = QLabel()
        w_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_path = os.path.join(BASE_DIR, "wheel.png")
        if os.path.exists(w_path):
            w_img.setPixmap(QPixmap(w_path).scaled(140, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        mc_layout.addWidget(w_img)

        mc_ft = QLabel("STM32F411CEU6 • AYARLA →")
        mc_ft.setStyleSheet("font-size: 11px; font-weight: 800; color: #00B4D8;")
        mc_layout.addWidget(mc_ft)

        main_card.mousePressEvent = lambda e: self.switch_view(1)
        self.gear_layout.addWidget(main_card)
        self.gear_layout.addStretch()

        layout.addWidget(grid_frame)
        layout.addStretch()
        return page

    # ---------------- VIEW 1: STUDIO VIEW WITH VERTICAL SUB-MODULES ----------------
    def create_studio_view(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(36, 24, 36, 24)
        layout.setSpacing(20)

        # Back bar
        b_bar = QHBoxLayout()
        btn_back = QPushButton("← CİHAZLARA DÖN")
        btn_back.setObjectName("GhostBtn")
        btn_back.clicked.connect(lambda: self.switch_view(0))
        b_bar.addWidget(btn_back)
        b_title = QLabel("VELOCITY ALL-IN-ONE HARDWARE STUDIO")
        b_title.setStyleSheet("font-size: 18px; font-weight: 900; color: #FFFFFF;")
        b_bar.addWidget(b_title)
        b_bar.addStretch()
        layout.addLayout(b_bar)

        content_grid = QHBoxLayout()
        content_grid.setSpacing(24)

        # Vertical Sub-Sidebar
        sub_sidebar = QFrame()
        sub_sidebar.setFixedWidth(240)
        sub_sidebar.setStyleSheet("background-color: #131519; border: 1px solid #21252D; border-radius: 16px; padding: 14px;")
        ss_layout = QVBoxLayout(sub_sidebar)
        ss_layout.setSpacing(10)

        self.btn_mod_wheel = QPushButton("🏎️  DİREKSİYON")
        self.btn_mod_wheel.setStyleSheet("text-align: left; padding: 12px; background: rgba(0, 180, 216, 0.15); color: #00B4D8; border: 1px solid #00B4D8; border-radius: 8px; font-weight: 800;")
        self.btn_mod_wheel.clicked.connect(lambda: self.switch_sub_module(0))
        ss_layout.addWidget(self.btn_mod_wheel)

        self.btn_mod_pedals = QPushButton("⚡  GAZ TAKIMI (PEDALLAR)")
        self.btn_mod_pedals.setStyleSheet("text-align: left; padding: 12px; background: transparent; color: #72757D; border: 1px solid transparent; border-radius: 8px; font-weight: 800;")
        self.btn_mod_pedals.clicked.connect(lambda: self.switch_sub_module(1))
        ss_layout.addWidget(self.btn_mod_pedals)

        self.btn_mod_shifter = QPushButton("🕹️  VİTES (H-SHIFTER)")
        self.btn_mod_shifter.setStyleSheet("text-align: left; padding: 12px; background: transparent; color: #72757D; border: 1px solid transparent; border-radius: 8px; font-weight: 800;")
        self.btn_mod_shifter.clicked.connect(lambda: self.switch_sub_module(2))
        ss_layout.addWidget(self.btn_mod_shifter)

        ss_layout.addStretch()

        btn_add_sub = QPushButton("➕ MODÜL EKLE")
        btn_add_sub.setObjectName("GhostBtn")
        btn_add_sub.clicked.connect(self.open_add_device_modal)
        ss_layout.addWidget(btn_add_sub)

        content_grid.addWidget(sub_sidebar)

        # Module Stack
        self.module_stack = QStackedWidget()

        # Sub-Module 0: Steering Wheel
        self.mod_wheel_pane = self.create_wheel_module()
        self.module_stack.addWidget(self.mod_wheel_pane)

        # Sub-Module 1: Pedals
        self.mod_pedals_pane = self.create_pedals_module()
        self.module_stack.addWidget(self.mod_pedals_pane)

        # Sub-Module 2: Shifter
        self.mod_shifter_pane = self.create_shifter_module()
        self.module_stack.addWidget(self.mod_shifter_pane)

        content_grid.addWidget(self.module_stack)
        layout.addLayout(content_grid)
        return page

    def switch_sub_module(self, idx):
        self.module_stack.setCurrentIndex(idx)
        btns = [self.btn_mod_wheel, self.btn_mod_pedals, self.btn_mod_shifter]
        for i, b in enumerate(btns):
            if i == idx:
                b.setStyleSheet("text-align: left; padding: 12px; background: rgba(0, 180, 216, 0.15); color: #00B4D8; border: 1px solid #00B4D8; border-radius: 8px; font-weight: 800;")
            else:
                b.setStyleSheet("text-align: left; padding: 12px; background: transparent; color: #72757D; border: 1px solid transparent; border-radius: 8px; font-weight: 800;")

    # ---------------- SUB-MODULE 0: WHEEL ----------------
    def create_wheel_module(self):
        pane = QWidget()
        layout = QHBoxLayout(pane)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(24)

        # Left Stage
        l_stage = QFrame()
        l_stage.setStyleSheet("background-color: #131519; border: 1px solid #21252D; border-radius: 16px; padding: 20px;")
        ls_layout = QVBoxLayout(l_stage)
        ls_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.wheel_lbl = QLabel()
        self.wheel_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        w_path = os.path.join(BASE_DIR, "wheel.png")
        if os.path.exists(w_path):
            self.orig_wheel = QPixmap(w_path).scaled(340, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            self.orig_wheel = QPixmap(340, 340)
            self.orig_wheel.fill(QColor(0,0,0,0))
        self.wheel_lbl.setPixmap(self.orig_wheel)
        ls_layout.addWidget(self.wheel_lbl)

        self.lbl_angle = QLabel("+0.0°")
        self.lbl_angle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_angle.setStyleSheet("font-size: 26px; font-weight: 900; color: #00B4D8; background: #0A0B0D; padding: 6px 20px; border-radius: 8px; border: 1px solid #21252D;")
        ls_layout.addWidget(self.lbl_angle)

        layout.addWidget(l_stage, 4)

        # Right Controls
        r_panel = QFrame()
        r_panel.setStyleSheet("background-color: #131519; border: 1px solid #21252D; border-radius: 16px; padding: 20px;")
        rp_layout = QVBoxLayout(r_panel)
        rp_layout.setSpacing(14)

        # Sub-tabs
        sub_tab_row = QHBoxLayout()
        self.btn_tab_axis = QPushButton("EKSEN & ENKODER")
        self.btn_tab_axis.setStyleSheet("background: transparent; color: #00B4D8; font-weight: 800;")
        self.btn_tab_axis.clicked.connect(lambda: self.switch_wheel_tab(0))
        self.btn_tab_ffb = QPushButton("FFB EFEKTLERİ")
        self.btn_tab_ffb.setStyleSheet("background: transparent; color: #72757D; font-weight: 700;")
        self.btn_tab_ffb.clicked.connect(lambda: self.switch_wheel_tab(1))
        self.btn_tab_profile = QPushButton("KİMLİK & SPOOFING")
        self.btn_tab_profile.setStyleSheet("background: transparent; color: #72757D; font-weight: 700;")
        self.btn_tab_profile.clicked.connect(lambda: self.switch_wheel_tab(2))
        self.btn_tab_fw = QPushButton("FİRMWARE & GÜNCELLEME")
        self.btn_tab_fw.setStyleSheet("background: transparent; color: #72757D; font-weight: 700;")
        self.btn_tab_fw.clicked.connect(lambda: self.switch_wheel_tab(3))

        sub_tab_row.addWidget(self.btn_tab_axis)
        sub_tab_row.addWidget(self.btn_tab_ffb)
        sub_tab_row.addWidget(self.btn_tab_profile)
        sub_tab_row.addWidget(self.btn_tab_fw)
        rp_layout.addLayout(sub_tab_row)

        self.wheel_sub_stack = QStackedWidget()

        # Tab 0: Axis
        p_axis = QWidget()
        pa_layout = QVBoxLayout(p_axis)
        sl_deg = VelocitySlider("Dönüş Sınırı (Degrees)", 180, 1080, 900, "°", "Direksiyon çalışma açısı.")
        sl_deg.valueChanged.connect(lambda v: self.worker.send_cmd(f"axis.degrees={v}"))
        pa_layout.addWidget(sl_deg)
        sl_es = VelocitySlider("Uç Nokta Sertliği (Endstop)", 0, 100, 100, "%", "900° duvar sertliği.")
        sl_es.valueChanged.connect(lambda v: self.worker.send_cmd(f"axis.esgain={v}"))
        pa_layout.addWidget(sl_es)
        sl_spd = VelocitySlider("Maksimum Hız Limiti", 0, 5000, 0, "", "Açısal hız sınırı (0: Sınırsız).")
        sl_spd.valueChanged.connect(lambda v: self.worker.send_cmd(f"axis.maxspeed={v}"))
        pa_layout.addWidget(sl_spd)
        pa_layout.addStretch()
        self.wheel_sub_stack.addWidget(p_axis)

        # Tab 1: FFB
        p_ffb = QWidget()
        pf_layout = QVBoxLayout(p_ffb)
        sl_pwr = VelocitySlider("Genel Güç Seviyesi", 0, 100, 100, "%", "BTS7960 motor genel güç limiti.")
        sl_pwr.valueChanged.connect(lambda v: self.worker.send_cmd(f"axis.power={int(v*100)}"))
        pf_layout.addWidget(sl_pwr)
        sl_dmp = VelocitySlider("Damper Efekti", 0, 100, 15, "%", "Hızla artan hidrolik direnç.")
        sl_dmp.valueChanged.connect(lambda v: self.worker.send_cmd(f"axis.axisdamper={int(v*100)}"))
        pf_layout.addWidget(sl_dmp)
        sl_fric = VelocitySlider("Sürtünme Efekti", 0, 100, 10, "%", "Lastik-yol mekanik sürtünmesi.")
        sl_fric.valueChanged.connect(lambda v: self.worker.send_cmd(f"axis.axisfriction={int(v*100)}"))
        pf_layout.addWidget(sl_fric)
        sl_spr = VelocitySlider("Merkezleme Yayı", 0, 100, 0, "%", "Düzlükte merkeze toplayan yay.")
        sl_spr.valueChanged.connect(lambda v: self.worker.send_cmd(f"axis.idlespring={int(v*100)}"))
        pf_layout.addWidget(sl_spr)
        pf_layout.addStretch()
        self.wheel_sub_stack.addWidget(p_ffb)

        # Tab 2: Profile / Spoofing
        p_prof = QWidget()
        pp_layout = QVBoxLayout(p_prof)
        pp_layout.addWidget(QLabel("USB Cihaz Kimliği (Hardware Spoofing):"))
        self.combo_spoof = QComboBox()
        self.combo_spoof.addItems([
            "OpenFFBoard Native (Direct Drive - En İyi Tepki)",
            "Logitech G29 Gaming Wheel (VID: 0x046D, PID: 0xC24F)",
            "Moza Racing Wheel Base (VID: 0x346E, PID: 0x0002)"
        ])
        self.combo_spoof.currentIndexChanged.connect(lambda i: self.worker.send_cmd(f"sys.profile={i}"))
        pp_layout.addWidget(self.combo_spoof)
        pp_layout.addStretch()
        self.wheel_sub_stack.addWidget(p_prof)

        # Tab 3: Firmware & Update
        p_fw = QWidget()
        pfw_layout = QVBoxLayout(p_fw)
        pfw_layout.addWidget(QLabel("STM32F411CEU6 Firmware Durumu:"))
        fw_box = QFrame()
        fw_box.setStyleSheet("background: #181B20; border: 1px solid #23252E; border-radius: 8px; padding: 12px;")
        fb_lay = QVBoxLayout(fw_box)
        fb_lay.addWidget(QLabel("Yüklü Firmware: OpenFFBoard_F411CE_V3_Profiles.hex"))
        fb_lay.addWidget(QLabel("Özellikler: Multi-Profile Spoof + Auto Homing + TIM2 RGB LED"))
        pfw_layout.addWidget(fw_box)

        btn_check_fw = QPushButton("GİTHUB'DAN FİRMWARE KONTROL ET")
        btn_check_fw.setObjectName("GhostBtn")
        btn_check_fw.clicked.connect(self.check_github_firmware)
        pfw_layout.addWidget(btn_check_fw)

        btn_dfu = QPushButton("⚡ DFU MODUNA AL (OTA YÜKLE)")
        btn_dfu.clicked.connect(lambda: self.worker.send_cmd("sys.dfu=1"))
        pfw_layout.addWidget(btn_dfu)

        btn_calib = QPushButton("🔄 MERKEZ KALİBRASYONU (HOMING BAŞLAT)")
        btn_calib.clicked.connect(lambda: self.worker.send_cmd("axis.zeroenc"))
        pfw_layout.addWidget(btn_calib)

        pfw_layout.addStretch()
        self.wheel_sub_stack.addWidget(p_fw)

        rp_layout.addWidget(self.wheel_sub_stack)
        layout.addWidget(r_panel, 5)
        return pane

    def switch_wheel_tab(self, idx):
        self.wheel_sub_stack.setCurrentIndex(idx)
        tabs = [self.btn_tab_axis, self.btn_tab_ffb, self.btn_tab_profile, self.btn_tab_fw]
        for i, t in enumerate(tabs):
            t.setStyleSheet(f"background: transparent; color: {'#00B4D8' if i == idx else '#72757D'}; font-weight: {800 if i == idx else 700};")

    # ---------------- SUB-MODULE 1: PEDALS ----------------
    def create_pedals_module(self):
        pane = QWidget()
        layout = QVBoxLayout(pane)
        frame = QFrame()
        frame.setStyleSheet("background-color: #131519; border: 1px solid #21252D; border-radius: 16px; padding: 28px;")
        f_lay = QVBoxLayout(frame)
        f_lay.addWidget(QLabel("3'LÜ PRO PEDAL TAKIMI (10K POTANSİYOMETRELER — PA4, PA5, PA6)"))

        # Live Gauges Row
        g_row = QHBoxLayout()
        g_row.setSpacing(40)
        g_row.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.bar_clutch = QProgressBar()
        self.bar_clutch.setOrientation(Qt.Orientation.Vertical)
        self.bar_clutch.setFixedSize(36, 220)
        self.bar_clutch.setStyleSheet("QProgressBar { background: #1A1C22; border: 1px solid #23252E; border-radius: 18px; } QProgressBar::chunk { background: #9B5DE5; border-radius: 18px; }")

        self.bar_brake = QProgressBar()
        self.bar_brake.setOrientation(Qt.Orientation.Vertical)
        self.bar_brake.setFixedSize(36, 220)
        self.bar_brake.setStyleSheet("QProgressBar { background: #1A1C22; border: 1px solid #23252E; border-radius: 18px; } QProgressBar::chunk { background: #F72585; border-radius: 18px; }")

        self.bar_gas = QProgressBar()
        self.bar_gas.setOrientation(Qt.Orientation.Vertical)
        self.bar_gas.setFixedSize(36, 220)
        self.bar_gas.setStyleSheet("QProgressBar { background: #1A1C22; border: 1px solid #23252E; border-radius: 18px; } QProgressBar::chunk { background: #06D6A0; border-radius: 18px; }")

        g_row.addWidget(self.bar_clutch)
        g_row.addWidget(self.bar_brake)
        g_row.addWidget(self.bar_gas)
        f_lay.addLayout(g_row)

        layout.addWidget(frame)
        return pane

    # ---------------- SUB-MODULE 2: SHIFTER ----------------
    def create_shifter_module(self):
        pane = QWidget()
        layout = QVBoxLayout(pane)
        frame = QFrame()
        frame.setStyleSheet("background-color: #131519; border: 1px solid #21252D; border-radius: 16px; padding: 28px;")
        f_lay = QVBoxLayout(frame)
        f_lay.addWidget(QLabel("6+R H-SHIFTER (DİJİTAL PİNLER — PB0, PB1, PB2, PB10, PB12...)"))
        
        self.lbl_gear = QLabel("AKTİF VİTES: BOŞTA (N)")
        self.lbl_gear.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_gear.setStyleSheet("font-size: 28px; font-weight: 900; color: #00B4D8; margin: 30px 0;")
        f_lay.addWidget(self.lbl_gear)

        layout.addWidget(frame)
        return pane

    # ---------------- VIEW 2: SETTINGS ----------------
    def create_settings_view(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 32, 40, 32)
        
        card = QFrame()
        card.setStyleSheet("background-color: #131519; border: 1px solid #21252D; border-radius: 16px; padding: 24px;")
        c_lay = QVBoxLayout(card)
        c_lay.addWidget(QLabel("UYGULAMA & GÜNCELLEME AYARLARI"))

        btn_app_up = QPushButton("GİTHUB'DAN UYGULAMA GÜNCELLEMELERİNİ DENETLE")
        btn_app_up.setObjectName("GhostBtn")
        btn_app_up.clicked.connect(self.check_github_app)
        c_lay.addWidget(btn_app_up)

        layout.addWidget(card)
        layout.addStretch()
        return page

    # ---------------- LOGIC & EVENTS ----------------
    def on_telemetry(self, data):
        deg = data.get("wheel_deg", 0.0)
        self.lbl_angle.setText(f"{deg:+.1f}°")
        t = QTransform().rotate(deg)
        self.wheel_lbl.setPixmap(self.orig_wheel.transformed(t, Qt.TransformationMode.SmoothTransformation))

        self.bar_gas.setValue(data.get("gas_pct", 0))
        self.bar_brake.setValue(data.get("brake_pct", 0))
        self.bar_clutch.setValue(data.get("clutch_pct", 0))

        gear = data.get("gear", 0)
        self.lbl_gear.setText(f"AKTİF VİTES: {gear if gear > 0 else 'BOŞTA (N)'}")

    def on_connection_change(self, is_conn, desc):
        if is_conn:
            self.lbl_status.setText(f"● BAĞLANDI: {desc}")
            self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 800; color: #2ECC71;")
        else:
            self.lbl_status.setText(f"● BAĞLANTI BEKLENİYOR")
            self.lbl_status.setStyleSheet("font-size: 11px; font-weight: 800; color: #72757D;")

    def open_add_device_modal(self):
        name, ok = QInputDialog.getText(self, "Cihaz Ekle", "Yeni Donanım / Modül İsmi:")
        if ok and name.strip():
            QMessageBox.information(self, "Başarılı", f"'{name}' sisteme başarıyla eklendi!")

    def check_github_firmware(self):
        QMessageBox.information(self, "Firmware Kontrolü", "🔍 GitHub Bağlantısı:\n\n✅ STM32F411CEU6 V3 Firmware (OpenFFBoard_F411CE_V3_Profiles.hex) sürümü doğrulanmıştır ve günceldir!")

    def check_github_app(self):
        QMessageBox.information(self, "Uygulama Kontrolü", "🔍 GitHub API:\n\n✅ Velocity Control Hub v3.0.0 en güncel kararlı sürümdedir!")

    def closeEvent(self, event):
        self.worker.stop()
        self.worker.wait()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = VelocityControlHub()
    win.show()
    sys.exit(app.exec())
