#!/usr/bin/env python3
"""
JARVIS COMMAND CENTER - MAIN HUD
Cybernetic Sci-Fi Holographic Desktop Interface
Engineered with PyQt6, custom QPainter real-time animations, and live pipeline streaming.
"""

import sys
import os
import time
import json
import math
import random
import subprocess
import traceback
from typing import List

# Ensure stdout/stderr are valid streams under pythonw GUI execution
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

def exception_hook(exctype, value, tb):
    err = "".join(traceback.format_exception(exctype, value, tb))
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hud_crash.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n--- HUD CRASH [{time.strftime('%Y-%m-%d %H:%M:%S')}] ---\n")
            f.write(err)
    except Exception:
        pass
    sys.__excepthook__(exctype, value, tb)

sys.excepthook = exception_hook

# Auto-install dependencies if missing
try:
    import PyQt6
    import psutil
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "PyQt6", "psutil"])
    import psutil

from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QBrush,
    QFont,
    QLinearGradient,
    QRadialGradient,
    QPainterPath,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QTextEdit,
    QFrame,
)

from jarvis_config import (
    JARVIS_CORE_DIR,
    get_target_repo,
    get_project_name,
    is_n8n_online,
    get_current_git_branch,
)

PROJECT_ROOT = JARVIS_CORE_DIR
TRANSCRIPT_FILE = os.path.join(JARVIS_CORE_DIR, "last_transcript.txt")
INTENT_FILE = os.path.join(JARVIS_CORE_DIR, "last_intent.json")
STATUS_FILE = os.path.join(JARVIS_CORE_DIR, "last_status.txt")
ANTIGRAVITY_TASK_FILE = os.path.join(JARVIS_CORE_DIR, "antigravity_task.json")
ANTIGRAVITY_LOG_FILE = os.path.join(JARVIS_CORE_DIR, "antigravity_log.txt")

# Cyber Sci-Fi Color Palette
COLOR_BG = QColor(11, 11, 30, 245)
COLOR_PANEL_BG = QColor(14, 16, 40, 220)
COLOR_CYAN = QColor(0, 225, 255)
COLOR_CYAN_DIM = QColor(0, 225, 255, 60)
COLOR_AMBER = QColor(255, 157, 0)
COLOR_GREEN = QColor(0, 255, 136)
COLOR_TEXT_DIM = QColor(140, 170, 200)
COLOR_BORDER = QColor(0, 225, 255, 120)

class SciFiFrame(QFrame):
    """Custom styled frame with sci-fi bracket corners and micro-dot aesthetics."""
    def __init__(self, title="PANEL", parent=None):
        super().__init__(parent)
        self.title = title
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background with subtle gradient
        bg_grad = QLinearGradient(0, 0, w, h)
        bg_grad.setColorAt(0, QColor(12, 15, 36, 210))
        bg_grad.setColorAt(1, QColor(8, 10, 26, 230))
        painter.fillRect(self.rect(), bg_grad)

        # Border
        pen = QPen(COLOR_CYAN_DIM, 1)
        painter.setPen(pen)
        painter.drawRect(0, 0, w - 1, h - 1)

        # High-tech corner brackets
        bracket_pen = QPen(COLOR_CYAN, 2)
        painter.setPen(bracket_pen)
        blen = 14

        # Top-Left
        painter.drawLine(0, 0, blen, 0)
        painter.drawLine(0, 0, 0, blen)
        # Top-Right
        painter.drawLine(w - 1, 0, w - 1 - blen, 0)
        painter.drawLine(w - 1, 0, w - 1, blen)
        # Bottom-Left
        painter.drawLine(0, h - 1, blen, h - 1)
        painter.drawLine(0, h - 1, 0, h - 1 - blen)
        # Bottom-Right
        painter.drawLine(w - 1, h - 1, w - 1 - blen, h - 1)
        painter.drawLine(w - 1, h - 1, w - 1, h - 1 - blen)

        # Header Title Bar
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 225, 255, 35))
        painter.drawRect(2, 2, w - 4, 22)

        # Title Text & Micro-tag
        painter.setPen(COLOR_CYAN)
        font = QFont("Consolas", 9, QFont.Weight.Bold)
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.5)
        painter.setFont(font)
        painter.drawText(10, 17, f"// {self.title.upper()} //")

        # Top-right micro-dots
        painter.setBrush(COLOR_GREEN)
        painter.drawEllipse(w - 18, 9, 5, 5)
        painter.setBrush(COLOR_AMBER)
        painter.drawEllipse(w - 28, 9, 5, 5)


class WaveformVisualizer(QWidget):
    """Dynamic animated waveform monitor simulating live telemetry/audio frequencies."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(60)
        self.phase = 0.0

    def advance(self):
        self.phase += 0.15
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        mid_y = h / 2.0

        # Background grid lines
        painter.setPen(QPen(QColor(0, 225, 255, 20), 1, Qt.PenStyle.DashLine))
        painter.drawLine(0, int(mid_y), w, int(mid_y))
        for x in range(0, w, 30):
            painter.drawLine(x, 0, x, h)

        # Primary flowing cyan wave
        path = QPainterPath()
        path.moveTo(0, mid_y)
        for x in range(0, w, 4):
            y = mid_y + math.sin(x * 0.04 + self.phase) * 16.0 + math.sin(x * 0.08 - self.phase * 0.8) * 8.0
            path.lineTo(x, y)

        pen1 = QPen(COLOR_CYAN, 2)
        painter.setPen(pen1)
        painter.drawPath(path)

        # Secondary harmonic amber wave
        path2 = QPainterPath()
        path2.moveTo(0, mid_y)
        for x in range(0, w, 4):
            y = mid_y + math.cos(x * 0.03 - self.phase * 1.2) * 12.0
            path2.lineTo(x, y)

        pen2 = QPen(QColor(255, 157, 0, 160), 1.5)
        painter.setPen(pen2)
        painter.drawPath(path2)


class RotatingAICore(QWidget):
    """Central Holographic Cyber HUD Rotating Arc Reactor & Telemetry Visualizer."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 280)
        self.angle_outer = 0.0
        self.angle_inner = 0.0
        self.pulse = 1.0
        self.pulse_dir = 0.02
        self.samples = [random.uniform(0.3, 1.0) for _ in range(36)]

    def advance(self):
        self.angle_outer -= 1.2
        self.angle_inner += 2.0
        self.pulse += self.pulse_dir
        if self.pulse > 1.15 or self.pulse < 0.85:
            self.pulse_dir *= -1
        # Random audio pulse variance
        for i in range(len(self.samples)):
            self.samples[i] = max(0.2, min(1.0, self.samples[i] + random.uniform(-0.15, 0.15)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        radius = min(cx, cy) - 15

        # 1. Subtle central ambient glow
        rad_grad = QRadialGradient(cx, cy, radius * 0.8)
        rad_grad.setColorAt(0, QColor(0, 225, 255, 45))
        rad_grad.setColorAt(0.7, QColor(0, 225, 255, 10))
        rad_grad.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setBrush(rad_grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QPointF(cx, cy), radius * 0.9, radius * 0.9)

        # 2. Outer Ring with Ticks (Rotates CCW)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle_outer)
        outer_pen = QPen(COLOR_CYAN, 1.5, Qt.PenStyle.DashLine)
        painter.setPen(outer_pen)
        painter.drawEllipse(QPointF(0, 0), radius, radius)

        # Segmented outer brackets
        arc_pen = QPen(COLOR_CYAN, 3)
        painter.setPen(arc_pen)
        rect_outer = QRectF(-radius, -radius, radius * 2, radius * 2)
        painter.drawArc(rect_outer, int(20 * 16), int(60 * 16))
        painter.drawArc(rect_outer, int(140 * 16), int(60 * 16))
        painter.drawArc(rect_outer, int(260 * 16), int(60 * 16))
        painter.restore()

        # 3. Middle Radial Audio Wave Bars
        mid_r = radius * 0.72
        bar_pen = QPen(COLOR_CYAN, 2)
        painter.setPen(bar_pen)
        num_bars = len(self.samples)
        for i in range(num_bars):
            theta = (2 * math.pi / num_bars) * i + math.radians(self.angle_inner * 0.4)
            bar_len = 10 + self.samples[i] * 18 * self.pulse
            x1 = cx + math.cos(theta) * (mid_r - bar_len)
            y1 = cy + math.sin(theta) * (mid_r - bar_len)
            x2 = cx + math.cos(theta) * mid_r
            y2 = cy + math.sin(theta) * mid_r
            painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 4. Inner Amber Target Reticle (Rotates CW)
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle_inner)
        inner_r = radius * 0.42 * self.pulse
        painter.setPen(QPen(COLOR_AMBER, 1.5))
        painter.drawEllipse(QPointF(0, 0), inner_r, inner_r)

        # Crosshairs
        painter.drawLine(QPointF(-inner_r - 6, 0), QPointF(-inner_r + 4, 0))
        painter.drawLine(QPointF(inner_r - 4, 0), QPointF(inner_r + 6, 0))
        painter.drawLine(QPointF(0, -inner_r - 6), QPointF(0, -inner_r + 4))
        painter.drawLine(QPointF(0, inner_r - 4), QPointF(0, inner_r + 6))
        painter.restore()

        # 5. Core Nucleus (Glowing Center Telemetry)
        core_r = 16 * self.pulse
        painter.setBrush(COLOR_GREEN)
        painter.setPen(QPen(QColor(0, 255, 136, 180), 2))
        painter.drawEllipse(QPointF(cx, cy), core_r, core_r)

        # Numerical telemetry readout
        painter.setPen(COLOR_CYAN)
        font = QFont("Consolas", 8, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(int(cx - 32), int(cy + radius * 0.85), f"SYNC:{int(98 + self.pulse*2)}%")
        painter.drawText(int(cx - 36), int(cy - radius * 0.78), f"HZ: 16.4K")


class JarvisHUD(QMainWindow):
    def __init__(self, target_repo: str = None):
        super().__init__()
        self.setWindowTitle("JARVIS COMMAND CENTER - MAIN HUD")
        self.resize(1280, 720)
        self.setMinimumSize(1024, 600)

        # High-tech dark window styling
        self.setStyleSheet("""
            QMainWindow {
                background-color: #0b0b1e;
            }
            QLabel {
                color: #00e1ff;
                font-family: 'Consolas', 'Segoe UI', monospace;
            }
            QTextEdit {
                background-color: #0c0e24;
                color: #00ff88;
                border: 1px solid rgba(0, 225, 255, 80);
                font-family: 'Consolas', monospace;
                font-size: 11px;
                padding: 6px;
            }
            QScrollBar:vertical {
                border: none;
                background: #080a1c;
                width: 6px;
            }
            QScrollBar::handle:vertical {
                background: #00e1ff;
                min-height: 20px;
                border-radius: 3px;
            }
        """)

        # Target project & telemetry context
        target_override = target_repo
        if target_override is None:
            for i, a in enumerate(sys.argv):
                if a == "--project" and i + 1 < len(sys.argv):
                    target_override = sys.argv[i + 1]
                    break
        self.target_repo = get_target_repo(target_override)
        self.project_name = get_project_name(self.target_repo)
        self.current_branch = get_current_git_branch(self.target_repo)
        self.n8n_online = is_n8n_online()
        self.last_status_check = time.time()

        self.last_transcript_raw = ""
        self.last_response_raw = ""
        self.last_status_raw = ""
        self.typewriter_text = ""
        self.typewriter_idx = 0
        self.active_command_log: List[str] = []
        self.last_ag_log_size = 0
        self.last_ag_task_status = ""

        self.setWindowTitle(f"JARVIS COMMAND CENTER - [{self.project_name.upper()}]")
        self.init_ui()

        # Timers
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.update_animations)
        self.anim_timer.start(35)  # ~30 FPS

        self.data_timer = QTimer(self)
        self.data_timer.timeout.connect(self.refresh_live_data)
        self.data_timer.start(100)  # 100ms pipeline refresh

    def init_ui(self):
        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(8)

        # ----------------- TOP HEADER / TITLE BAR -----------------
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)

        # Top-left glowing badges as specified
        self.badge_active = QLabel("[ACTIVE]")
        self.badge_active.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.badge_active.setStyleSheet("color: #00ff88; background: rgba(0, 255, 136, 25); border: 1px solid #00ff88; padding: 3px 8px; border-radius: 2px;")
        header_layout.addWidget(self.badge_active)

        self.badge_sysok = QLabel("[SYS_OK]")
        self.badge_sysok.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.badge_sysok.setStyleSheet("color: #00e1ff; background: rgba(0, 225, 255, 25); border: 1px solid #00e1ff; padding: 3px 8px; border-radius: 2px;")
        header_layout.addWidget(self.badge_sysok)

        title_label = QLabel(f"JARVIS COMMAND CENTER - [{self.project_name.upper()}]")
        title_label.setFont(QFont("Consolas", 13, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #00e1ff; letter-spacing: 2px; padding-left: 8px;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()

        self.badge_audio = QLabel("[AUDIO: 16kHz PCM]")
        self.badge_audio.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.badge_audio.setStyleSheet("color: #8ca0b8; background: rgba(140, 160, 184, 20); border: 1px solid #8ca0b8; padding: 3px 8px; border-radius: 2px;")
        header_layout.addWidget(self.badge_audio)

        self.badge_n8n = QLabel("[N8N: ONLINE]" if self.n8n_online else "[N8N: STANDBY]")
        self.badge_n8n.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.badge_n8n.setStyleSheet("color: #00ff88; background: rgba(0, 255, 136, 25); border: 1px solid #00ff88; padding: 3px 8px; border-radius: 2px;" if self.n8n_online else "color: #ff9d00; background: rgba(255, 157, 0, 25); border: 1px solid #ff9d00; padding: 3px 8px; border-radius: 2px;")
        header_layout.addWidget(self.badge_n8n)

        self.badge_groq = QLabel("[GROQ: ONLINE]")
        self.badge_groq.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.badge_groq.setStyleSheet("color: #ff9d00; background: rgba(255, 157, 0, 25); border: 1px solid #ff9d00; padding: 3px 8px; border-radius: 2px;")
        header_layout.addWidget(self.badge_groq)

        main_layout.addLayout(header_layout)

        # ----------------- MAIN 3-COLUMN CONTENT GRID -----------------
        grid = QGridLayout()
        grid.setSpacing(8)

        # === PANEL 1: SYSTEM STATUS (Top-Left) ===
        self.panel_sys = SciFiFrame("1. SYSTEM STATUS")
        sys_layout = QVBoxLayout(self.panel_sys)
        sys_layout.setContentsMargins(10, 30, 10, 10)
        sys_layout.setSpacing(5)

        self.lbl_proj_info = QLabel(f"PROJECT      : {self.project_name.upper()}")
        self.lbl_proj_info.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.lbl_proj_info.setStyleSheet("color: #00e1ff;")
        sys_layout.addWidget(self.lbl_proj_info)

        self.lbl_branch = QLabel(f"GIT BRANCH   : {self.current_branch}")
        self.lbl_branch.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self.lbl_branch.setStyleSheet("color: #00ff88;")
        sys_layout.addWidget(self.lbl_branch)

        self.lbl_n8n_pipe = QLabel(f"N8N ENGINE   : {'[ONLINE]' if self.n8n_online else '[STANDBY]'}")
        self.lbl_n8n_pipe.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.lbl_n8n_pipe.setStyleSheet("color: #00ff88;" if self.n8n_online else "color: #ff9d00;")
        sys_layout.addWidget(self.lbl_n8n_pipe)

        self.lbl_cpu = QLabel("CPU USAGE    : 0.0%")
        self.lbl_cpu.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        sys_layout.addWidget(self.lbl_cpu)

        self.lbl_ram = QLabel("MEMORY ALLOC : 0.0 MB")
        self.lbl_ram.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        sys_layout.addWidget(self.lbl_ram)

        self.lbl_audio = QLabel("AUDIO INPUT  : 16kHz PCM (PyAudio Active)")
        self.lbl_audio.setFont(QFont("Consolas", 8))
        self.lbl_audio.setStyleSheet("color: #8ca0b8;")
        sys_layout.addWidget(self.lbl_audio)

        # Animated signal waveform
        self.waveform = WaveformVisualizer()
        sys_layout.addWidget(self.waveform)
        grid.addWidget(self.panel_sys, 0, 0)

        # === CENTER FOCAL POINT: ROTATING AI CORE ===
        self.ai_core = RotatingAICore()
        grid.addWidget(self.ai_core, 0, 1, 2, 1, Qt.AlignmentFlag.AlignCenter)

        # === PANEL 3: BACKGROUND PIPELINE EXECUTION (Top-Right) ===
        self.panel_pipe = SciFiFrame("3. PIPELINE EXECUTION")
        pipe_layout = QVBoxLayout(self.panel_pipe)
        pipe_layout.setContentsMargins(10, 30, 10, 10)
        pipe_layout.setSpacing(6)

        # Antigravity Status Indicator
        ag_status_layout = QHBoxLayout()
        self.lbl_ag_tag = QLabel("BRIDGE:")
        self.lbl_ag_tag.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        self.lbl_ag_tag.setStyleSheet("color: #8ca0b8;")
        ag_status_layout.addWidget(self.lbl_ag_tag)

        self.badge_antigravity = QLabel("[ANTIGRAVITY: STANDBY]")
        self.badge_antigravity.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.badge_antigravity.setStyleSheet("color: #00e1ff; background: rgba(0, 225, 255, 20); border: 1px solid #00e1ff; padding: 2px 6px; border-radius: 2px;")
        ag_status_layout.addWidget(self.badge_antigravity)
        ag_status_layout.addStretch()
        pipe_layout.addLayout(ag_status_layout)

        self.txt_console = QTextEdit()
        self.txt_console.setReadOnly(True)
        pipe_layout.addWidget(self.txt_console)
        grid.addWidget(self.panel_pipe, 0, 2)

        # === PANEL 2: VOICE TRANSCRIPT (Bottom-Left) ===
        self.panel_voice = SciFiFrame("2. VOICE TRANSCRIPT")
        voice_layout = QVBoxLayout(self.panel_voice)
        voice_layout.setContentsMargins(10, 30, 10, 10)

        self.lbl_transcript = QLabel("USER > Awaiting voice activation command...")
        self.lbl_transcript.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.lbl_transcript.setWordWrap(True)
        self.lbl_transcript.setStyleSheet("color: #00e1ff; padding: 4px;")
        voice_layout.addWidget(self.lbl_transcript)
        voice_layout.addStretch()
        grid.addWidget(self.panel_voice, 1, 0)

        # === PANEL 4: JARVIS RESPONSE (Bottom-Right) ===
        self.panel_resp = SciFiFrame("4. JARVIS RESPONSE")
        resp_layout = QVBoxLayout(self.panel_resp)
        resp_layout.setContentsMargins(10, 30, 10, 10)

        self.lbl_response = QLabel("JARVIS > Neural speech and command system online, sir.")
        self.lbl_response.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self.lbl_response.setWordWrap(True)
        self.lbl_response.setStyleSheet("color: #00ff88; padding: 4px;")
        resp_layout.addWidget(self.lbl_response)
        resp_layout.addStretch()
        grid.addWidget(self.panel_resp, 1, 2)

        # Set column & row stretches
        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 4)
        grid.setColumnStretch(2, 3)
        grid.setRowStretch(0, 5)
        grid.setRowStretch(1, 5)

        main_layout.addLayout(grid)

        # Initial console greeting
        self.log_console("SYSTEM BOOT COMPLETED: Jarvis HUD Initialized.")
        self.log_console(f"ACTIVE WORKSPACE: {self.target_repo}")
        self.log_console(f"ACTIVE GIT BRANCH: {self.current_branch}")
        self.log_console(f"N8N AUTOMATION: {'ONLINE (http://localhost:5678)' if self.n8n_online else 'STANDBY'}")

    def log_console(self, msg: str, color: str = "#00ff88"):
        timestamp = time.strftime("[%H:%M:%S]")
        formatted = f"<span style='color:#00e1ff;'>{timestamp}</span> <span style='color:{color}; font-weight:bold;'>{msg}</span>"
        self.txt_console.append(formatted)

    def update_animations(self):
        # Update circular reactor & wave
        self.ai_core.advance()
        self.waveform.advance()

        # Pulse the [ACTIVE] badge
        pulse_alpha = int(25 + 20 * math.sin(time.time() * 4.0))
        self.badge_active.setStyleSheet(f"color: #00ff88; background: rgba(0, 255, 136, {pulse_alpha}); border: 1px solid #00ff88; padding: 3px 8px; border-radius: 2px;")

        # Typewriter effect for response label
        if self.typewriter_text and self.typewriter_idx <= len(self.typewriter_text):
            current = self.typewriter_text[:self.typewriter_idx]
            caret = "_" if (int(time.time() * 4) % 2 == 0) else " "
            self.lbl_response.setText(f"JARVIS > {current}{caret}")
            self.typewriter_idx += 2
        elif self.typewriter_text:
            self.lbl_response.setText(f"JARVIS > {self.typewriter_text}")

    def refresh_live_data(self):
        # Periodically refresh Git branch & n8n telemetry
        if time.time() - self.last_status_check > 2.0:
            self.last_status_check = time.time()
            self.current_branch = get_current_git_branch(self.target_repo)
            self.n8n_online = is_n8n_online()
            self.lbl_branch.setText(f"GIT BRANCH   : {self.current_branch}")
            self.lbl_n8n_pipe.setText(f"N8N ENGINE   : {'[ONLINE]' if self.n8n_online else '[STANDBY]'}")
            self.lbl_n8n_pipe.setStyleSheet("color: #00ff88;" if self.n8n_online else "color: #ff9d00;")
            self.badge_n8n.setText("[N8N: ONLINE]" if self.n8n_online else "[N8N: STANDBY]")
            self.badge_n8n.setStyleSheet("color: #00ff88; background: rgba(0, 255, 136, 25); border: 1px solid #00ff88; padding: 3px 8px; border-radius: 2px;" if self.n8n_online else "color: #ff9d00; background: rgba(255, 157, 0, 25); border: 1px solid #ff9d00; padding: 3px 8px; border-radius: 2px;")

        # 1. Update system resource telemetry
        if psutil:
            try:
                cpu = psutil.cpu_percent()
                mem = psutil.virtual_memory()
                self.lbl_cpu.setText(f"CPU USAGE    : {cpu:.1f}%")
                self.lbl_ram.setText(f"MEMORY ALLOC : {mem.percent:.1f}% ({mem.used // (1024*1024)}MB)")
            except Exception:
                pass

        # 2. Check Voice Transcript
        if os.path.exists(TRANSCRIPT_FILE):
            try:
                with open(TRANSCRIPT_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read().strip()
                if content and content != self.last_transcript_raw:
                    self.last_transcript_raw = content
                    caret = "_" if (int(time.time() * 3) % 2 == 0) else ""
                    self.lbl_transcript.setText(f"USER > \"{content}\"{caret}")
                    self.log_console(f"TRANSCRIPT RECEIVED: {content}", color="#00e1ff")
            except Exception:
                pass

        # 3. Check Intent & Response Data
        if os.path.exists(INTENT_FILE):
            try:
                with open(INTENT_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    data = json.load(f)

                # Check command execution
                cmd = data.get("command", "")
                action_type = data.get("type", data.get("action", ""))
                exec_status = data.get("execution_status", "")

                # For actions (git_action, antigravity_task), determine true response based on execution_status
                if action_type in ["git_action", "antigravity_task"]:
                    if exec_status == "failed":
                        resp = data.get("speaking_response", "Git operation failed, sir.")
                        self.lbl_response.setStyleSheet("color: #ff4444; padding: 4px;")
                    elif exec_status == "success":
                        resp = data.get("speaking_response", "Task completed successfully, sir.")
                        self.lbl_response.setStyleSheet("color: #00ff88; padding: 4px;")
                    else:
                        # Action pending or in progress: show start announcement, never premature success
                        resp = data.get("speaking_start") or f"Executing {data.get('task_description', 'action')}..."
                        self.lbl_response.setStyleSheet("color: #ff9d00; padding: 4px;")
                else:
                    # Query or direct QA: response is immediately authoritative
                    resp = data.get("speaking_response", data.get("speaking_start", ""))
                    self.lbl_response.setStyleSheet("color: #00ff88; padding: 4px;")

                if resp and resp != self.last_response_raw:
                    self.last_response_raw = resp
                    self.typewriter_text = resp
                    self.typewriter_idx = 0
                    self.log_console(f"ACTION [{action_type.upper()}]: {cmd if cmd else 'QA Query'}", color="#ff9d00")
                    if cmd:
                        # Parse subcommands (e.g., git add, git commit) for cyber display
                        for sub_cmd in cmd.split("&&"):
                            clean_sub = sub_cmd.strip()
                            if clean_sub.startswith("git") or clean_sub.startswith("gh"):
                                self.log_console(f">> EXECUTING: {clean_sub}", color="#00e1ff")
                            elif "cd " in clean_sub:
                                self.log_console(f">> WORKSPACE: {clean_sub}", color="#8ca0b8")
            except Exception:
                pass

        # 3b. Monitor Status File for real-time execution results
        if os.path.exists(STATUS_FILE):
            try:
                with open(STATUS_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    status_line = f.read().strip()
                if status_line and status_line != self.last_status_raw:
                    self.last_status_raw = status_line
                    if status_line.startswith("[GIT ERROR]") or status_line.startswith("[ERROR]"):
                        clean_err = status_line.replace("[GIT ERROR]", "").replace("[ERROR]", "").strip()
                        self.lbl_response.setStyleSheet("color: #ff4444; padding: 4px;")
                        self.typewriter_text = f"Git Error: {clean_err}"
                        self.typewriter_idx = 0
                        self.last_response_raw = self.typewriter_text
                        self.log_console(f"EXECUTION FAILED: {clean_err}", color="#ff4444")
                    elif status_line.startswith("[GIT SUCCESS]") or status_line.startswith("[SUCCESS]"):
                        clean_succ = status_line.replace("[GIT SUCCESS]", "").replace("[SUCCESS]", "").strip()
                        self.lbl_response.setStyleSheet("color: #00ff88; padding: 4px;")
                        self.typewriter_text = clean_succ
                        self.typewriter_idx = 0
                        self.last_response_raw = self.typewriter_text
                        self.log_console(f"EXECUTION SUCCESS: {clean_succ}", color="#00ff88")
            except Exception:
                pass

        # 4. Stream Antigravity Telemetry Logs to Panel 3
        if os.path.exists(ANTIGRAVITY_LOG_FILE):
            try:
                curr_size = os.path.getsize(ANTIGRAVITY_LOG_FILE)
                if curr_size > self.last_ag_log_size:
                    with open(ANTIGRAVITY_LOG_FILE, "r", encoding="utf-8", errors="ignore") as f:
                        f.seek(self.last_ag_log_size)
                        new_content = f.read()
                        self.last_ag_log_size = curr_size
                    for line in new_content.splitlines():
                        line_clean = line.strip()
                        if line_clean:
                            color = "#00e1ff" if "PASSED" in line_clean else ("#ff9d00" if "Reading" in line_clean or "AST" in line_clean else "#00ff88")
                            self.log_console(line_clean, color=color)
            except Exception:
                pass

        # 5. Monitor Antigravity Task Payload
        if os.path.exists(ANTIGRAVITY_TASK_FILE):
            try:
                with open(ANTIGRAVITY_TASK_FILE, "r", encoding="utf-8", errors="ignore") as f:
                    ag_task = json.load(f)
                status = ag_task.get("status", "")
                action = ag_task.get("action", "task").upper()
                target = ag_task.get("target_file", "")

                if status != self.last_ag_task_status:
                    self.last_ag_task_status = status
                    if status in ["pending", "in_progress", "dispatched"]:
                        self.badge_antigravity.setText(f"[ANTIGRAVITY: {action} // {target}]")
                        self.badge_antigravity.setStyleSheet("color: #ff9d00; background: rgba(255, 157, 0, 30); border: 1px solid #ff9d00; padding: 2px 6px; border-radius: 2px;")
                    elif status == "completed":
                        self.badge_antigravity.setText(f"[ANTIGRAVITY: {target} [SYS_OK]]")
                        self.badge_antigravity.setStyleSheet("color: #00ff88; background: rgba(0, 255, 136, 30); border: 1px solid #00ff88; padding: 2px 6px; border-radius: 2px;")
                    elif status == "failed":
                        self.badge_antigravity.setText(f"[ANTIGRAVITY: DEFECT DETECTED]")
                        self.badge_antigravity.setStyleSheet("color: #ff4444; background: rgba(255, 68, 68, 30); border: 1px solid #ff4444; padding: 2px 6px; border-radius: 2px;")
            except Exception:
                pass


def main():
    target_repo = None
    for i, a in enumerate(sys.argv):
        if a == "--project" and i + 1 < len(sys.argv):
            target_repo = sys.argv[i + 1]
            break
    app = QApplication(sys.argv)
    hud = JarvisHUD(target_repo=target_repo)
    hud.show()
    hud.raise_()
    hud.activateWindow()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
