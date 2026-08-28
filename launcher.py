"""MONGDEE AI Booth OS — Launcher.

A single window with buttons instead of terminal commands: open the booth,
the dashboard, or the AI trainer with one click. This is also the thing a
desktop shortcut / the built .exe (see BUILD.md) points at.

On a machine where the project's Python environment hasn't been set up yet,
this window itself still opens (its own dependency is just PySide6 — see
BUILD.md) and offers a "🔧 ติดตั้งระบบครั้งแรก" button that runs install.sh /
install.bat for you, streaming the output, before enabling the launch
buttons.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QProcess
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


def project_root() -> Path:
    """The folder that holds app.py/dashboard.py/trainer.py — computed relative
    to this script's own location so it works whether run as `python
    launcher.py` from source or as a frozen .exe placed at the project root
    (see build_windows.bat / build_linux.sh)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


ROOT = project_root()
IS_WINDOWS = sys.platform.startswith("win")
VENV_PYTHON = ROOT / (".venv/Scripts/python.exe" if IS_WINDOWS else ".venv/bin/python")
INSTALL_SCRIPT = ROOT / ("install.bat" if IS_WINDOWS else "install.sh")


class LauncherWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MONGDEE AI Booth OS — Launcher")
        self.resize(560, 620)
        icon_path = ROOT / "assets" / "icon.png"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.install_process: QProcess | None = None
        self._build_ui()
        self._refresh_ready_state()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("MONGDEE AI Booth OS")
        title.setFont(QFont("Sans", 18, QFont.Bold))
        root.addWidget(title)

        subtitle = QLabel("ระบบปฏิบัติการสำหรับบูธอัจฉริยะ — เลือกสิ่งที่ต้องการเปิด")
        subtitle.setStyleSheet("color: #999;")
        root.addWidget(subtitle)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("padding: 6px 0;")
        root.addWidget(self.status_label)

        self.setup_btn = QPushButton("🔧 ติดตั้งระบบครั้งแรก (First-time Setup)")
        self.setup_btn.clicked.connect(self._on_run_setup)
        root.addWidget(self.setup_btn)

        booth_box = QFrame()
        booth_box.setStyleSheet("QFrame { background: #181a20; border: 1px solid #30333d; border-radius: 10px; }")
        booth_layout = QVBoxLayout(booth_box)
        booth_layout.addWidget(QLabel("ตั้งค่าบูธ (แก้ไขได้ หรือปล่อยค่าเริ่มต้น)"))

        form_row1 = QHBoxLayout()
        self.booth_name_input = QLineEdit("MONGDEE Demo Booth")
        self.booth_name_input.setPlaceholderText("ชื่อบูธ")
        form_row1.addWidget(QLabel("ชื่อบูธ:"))
        form_row1.addWidget(self.booth_name_input)
        booth_layout.addLayout(form_row1)

        form_row2 = QHBoxLayout()
        self.event_id_input = QLineEdit("1-Day-at-IMPACT")
        self.event_id_input.setPlaceholderText("Event ID")
        form_row2.addWidget(QLabel("Event ID:"))
        form_row2.addWidget(self.event_id_input)
        booth_layout.addLayout(form_row2)

        form_row3 = QHBoxLayout()
        self.cameras_input = QLineEdit()
        self.cameras_input.setPlaceholderText("ปล่อยว่าง = ค้นหากล้องอัตโนมัติ (หรือระบุ เช่น /dev/video0,/dev/video2)")
        form_row3.addWidget(QLabel("กล้อง:"))
        form_row3.addWidget(self.cameras_input)
        booth_layout.addLayout(form_row3)

        root.addWidget(booth_box)

        self.booth_btn = QPushButton("🏬 เปิดบูธ (Start Booth)")
        self.booth_btn.clicked.connect(self._on_open_booth)
        root.addWidget(self.booth_btn)

        self.dashboard_btn = QPushButton("📊 เปิด Dashboard")
        self.dashboard_btn.clicked.connect(self._on_open_dashboard)
        root.addWidget(self.dashboard_btn)

        self.trainer_btn = QPushButton("🎓 เปิด AI Trainer")
        self.trainer_btn.clicked.connect(self._on_open_trainer)
        root.addWidget(self.trainer_btn)

        self.web_btn = QPushButton("🌐 เปิดผ่านเบราว์เซอร์ (ทุกฟีเจอร์ในหน้าเว็บเดียว)")
        self.web_btn.clicked.connect(self._on_open_web)
        root.addWidget(self.web_btn)

        root.addWidget(QLabel("บันทึกการติดตั้ง:"))
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(160)
        root.addWidget(self.log)

        self.setStyleSheet("""
            QWidget { background: #101218; color: white; }
            QPushButton { background: #20232c; border: 1px solid #383c48; border-radius: 10px;
                          padding: 12px; color: white; font-size: 14px; }
            QPushButton:hover { background: #2b2f3a; }
            QPushButton:disabled { color: #555; }
            QLineEdit, QTextEdit { background: #12141a; border: 1px solid #30333d; border-radius: 6px;
                                    color: white; padding: 4px 6px; }
        """)

    # -------------------------------------------------------------- state
    def _is_ready(self) -> bool:
        return VENV_PYTHON.exists()

    def _refresh_ready_state(self):
        ready = self._is_ready()
        for btn in (self.booth_btn, self.dashboard_btn, self.trainer_btn, self.web_btn):
            btn.setEnabled(ready)
        if ready:
            self.status_label.setText("✅ ระบบพร้อมใช้งาน")
            self.status_label.setStyleSheet("color: #2ecc71; padding: 6px 0;")
        else:
            self.status_label.setText(
                "⚠️ ยังไม่ได้ติดตั้งระบบ — กดปุ่ม \"ติดตั้งระบบครั้งแรก\" ด้านล่างก่อน "
                "(ใช้เวลาสักครู่ ต้องต่ออินเทอร์เน็ต)"
            )
            self.status_label.setStyleSheet("color: #f1c40f; padding: 6px 0;")

    # ----------------------------------------------------------- launching
    def _launch(self, script_name: str, extra_args: list[str] | None = None):
        if not self._is_ready():
            QMessageBox.warning(self, "ยังไม่พร้อม", "กรุณาติดตั้งระบบก่อน (ปุ่ม \"ติดตั้งระบบครั้งแรก\")")
            return
        script_path = ROOT / script_name
        args = [str(VENV_PYTHON), str(script_path)] + (extra_args or [])
        try:
            subprocess.Popen(args, cwd=str(ROOT))
        except Exception as exc:
            QMessageBox.critical(self, "เปิดไม่สำเร็จ", str(exc))

    def _on_open_booth(self):
        args = [
            "--booth-name", self.booth_name_input.text().strip() or "MONGDEE Demo Booth",
            "--event-id", self.event_id_input.text().strip() or "1-Day-at-IMPACT",
        ]
        cameras = self.cameras_input.text().strip()
        if cameras:
            args += ["--cameras", cameras]
        self._launch("app.py", args)

    def _on_open_dashboard(self):
        self._launch("dashboard.py")

    def _on_open_trainer(self):
        self._launch("trainer.py")

    def _on_open_web(self):
        args = [
            "--booth-name", self.booth_name_input.text().strip() or "MONGDEE Demo Booth",
            "--event-id", self.event_id_input.text().strip() or "1-Day-at-IMPACT",
        ]
        cameras = self.cameras_input.text().strip()
        if cameras:
            args += ["--cameras", cameras]
        self._launch("web_server.py", args)

    # -------------------------------------------------------------- setup
    def _on_run_setup(self):
        if not INSTALL_SCRIPT.exists():
            QMessageBox.critical(self, "ไม่พบตัวติดตั้ง", f"ไม่พบไฟล์ {INSTALL_SCRIPT.name}")
            return
        self.setup_btn.setEnabled(False)
        self.log.clear()
        self.log.append(f"กำลังรัน {INSTALL_SCRIPT.name} ... (อาจใช้เวลาหลายนาที)")

        self.install_process = QProcess(self)
        self.install_process.setWorkingDirectory(str(ROOT))
        if IS_WINDOWS:
            self.install_process.setProgram("cmd.exe")
            self.install_process.setArguments(["/c", str(INSTALL_SCRIPT)])
        else:
            self.install_process.setProgram("bash")
            self.install_process.setArguments([str(INSTALL_SCRIPT)])
        self.install_process.readyReadStandardOutput.connect(self._on_install_output)
        self.install_process.readyReadStandardError.connect(self._on_install_output)
        self.install_process.finished.connect(self._on_install_finished)
        self.install_process.start()

    def _on_install_output(self):
        if not self.install_process:
            return
        data = bytes(self.install_process.readAllStandardOutput()).decode("utf-8", "ignore")
        data += bytes(self.install_process.readAllStandardError()).decode("utf-8", "ignore")
        if data:
            self.log.append(data.rstrip())

    def _on_install_finished(self, exit_code, _status):
        self.setup_btn.setEnabled(True)
        if exit_code == 0:
            self.log.append("\n✅ ติดตั้งเสร็จสมบูรณ์")
        else:
            self.log.append(f"\n❌ ติดตั้งล้มเหลว (exit code {exit_code}) — ดู log ด้านบน")
        self._refresh_ready_state()


def main():
    app = QApplication(sys.argv)
    window = LauncherWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
