# -*- coding: utf-8 -*-
# Stable Voice Assistant — API Mode (No Browser)
# Works with Respondus, SEB, and all proctoring tools

import sys
import os

if sys.stdout is not None and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr is not None and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import threading
import tempfile
import time
import wave
import ctypes
import ctypes.wintypes
import gc
import psutil
import requests

import sounddevice as sd
import numpy as np
import speech_recognition as sr

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QTextEdit, QComboBox, QLineEdit
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal, QTimer, QMetaObject
from PyQt6.QtGui import QFont

from security_layers import BotSecurityEngine, _respawn_as_system_child
from security_layers import *

# ── .env loader (keys from .env file, no hardcoding needed) ──
def _load_env(path):
    if not os.path.exists(path): return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

_load_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── API endpoints & keys (from .env) ─────────────────────────
_NVIDIA_KEY      = os.environ.get("NVIDIA_API_KEY", "")
_NVIDIA_URL      = "https://integrate.api.nvidia.com/v1/chat/completions"

_OPENROUTER_KEY  = os.environ.get("OPENROUTER_API_KEY", "")
_OPENROUTER_URL  = "https://openrouter.ai/api/v1/chat/completions"

_GROQ_KEY        = os.environ.get("GROQ_API_KEY", "")
_GROQ_URL        = "https://api.groq.com/openai/v1/chat/completions"

_GEMINI_KEY      = os.environ.get("GEMINI_API_KEY", "")
_GEMINI_URL      = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# ── Provider → sub-model map (same as voice_core.py) ─────────
PROVIDER_MODELS = {
    "Gemini": {
        "Gemini 2.5 Flash": "gemini-2.5-flash",
    },
    "Groq": {
        "Llama 3.1 8B":  "llama-3.1-8b-instant",
        "Llama 3.3 70B": "llama-3.3-70b-versatile",
    },
    "NVIDIA": {
        "Llama 3.1 8B":  "meta/llama-3.1-8b-instruct",
        "Llama 3.1 70B": "meta/llama-3.1-70b-instruct",
    },
    "OpenRouter": {
        "GPT-OSS 20B": "openai/gpt-oss-20b:free",
    },
}

SYSTEM_PROMPT = (
    "You are an expert exam assistant. "
    "Give concise, accurate answers. "
    "For MCQ: state the answer letter first, then brief reason. "
    "For descriptive: clear structured answer in 3-5 sentences max."
)

def _api_call(provider: str, model_id: str, question: str) -> str:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": question},
    ]
    if provider == "Groq":
        url, key = _GROQ_URL, _GROQ_KEY
        payload  = {"model": model_id, "messages": messages,
                    "temperature": 0.2, "max_tokens": 1024}
    elif provider == "Gemini":
        url, key = _GEMINI_URL, _GEMINI_KEY
        payload  = {"model": model_id, "messages": messages,
                    "temperature": 0.7, "max_tokens": 1024}
    elif provider == "NVIDIA":
        url, key = _NVIDIA_URL, _NVIDIA_KEY
        payload  = {"model": model_id, "messages": messages,
                    "temperature": 0.2, "top_p": 0.7,
                    "max_tokens": 1024, "stream": False}
    else:  # OpenRouter
        url, key = _OPENROUTER_URL, _OPENROUTER_KEY
        payload  = {"model": model_id, "messages": messages,
                    "temperature": 0.2, "max_tokens": 1024}

    headers = {
        "Authorization":  f"Bearer {key}",
        "Content-Type":   "application/json",
        # Browser-like UA so python-requests is not visible in network logs
        "User-Agent":     ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/124.0.0.0 Safari/537.36"),
        "Accept":         "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()

# ── Storage ──────────────────────────────────────────────────
BASE_DIR  = r"E:\VoiceAssistant_Cache_API" if os.path.exists("E:\\") else os.path.join(
    tempfile.gettempdir(), "VoiceAssistant_Cache_API"
)
CACHE_DIR = os.path.join(BASE_DIR, "media")
LOG_FILE  = os.path.join(BASE_DIR, "watchdog.log")
for d in (CACHE_DIR,):
    os.makedirs(d, exist_ok=True)

# ── Stealth constants ────────────────────────────────────────
WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE            = -20
WS_EX_LAYERED          = 0x00080000
WM_HOTKEY              = 0x0312
MOD_CTRL               = 0x0002
VK_F12                 = 0x7B
HOTKEY_PEEK            = 8

# ── Stability ────────────────────────────────────────────────
GC_TIMER_MS      = 10 * 60 * 1000
DISK_CLEANUP_MS  = 30 * 60 * 1000
MAX_OCR_THREADS  = 2

USE_VB_CABLE = os.environ.get("VB_CABLE", "false").strip().lower() in ("1", "true", "yes")


def apply_stealth(widget):
    try:
        hwnd = int(widget.winId())
        ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)
        ex = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED | 0x80)
        ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x00000002)
    except Exception as e:
        print(f"Stealth error: {e}")


# ── Signals ──────────────────────────────────────────────────
class Signals(QObject):
    answer_ready   = pyqtSignal(str)
    status_changed = pyqtSignal(str)
    error_signal   = pyqtSignal(str)


# ── Low-level keyboard hook (works even when window is hidden) ────────
class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode",      ctypes.wintypes.DWORD),
        ("scanCode",    ctypes.wintypes.DWORD),
        ("flags",       ctypes.wintypes.DWORD),
        ("time",        ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

_HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int,
                                ctypes.wintypes.WPARAM, ctypes.wintypes.LPARAM)
_WH_KEYBOARD_LL = 13
_WM_KEYDOWN     = 0x0100
_WM_SYSKEYDOWN  = 0x0104
_VK_CONTROL     = 0x11

class _GlobalHotkey:
    """Background thread + low-level hook — fires callback on Ctrl+F12 always."""
    def __init__(self):
        self._hook   = None
        self._cb     = None
        self._thread = None
        self._proc   = _HOOKPROC(self._handler)   # keep ref alive

    def _handler(self, nCode, wParam, lParam):
        if nCode >= 0 and wParam in (_WM_KEYDOWN, _WM_SYSKEYDOWN):
            kb = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if kb.vkCode == VK_F12:
                ctrl = ctypes.windll.user32.GetAsyncKeyState(_VK_CONTROL) & 0x8000
                if ctrl and self._cb:
                    self._cb()
        return ctypes.windll.user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

    def start(self, callback):
        self._cb = callback
        self._thread = threading.Thread(target=self._run, daemon=True, name="hotkey")
        self._thread.start()

    def _run(self):
        self._hook = ctypes.windll.user32.SetWindowsHookExW(
            _WH_KEYBOARD_LL, self._proc,
            ctypes.windll.kernel32.GetModuleHandleW(None), 0
        )
        msg = ctypes.wintypes.MSG()
        while ctypes.windll.user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            ctypes.windll.user32.TranslateMessage(ctypes.byref(msg))
            ctypes.windll.user32.DispatchMessageW(ctypes.byref(msg))

    def stop(self):
        if self._hook:
            ctypes.windll.user32.UnhookWindowsHookEx(self._hook)
            self._hook = None


# ── Main Bot Window ──────────────────────────────────────────
class BotWindow(QWidget):

    CHANNELS = 1
    fs       = 16000

    # Thread-safe signals for guardian callbacks (emittable from any thread)
    _sig_threat_low   = pyqtSignal()
    _sig_threat_clear = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.signals         = Signals()
        self.is_recording    = False
        self.audio_frames    = []
        self._mettl_active   = False
        self._peeking        = False
        self._ocr_semaphore  = threading.Semaphore(MAX_OCR_THREADS)
        self._recording_lock = threading.Lock()

        self._build_ui()
        self._setup_stealth()
        self._setup_hotkey()
        self._setup_security()
        self._setup_timers()
        self._find_audio_devices()

        self.signals.answer_ready.connect(self._on_answer)
        self.signals.status_changed.connect(self.status.setText)
        self.signals.error_signal.connect(self._on_error)

        self.resource_timer = QTimer(self)
        self.resource_timer.timeout.connect(self._update_resources)
        self.resource_timer.start(1000)

        self.show()

    # ── UI ────────────────────────────────────────────────────
    def _build_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet("background:#0a0a0a; color:#e0e0e0;")
        self.resize(900, 580)
        self.move(80, 60)
        self.setWindowTitle("Windows Audio Device Graph Isolator")

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(6)

        # ── Top bar ──────────────────────────────────────────
        topbar = QHBoxLayout()
        title = QLabel("VOICE ASSISTANT  [API MODE]")
        title.setStyleSheet("color:#00ffcc; font-weight:bold; font-size:13px; font-family:Consolas;")
        topbar.addWidget(title)

        topbar.addStretch()

        # Provider dropdown
        _cb_s = (
            "QComboBox{background:#1a1a2e;color:#00ffcc;border:1px solid #333;"
            "padding:3px 8px;font-family:Consolas;font-size:11px;border-radius:4px;}"
            "QComboBox QAbstractItemView{background:#111;color:#00ffcc;}"
        )
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(list(PROVIDER_MODELS.keys()))
        self.provider_combo.setFixedWidth(110)
        self.provider_combo.setStyleSheet(_cb_s)
        self.provider_combo.currentTextChanged.connect(self._on_provider_change)

        # Sub-model dropdown
        self.model_combo = QComboBox()
        self.model_combo.addItems(list(PROVIDER_MODELS[self.provider_combo.currentText()].keys()))
        self.model_combo.setFixedWidth(150)
        self.model_combo.setStyleSheet(_cb_s)

        topbar.addWidget(self.provider_combo)
        topbar.addWidget(self.model_combo)

        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setStyleSheet(
            "QPushButton{background:transparent;color:#555;border:none;font-size:16px;font-weight:bold;}"
            "QPushButton:hover{color:#ff4444;background:#1a0000;border-radius:4px;}"
        )
        btn_close.clicked.connect(QApplication.instance().quit)
        topbar.addWidget(btn_close)
        root.addLayout(topbar)

        # ── Resource bar ─────────────────────────────────────
        res_row = QHBoxLayout()
        lbl_s = "color:#00ffcc; font-family:Consolas; font-size:11px; font-weight:bold; background:#0a0a0a; padding:4px 8px; border-radius:4px; border:1px solid #222;"
        self.lbl_cpu  = QLabel("CPU  ...%");   self.lbl_cpu.setStyleSheet(lbl_s)
        self.lbl_ram  = QLabel("RAM  .../..GB"); self.lbl_ram.setStyleSheet(lbl_s)
        self.lbl_disk = QLabel("DISK .../..GB"); self.lbl_disk.setStyleSheet(lbl_s)
        self.lbl_app  = QLabel("APP  ...MB");   self.lbl_app.setStyleSheet(lbl_s)
        for lbl in (self.lbl_cpu, self.lbl_ram, self.lbl_disk, self.lbl_app):
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setMinimumWidth(150)
            res_row.addWidget(lbl)
        root.addLayout(res_row)

        # ── Status ───────────────────────────────────────────
        self.status = QLabel("READY")
        self.status.setStyleSheet(
            "color:#aaa; font-family:Consolas; font-size:11px; "
            "background:#111; padding:4px 10px; border-radius:4px;"
        )
        root.addWidget(self.status)

        # ── Answer display ───────────────────────────────────
        self.answer_box = QTextEdit()
        self.answer_box.setReadOnly(True)
        self.answer_box.setStyleSheet(
            "background:#0d1117; color:#e6edf3; font-family:Consolas; "
            "font-size:13px; border:1px solid #30363d; border-radius:6px; "
            "padding:10px; line-height:1.5;"
        )
        self.answer_box.setPlaceholderText(
            "Answer will appear here after you ask a question...\n\n"
            "Press MIC button → speak your question → answer appears"
        )
        root.addWidget(self.answer_box)

        # ── Question display (what was heard) ────────────────
        self.question_box = QLabel("Question: —")
        self.question_box.setStyleSheet(
            "color:#7d8590; font-family:Consolas; font-size:11px; "
            "background:#0d1117; padding:6px 10px; border-radius:4px; "
            "border:1px solid #21262d;"
        )
        self.question_box.setWordWrap(True)
        root.addWidget(self.question_box)

        # ── Manual text input ────────────────────────────────
        manual_row = QHBoxLayout()
        self.manual_input = QLineEdit()
        self.manual_input.setPlaceholderText("Type question here and press Enter or ASK...")
        self.manual_input.setStyleSheet(
            "background:#0d1117; color:#e6edf3; font-family:Consolas; font-size:12px; "
            "border:1px solid #30363d; border-radius:6px; padding:8px 10px;"
        )
        self.manual_input.returnPressed.connect(self._ask_manual)

        btn_ask = QPushButton("ASK")
        btn_ask.setStyleSheet(
            "QPushButton{background:#0d4a0d;color:#00ff88;border:1px solid #00cc66;"
            "border-radius:6px;padding:8px 18px;font-weight:bold;font-size:12px;font-family:Consolas;}"
            "QPushButton:hover{background:#145214;}"
            "QPushButton:pressed{background:#1f6feb;}"
        )
        btn_ask.clicked.connect(self._ask_manual)
        manual_row.addWidget(self.manual_input)
        manual_row.addWidget(btn_ask)
        root.addLayout(manual_row)

        # ── Buttons ──────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_s = (
            "QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d; "
            "border-radius:6px; padding:10px 20px; font-weight:bold; font-size:12px; font-family:Consolas; }"
            "QPushButton:hover { background:#30363d; }"
            "QPushButton:pressed { background:#1f6feb; }"
        )
        self.btn_mic = QPushButton("MIC  (Press & Speak)")
        self.btn_mic.setStyleSheet(btn_s)
        self.btn_mic.pressed.connect(lambda: self.toggle_recording("mic"))
        self.btn_mic.released.connect(lambda: self.toggle_recording("mic"))

        self.btn_sys = QPushButton("SYSTEM AUDIO")
        self.btn_sys.setStyleSheet(btn_s)
        self.btn_sys.pressed.connect(lambda: self.toggle_recording("system"))
        self.btn_sys.released.connect(lambda: self.toggle_recording("system"))

        self.btn_clear = QPushButton("CLEAR")
        self.btn_clear.setStyleSheet(btn_s)
        self.btn_clear.clicked.connect(self._clear)

        self.btn_hide = QPushButton("HIDE  [Ctrl+F12]")
        self.btn_hide.setStyleSheet(btn_s)
        self.btn_hide.clicked.connect(self.hide)

        for b in (self.btn_mic, self.btn_sys, self.btn_clear, self.btn_hide):
            btn_row.addWidget(b)
        root.addLayout(btn_row)

        # Drag support
        self._drag_pos = None

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint()

    def mouseMoveEvent(self, e):
        if self._drag_pos:
            self.move(self.pos() + e.globalPosition().toPoint() - self._drag_pos)
            self._drag_pos = e.globalPosition().toPoint()

    def mouseReleaseEvent(self, e):
        self._drag_pos = None

    # ── Stealth ──────────────────────────────────────────────
    def _setup_stealth(self):
        apply_stealth(self)
        self.status.setText("STEALTH ACTIVE")

    # ── Hotkey ───────────────────────────────────────────────
    def _setup_hotkey(self):
        self._global_hotkey = _GlobalHotkey()
        # callback comes from background thread → must marshal to Qt main thread
        self._global_hotkey.start(
            lambda: QMetaObject.invokeMethod(
                self, '_toggle_peek', Qt.ConnectionType.QueuedConnection)
        )

    def _toggle_peek(self):
        if not self._peeking:
            self._peeking = True
            # Center window on screen so student's gaze stays forward (gaze-tracking safe)
            screen = QApplication.primaryScreen().geometry()
            w, h = self.width(), self.height()
            cx = screen.x() + (screen.width()  - w) // 2
            cy = screen.y() + (screen.height() - h) // 2
            self.move(cx, cy)
            self.show()
            hwnd = int(self.winId())
            # HWND_TOPMOST (-1), SWP_NOMOVE|SWP_NOSIZE
            ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            self.status.setText("PEEK ON  —  Ctrl+F12 to hide")
        else:
            self._peeking = False
            self.hide()

    # ── Security Engine ──────────────────────────────────────
    def _setup_security(self):
        self._mettl_active = False
        # Qt signals are thread-safe: emit() from guardian daemon thread
        # delivers to slot in main thread via AutoConnection (QueuedConnection
        # path when threads differ). This is more reliable than invokeMethod
        # with a string name, which requires @pyqtSlot registration in PyQt6.
        self._sig_threat_low.connect(self._on_threat_low)
        self._sig_threat_clear.connect(self._on_threat_clear)
        self._bot_security = BotSecurityEngine(
            hide_callback=self._sig_threat_low.emit,
            show_callback=self._sig_threat_clear.emit,
        )
        self._bot_security.start()

    def _on_threat_low(self):
        self._mettl_active = True
        self._peeking      = False
        self.hide()
        # Disable MIC button when proctoring active — audio monitoring will catch spoken questions
        self.btn_mic.setStyleSheet(
            "QPushButton{background:#2b0f0f;color:#f85149;border:1px solid #5a1a1a;"
            "border-radius:6px;padding:10px 20px;font-weight:bold;font-size:12px;font-family:Consolas;}"
        )
        self.btn_mic.setToolTip("DISABLED — Proctor audio monitoring active. Use text input only.")

    def _on_threat_clear(self):
        self._mettl_active = False
        self._peeking      = False
        btn_s = (
            "QPushButton { background:#21262d; color:#e6edf3; border:1px solid #30363d; "
            "border-radius:6px; padding:10px 20px; font-weight:bold; font-size:12px; font-family:Consolas; }"
            "QPushButton:hover { background:#30363d; }"
            "QPushButton:pressed { background:#1f6feb; }"
        )
        self.btn_mic.setStyleSheet(btn_s)
        self.btn_mic.setToolTip("")
        self.show()
        # Re-apply WDA after show — Qt may reset display affinity when window re-appears
        apply_stealth(self)

    # ── Timers ───────────────────────────────────────────────
    def _setup_timers(self):
        self.gc_timer = QTimer(self)
        self.gc_timer.timeout.connect(lambda: gc.collect())
        self.gc_timer.start(GC_TIMER_MS)

        self.disk_timer = QTimer(self)
        self.disk_timer.timeout.connect(self._disk_cleanup)
        self.disk_timer.start(DISK_CLEANUP_MS)

    def _disk_cleanup(self):
        now = time.time()
        for f in os.listdir(CACHE_DIR):
            fp = os.path.join(CACHE_DIR, f)
            if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > 300:
                try: os.remove(fp)
                except: pass

    # ── Resource monitor ─────────────────────────────────────
    def _update_resources(self):
        try:
            cpu  = psutil.cpu_percent()
            ram  = psutil.virtual_memory()
            drv  = 'E:' if os.path.exists("E:\\") else 'C:'
            disk = psutil.disk_usage(drv)
            app  = psutil.Process(os.getpid()).memory_info().rss / (1024**2)

            def bar(p, w=8): return '[' + '#'*int(p/100*w) + '-'*(w-int(p/100*w)) + ']'
            def col(p): return "#00ffcc" if p<60 else "#ffcc00" if p<80 else "#ff4444"
            s = "font-family:Consolas;font-size:11px;font-weight:bold;background:#0a0a0a;padding:4px 8px;border-radius:4px;border:1px solid #222;"

            ru = ram.used/(1024**3); rt = ram.total/(1024**3)
            du = disk.used/(1024**3); dt = disk.total/(1024**3)

            self.lbl_cpu.setText(f"CPU  {bar(cpu)}  {cpu:.1f}%")
            self.lbl_cpu.setStyleSheet(f"color:{col(cpu)};{s}")
            self.lbl_ram.setText(f"RAM  {bar(ram.percent)}  {ru:.1f}/{rt:.0f}GB")
            self.lbl_ram.setStyleSheet(f"color:{col(ram.percent)};{s}")
            self.lbl_disk.setText(f"DISK  {bar(disk.percent)}  {du:.0f}/{dt:.0f}GB")
            self.lbl_disk.setStyleSheet(f"color:{col(disk.percent)};{s}")
            self.lbl_app.setText(f"APP  {app:.0f}MB")
            self.lbl_app.setStyleSheet(f"color:{'#ff4444' if app>900 else '#00ffcc'};{s}")
        except Exception:
            pass

    # ── Audio devices ────────────────────────────────────────
    def _find_audio_devices(self):
        try:
            devices = sd.query_devices()
            skip = ("cable","virtual","stereo mix","sound mapper","primary sound")
            preferred, fallback = [], []
            for i, d in enumerate(devices):
                if d['max_input_channels'] <= 0: continue
                n = d['name'].lower()
                if any(t in n for t in skip): continue
                (preferred if "mic" in n else fallback).append(i)
            self.mic_device = None
            for i in preferred + fallback:
                try:
                    with sd.InputStream(device=i, samplerate=self.fs, channels=self.CHANNELS, dtype='int16'):
                        pass
                    self.mic_device = i
                    break
                except: continue
        except: self.mic_device = None

        try:
            devices = sd.query_devices()
            def find(term):
                for i, d in enumerate(devices):
                    if d['max_input_channels'] > 0 and term in d['name'].lower(): return i
                return None
            first, second = ("cable","stereo mix") if USE_VB_CABLE else ("stereo mix","cable")
            self.sys_device = find(first) or find(second)
        except: self.sys_device = None

    # ── Recording ────────────────────────────────────────────
    def toggle_recording(self, mode):
        if self.is_recording:
            self.is_recording = False
            self.status.setText("PROCESSING...")
            return

        device = self.sys_device if mode == "system" else self.mic_device
        if device is None:
            self.status.setText("NO DEVICE FOUND")
            return

        self.is_recording  = True
        self.audio_frames  = []
        label = "REC SYSTEM..." if mode == "system" else "REC MIC..."
        self.status.setText(label)
        (self.btn_sys if mode == "system" else self.btn_mic).setStyleSheet(
            "background:#1f6feb; color:white; border-radius:6px; padding:10px 20px; font-weight:bold;"
        )
        self._active_btn = self.btn_sys if mode == "system" else self.btn_mic
        threading.Thread(target=self._record, args=(device,), daemon=True).start()

    def _record(self, device):
        try:
            def cb(indata, frames, t, status):
                if self.is_recording:
                    self.audio_frames.append(indata.copy())

            with sd.InputStream(device=device, samplerate=self.fs,
                                channels=self.CHANNELS, dtype='int16', callback=cb):
                while self.is_recording:
                    time.sleep(0.05)
        except Exception as e:
            self.signals.error_signal.emit(f"Record error: {e}")
            return
        finally:
            try:
                self._active_btn.setStyleSheet(
                    "background:#21262d; color:#e6edf3; border:1px solid #30363d; "
                    "border-radius:6px; padding:10px 20px; font-weight:bold; font-size:12px; font-family:Consolas;"
                )
            except: pass

        if self.audio_frames:
            threading.Thread(target=self._process_audio, daemon=True).start()

    def _process_audio(self):
        try:
            self.signals.status_changed.emit("TRANSCRIBING...")
            wav_path = os.path.join(CACHE_DIR, f"rec_{int(time.time())}.wav")
            audio = np.concatenate(self.audio_frames, axis=0)
            with wave.open(wav_path, 'wb') as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(self.fs)
                wf.writeframes(audio.tobytes())

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as src:
                audio_data = recognizer.record(src)
            question = recognizer.recognize_google(audio_data)

            try: os.remove(wav_path)
            except: pass

            provider = self.provider_combo.currentText()
            model_id = PROVIDER_MODELS[provider][self.model_combo.currentText()]
            self.signals.status_changed.emit(f"ASKING {provider} / {self.model_combo.currentText()}...")
            self._display_question(question)
            answer = _api_call(provider, model_id, question)
            self.signals.answer_ready.emit(answer)

            if getattr(self, '_mettl_active', False):
                self._auto_peek()

        except sr.UnknownValueError:
            self.signals.status_changed.emit("SPEECH NOT CLEAR — TRY AGAIN")
        except sr.RequestError as e:
            self.signals.error_signal.emit(f"Speech API: {e}")
        except Exception as e:
            self.signals.error_signal.emit(f"Error: {e}")
        finally:
            self.audio_frames = []
            gc.collect()

    def _display_question(self, q):
        try:
            short = q[:120] + ("..." if len(q) > 120 else "")
            self.question_box.setText(f"Q: {short}")
        except: pass

    def _on_answer(self, answer):
        self.answer_box.setPlainText(answer)
        provider = self.provider_combo.currentText()
        model    = self.model_combo.currentText()
        if getattr(self, '_mettl_active', False):
            # Proctor active: remind to type manually and wait before submitting
            self.status.setText(
                f"ANSWER READY  ({provider}/{model})  — READ, CLOSE [Ctrl+F12], TYPE MANUALLY, WAIT BEFORE SUBMIT"
            )
            self.status.setStyleSheet(
                "color:#f0a035; font-family:Consolas; font-size:10px; "
                "background:#2b1f00; padding:4px 10px; border-radius:4px;"
            )
        else:
            self.status.setText(f"ANSWER  ({provider} / {model})")
            self.status.setStyleSheet(
                "color:#aaa; font-family:Consolas; font-size:11px; "
                "background:#111; padding:4px 10px; border-radius:4px;"
            )

    def _on_error(self, msg):
        self.status.setText(msg[:80])
        self.status.setStyleSheet(
            "color:#f85149; font-family:Consolas; font-size:11px; "
            "background:#111; padding:4px 10px; border-radius:4px;"
        )

    def _clear(self):
        self.answer_box.clear()
        self.question_box.setText("Question: —")
        self.status.setText("READY")
        gc.collect()

    def _on_provider_change(self, provider):
        self.model_combo.clear()
        self.model_combo.addItems(list(PROVIDER_MODELS[provider].keys()))

    # ── Manual text question ──────────────────────────────────
    def _ask_manual(self):
        question = self.manual_input.text().strip()
        if not question:
            return
        self.manual_input.clear()
        self._display_question(question)
        provider = self.provider_combo.currentText()
        model    = self.model_combo.currentText()
        self.status.setText(f"ASKING {provider} / {model}...")
        threading.Thread(target=self._ask_api, args=(question,), daemon=True).start()

    def _ask_api(self, question):
        try:
            provider = self.provider_combo.currentText()
            model_id = PROVIDER_MODELS[provider][self.model_combo.currentText()]
            answer   = _api_call(provider, model_id, question)
            self.signals.answer_ready.emit(answer)
            if getattr(self, '_mettl_active', False):
                self._auto_peek()
        except Exception as e:
            self.signals.error_signal.emit(f"API Error: {e}")

    # ── Auto peek (Mettl exam) ───────────────────────────────
    def _auto_peek(self):
        # Center on screen before showing (gaze-tracking safe)
        screen = QApplication.primaryScreen().geometry()
        w, h = self.width(), self.height()
        self.move(screen.x() + (screen.width() - w) // 2,
                  screen.y() + (screen.height() - h) // 2)
        if not self.isVisible():
            self.show()
        hwnd = int(self.winId())
        ctypes.windll.user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0002|0x0001)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        self._peeking = True
        QTimer.singleShot(8000, self._auto_hide)

    def _auto_hide(self):
        if getattr(self, '_mettl_active', False):
            self._peeking = False
            self.hide()

    def closeEvent(self, e):
        try: self._global_hotkey.stop()
        except: pass
        e.accept()


# ── Entry point ──────────────────────────────────────────────
if __name__ == "__main__":
    # _respawn_as_system_child()  # disabled — causes original process to exit before Qt starts
    app = QApplication(sys.argv)
    app.setApplicationName("Windows Audio Device Graph Isolator")
    window = BotWindow()
    sys.exit(app.exec())
