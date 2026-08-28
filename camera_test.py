import sys
import cv2

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap, QFont
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFrame,
    QMessageBox,
    QComboBox,
    QSpinBox,
    QDialog,
    QFormLayout,
)


# =========================================================
# Camera Configuration
# =========================================================

CAMERA_1 = "/dev/video2"
CAMERA_2 = "/dev/video4"

WIDTH = 1280
HEIGHT = 720
FPS = 30


# =========================================================
# Options Dialog
# =========================================================

class OptionsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Camera Options")
        self.setMinimumWidth(350)

        layout = QFormLayout(self)

        self.resolution = QComboBox()
        self.resolution.addItems([
            "1280x720",
            "640x480",
            "640x360",
        ])

        self.fps = QSpinBox()
        self.fps.setRange(1, 60)
        self.fps.setValue(30)

        layout.addRow("Resolution:", self.resolution)
        layout.addRow("FPS:", self.fps)

        buttons = QHBoxLayout()

        ok = QPushButton("Apply")
        cancel = QPushButton("Cancel")

        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)

        buttons.addWidget(ok)
        buttons.addWidget(cancel)

        layout.addRow(buttons)


# =========================================================
# Camera Widget
# =========================================================

class CameraWidget(QFrame):

    def __init__(self, title, device):
        super().__init__()

        self.device = device
        self.cap = None

        self.title = title

        self.video = QLabel("Camera Offline")
        self.video.setAlignment(Qt.AlignCenter)
        self.video.setMinimumSize(400, 300)

        self.video.setStyleSheet("""
            QLabel {
                background: #111318;
                color: #888;
                border-radius: 12px;
                font-size: 20px;
            }
        """)

        self.info = QLabel(
            f"{device} • Offline"
        )

        self.info.setAlignment(Qt.AlignCenter)

        self.info.setStyleSheet("""
            QLabel {
                color: #aaaaaa;
                padding: 8px;
            }
        """)

        title_label = QLabel(title)

        title_label.setAlignment(Qt.AlignCenter)

        title_label.setFont(
            QFont("Sans", 16, QFont.Bold)
        )

        title_label.setStyleSheet("""
            color: white;
            padding: 8px;
        """)

        layout = QVBoxLayout(self)

        layout.addWidget(title_label)
        layout.addWidget(self.video, 1)
        layout.addWidget(self.info)

        self.setStyleSheet("""
            QFrame {
                background: #181a20;
                border: 1px solid #30333d;
                border-radius: 16px;
            }
        """)

    def start(self, width=1280, height=720, fps=30):

        self.stop()

        self.cap = cv2.VideoCapture(
            self.device,
            cv2.CAP_V4L2
        )

        if not self.cap.isOpened():

            self.video.setText(
                f"❌ Cannot open\n{self.device}"
            )

            self.info.setText(
                f"{self.device} • Offline"
            )

            return False

        # MJPEG
        self.cap.set(
            cv2.CAP_PROP_FOURCC,
            cv2.VideoWriter_fourcc(*"MJPG")
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_WIDTH,
            width
        )

        self.cap.set(
            cv2.CAP_PROP_FRAME_HEIGHT,
            height
        )

        self.cap.set(
            cv2.CAP_PROP_FPS,
            fps
        )

        real_width = int(
            self.cap.get(
                cv2.CAP_PROP_FRAME_WIDTH
            )
        )

        real_height = int(
            self.cap.get(
                cv2.CAP_PROP_FRAME_HEIGHT
            )
        )

        real_fps = self.cap.get(
            cv2.CAP_PROP_FPS
        )

        self.info.setText(
            f"{self.device} • "
            f"{real_width}x{real_height} • "
            f"{real_fps:.0f} FPS"
        )

        return True

    def update_frame(self):

        if self.cap is None:
            return

        ret, frame = self.cap.read()

        if not ret:
            self.video.setText(
                "❌ Camera read error"
            )
            return

        # BGR → RGB
        frame = cv2.cvtColor(
            frame,
            cv2.COLOR_BGR2RGB
        )

        h, w, ch = frame.shape

        image = QImage(
            frame.data,
            w,
            h,
            ch * w,
            QImage.Format_RGB888
        )

        pixmap = QPixmap.fromImage(image)

        pixmap = pixmap.scaled(
            self.video.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )

        self.video.setPixmap(pixmap)

    def stop(self):

        if self.cap is not None:

            self.cap.release()
            self.cap = None

        self.video.clear()

        self.video.setText(
            "Camera Offline"
        )

        self.info.setText(
            f"{self.device} • Offline"
        )


# =========================================================
# Main Window
# =========================================================

class MainWindow(QWidget):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "Dual Webcam Tester"
        )

        self.resize(1400, 850)

        # Camera widgets
        self.camera1 = CameraWidget(
            "WEBCAM 1",
            CAMERA_1
        )

        self.camera2 = CameraWidget(
            "WEBCAM 2",
            CAMERA_2
        )

        # Camera layout
        cameras = QHBoxLayout()

        cameras.addWidget(
            self.camera1
        )

        cameras.addWidget(
            self.camera2
        )

        # Buttons
        self.start_button = QPushButton(
            "▶ Start"
        )

        self.stop_button = QPushButton(
            "■ Stop"
        )

        self.capture_button = QPushButton(
            "📸 Capture"
        )

        self.options_button = QPushButton(
            "⚙ Options"
        )

        self.fullscreen_button = QPushButton(
            "⛶ Fullscreen"
        )

        # Button events
        self.start_button.clicked.connect(
            self.start_cameras
        )

        self.stop_button.clicked.connect(
            self.stop_cameras
        )

        self.capture_button.clicked.connect(
            self.capture_images
        )

        self.options_button.clicked.connect(
            self.open_options
        )

        self.fullscreen_button.clicked.connect(
            self.toggle_fullscreen
        )

        # Button layout
        buttons = QHBoxLayout()

        buttons.addWidget(
            self.start_button
        )

        buttons.addWidget(
            self.stop_button
        )

        buttons.addWidget(
            self.capture_button
        )

        buttons.addWidget(
            self.options_button
        )

        buttons.addWidget(
            self.fullscreen_button
        )

        # Main layout
        layout = QVBoxLayout(self)

        title = QLabel(
            "DUAL WEBCAM TESTER"
        )

        title.setAlignment(
            Qt.AlignCenter
        )

        title.setFont(
            QFont(
                "Sans",
                22,
                QFont.Bold
            )
        )

        title.setStyleSheet(
            "color: white; padding: 15px;"
        )

        layout.addWidget(title)
        layout.addLayout(cameras, 1)
        layout.addLayout(buttons)

        # Dark UI
        self.setStyleSheet("""
            QWidget {
                background: #101218;
                color: white;
            }

            QPushButton {
                background: #20232c;
                border: 1px solid #383c48;
                border-radius: 10px;
                padding: 12px 18px;
                color: white;
                font-size: 14px;
            }

            QPushButton:hover {
                background: #2b2f3a;
            }

            QPushButton:pressed {
                background: #15171d;
            }
        """)

        # Timer
        self.timer = QTimer()

        self.timer.timeout.connect(
            self.update_cameras
        )

    # -----------------------------------------------------
    # Start
    # -----------------------------------------------------

    def start_cameras(self):

        cam1 = self.camera1.start(
            WIDTH,
            HEIGHT,
            FPS
        )

        cam2 = self.camera2.start(
            WIDTH,
            HEIGHT,
            FPS
        )

        if not cam1 and not cam2:

            QMessageBox.critical(
                self,
                "Camera Error",
                "ไม่สามารถเปิด Webcam ทั้งสองตัวได้"
            )

            return

        self.timer.start(15)

    # -----------------------------------------------------
    # Stop
    # -----------------------------------------------------

    def stop_cameras(self):

        self.timer.stop()

        self.camera1.stop()
        self.camera2.stop()

    # -----------------------------------------------------
    # Update
    # -----------------------------------------------------

    def update_cameras(self):

        self.camera1.update_frame()
        self.camera2.update_frame()

    # -----------------------------------------------------
    # Capture
    # -----------------------------------------------------

    def capture_images(self):

        cameras = [
            (self.camera1, "camera1"),
            (self.camera2, "camera2"),
        ]

        for camera, name in cameras:

            if camera.cap is None:
                continue

            ret, frame = camera.cap.read()

            if ret:

                filename = (
                    f"{name}.jpg"
                )

                cv2.imwrite(
                    filename,
                    frame
                )

        QMessageBox.information(
            self,
            "Capture",
            "บันทึกภาพเรียบร้อยแล้ว"
        )

    # -----------------------------------------------------
    # Options
    # -----------------------------------------------------

    def open_options(self):

        dialog = OptionsDialog(self)

        if dialog.exec():

            text = dialog.resolution.currentText()

            width, height = map(
                int,
                text.split("x")
            )

            fps = dialog.fps.value()

            self.camera1.start(
                width,
                height,
                fps
            )

            self.camera2.start(
                width,
                height,
                fps
            )

    # -----------------------------------------------------
    # Fullscreen
    # -----------------------------------------------------

    def toggle_fullscreen(self):

        if self.isFullScreen():

            self.showNormal()

        else:

            self.showFullScreen()

    # -----------------------------------------------------
    # Close
    # -----------------------------------------------------

    def closeEvent(self, event):

        self.stop_cameras()

        event.accept()


# =========================================================
# Application
# =========================================================

app = QApplication(sys.argv)

window = MainWindow()

window.show()

sys.exit(
    app.exec()
)