import cv2
import time
import numpy as np
from ultralytics import YOLO


# =========================================================
# CONFIGURATION
# =========================================================

CAMERA_1 = "/dev/video2"
CAMERA_2 = "/dev/video4"

CAMERA_WIDTH = 640
CAMERA_HEIGHT = 360
CAMERA_FPS = 30

DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 360

CONFIDENCE = 0.45

# YOLO จะตรวจทุกกี่ frame
# 1 = ตรวจทุก frame
# 2 = ตรวจทุก 2 frame
# 3 = ตรวจทุก 3 frame
DETECT_EVERY = 1

MODEL_NAME = "yolo11n.pt"


# =========================================================
# LOAD YOLO
# =========================================================

print("=" * 60)
print("        DUAL WEBCAM AI DETECTION")
print("=" * 60)

print("[AI] Loading YOLO model...")

model = YOLO(MODEL_NAME)

# ---------------------------------------------------------
# Detect CUDA
# ---------------------------------------------------------

try:
    import torch

    if torch.cuda.is_available():

        DEVICE = 0

        print(
            "[GPU] CUDA available:"
        )

        print(
            f"[GPU] {torch.cuda.get_device_name(0)}"
        )

    else:

        DEVICE = "cpu"

        print(
            "[GPU] CUDA not available"
        )

        print(
            "[GPU] Using CPU"
        )

except Exception:

    DEVICE = "cpu"

    print(
        "[GPU] PyTorch CUDA check failed"
    )

    print(
        "[GPU] Using CPU"
    )


print(
    f"[AI] Device: {DEVICE}"
)

print(
    f"[AI] Model: {MODEL_NAME}"
)

print(
    f"[AI] Confidence: {CONFIDENCE}"
)

print("=" * 60)


# =========================================================
# OPEN CAMERA
# =========================================================

def open_camera(device):

    print(
        f"[CAMERA] Opening {device}..."
    )

    cap = cv2.VideoCapture(
        device,
        cv2.CAP_V4L2
    )

    if not cap.isOpened():

        print(
            f"[ERROR] Cannot open {device}"
        )

        return None


    # -----------------------------------------------------
    # MJPEG
    # -----------------------------------------------------

    cap.set(
        cv2.CAP_PROP_FOURCC,
        cv2.VideoWriter_fourcc(
            *"MJPG"
        )
    )


    # -----------------------------------------------------
    # Resolution
    # -----------------------------------------------------

    cap.set(
        cv2.CAP_PROP_FRAME_WIDTH,
        CAMERA_WIDTH
    )

    cap.set(
        cv2.CAP_PROP_FRAME_HEIGHT,
        CAMERA_HEIGHT
    )


    # -----------------------------------------------------
    # FPS
    # -----------------------------------------------------

    cap.set(
        cv2.CAP_PROP_FPS,
        CAMERA_FPS
    )


    # -----------------------------------------------------
    # Buffer
    # -----------------------------------------------------

    cap.set(
        cv2.CAP_PROP_BUFFERSIZE,
        1
    )


    # -----------------------------------------------------
    # Read actual settings
    # -----------------------------------------------------

    actual_width = int(
        cap.get(
            cv2.CAP_PROP_FRAME_WIDTH
        )
    )

    actual_height = int(
        cap.get(
            cv2.CAP_PROP_FRAME_HEIGHT
        )
    )

    actual_fps = cap.get(
        cv2.CAP_PROP_FPS
    )


    print(
        f"[CAMERA] {device}"
    )

    print(
        f"         Resolution: "
        f"{actual_width}x{actual_height}"
    )

    print(
        f"         FPS: {actual_fps:.1f}"
    )


    return cap


# =========================================================
# OPEN BOTH CAMERAS
# =========================================================

cam1 = open_camera(
    CAMERA_1
)

cam2 = open_camera(
    CAMERA_2
)


if cam1 is None:

    print(
        f"[WARNING] Camera 1 unavailable: "
        f"{CAMERA_1}"
    )


if cam2 is None:

    print(
        f"[WARNING] Camera 2 unavailable: "
        f"{CAMERA_2}"
    )


if cam1 is None and cam2 is None:

    print(
        "[ERROR] No cameras available."
    )

    raise SystemExit


# =========================================================
# WINDOW
# =========================================================

WINDOW_NAME = (
    "Dual Webcam AI Detection"
)

cv2.namedWindow(
    WINDOW_NAME,
    cv2.WINDOW_NORMAL
)

cv2.resizeWindow(
    WINDOW_NAME,
    DISPLAY_WIDTH * 2,
    DISPLAY_HEIGHT
)


# =========================================================
# PLACEHOLDER
# =========================================================

def create_placeholder(
    title,
    message
):

    image = np.zeros(
        (
            DISPLAY_HEIGHT,
            DISPLAY_WIDTH,
            3
        ),
        dtype=np.uint8
    )

    cv2.putText(
        image,
        title,
        (30, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.2,
        (255, 255, 255),
        2
    )

    cv2.putText(
        image,
        message,
        (30, 180),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255),
        2
    )

    return image


# =========================================================
# INITIAL FRAMES
# =========================================================

frame1 = create_placeholder(
    "WEBCAM 1",
    "Waiting for camera..."
)

frame2 = create_placeholder(
    "WEBCAM 2",
    "Waiting for camera..."
)


# =========================================================
# DETECTION RESULTS
# =========================================================

result_frame1 = frame1.copy()
result_frame2 = frame2.copy()

last_result1 = None
last_result2 = None

count_person1 = 0
count_objects1 = 0

count_person2 = 0
count_objects2 = 0


# =========================================================
# FPS VARIABLES
# =========================================================

fps_start = time.perf_counter()

fps_frames = 0

display_fps = 0.0

frame_number = 0


# =========================================================
# MAIN LOOP
# =========================================================

try:

    while True:

        frame_number += 1


        # =================================================
        # CAMERA 1
        # =================================================

        if cam1 is not None:

            ret1, raw1 = cam1.read()

            if ret1:

                frame1 = raw1


        # =================================================
        # CAMERA 2
        # =================================================

        if cam2 is not None:

            ret2, raw2 = cam2.read()

            if ret2:

                frame2 = raw2


        # =================================================
        # YOLO DETECTION
        # =================================================

        if (
            frame_number % DETECT_EVERY == 0
        ):


            # ---------------------------------------------
            # CAMERA 1
            # ---------------------------------------------

            if cam1 is not None:

                try:

                    results1 = model.predict(
                        source=frame1,
                        imgsz=640,
                        conf=CONFIDENCE,
                        device=DEVICE,
                        verbose=False
                    )

                    if results1:

                        result1 = results1[0]

                        result_frame1 = (
                            result1.plot()
                        )


                        # Count objects
                        if result1.boxes is not None:

                            count_objects1 = len(
                                result1.boxes
                            )

                            count_person1 = 0

                            for cls in result1.boxes.cls:

                                class_id = int(
                                    cls.item()
                                )

                                class_name = (
                                    model.names[
                                        class_id
                                    ]
                                )

                                if class_name == "person":

                                    count_person1 += 1


                except Exception as error:

                    print(
                        f"[YOLO] Camera 1 error: "
                        f"{error}"
                    )


            # ---------------------------------------------
            # CAMERA 2
            # ---------------------------------------------

            if cam2 is not None:

                try:

                    results2 = model.predict(
                        source=frame2,
                        imgsz=640,
                        conf=CONFIDENCE,
                        device=DEVICE,
                        verbose=False
                    )

                    if results2:

                        result2 = results2[0]

                        result_frame2 = (
                            result2.plot()
                        )


                        # Count objects
                        if result2.boxes is not None:

                            count_objects2 = len(
                                result2.boxes
                            )

                            count_person2 = 0

                            for cls in result2.boxes.cls:

                                class_id = int(
                                    cls.item()
                                )

                                class_name = (
                                    model.names[
                                        class_id
                                    ]
                                )

                                if class_name == "person":

                                    count_person2 += 1


                except Exception as error:

                    print(
                        f"[YOLO] Camera 2 error: "
                        f"{error}"
                    )


        # =================================================
        # RESIZE
        # =================================================

        display1 = cv2.resize(
            result_frame1,
            (
                DISPLAY_WIDTH,
                DISPLAY_HEIGHT
            )
        )

        display2 = cv2.resize(
            result_frame2,
            (
                DISPLAY_WIDTH,
                DISPLAY_HEIGHT
            )
        )


        # =================================================
        # CAMERA HEADER
        # =================================================

        cv2.rectangle(
            display1,
            (0, 0),
            (DISPLAY_WIDTH, 55),
            (25, 25, 25),
            -1
        )

        cv2.rectangle(
            display2,
            (0, 0),
            (DISPLAY_WIDTH, 55),
            (25, 25, 25),
            -1
        )


        cv2.putText(
            display1,
            "WEBCAM 1",
            (20, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2
        )

        cv2.putText(
            display2,
            "WEBCAM 2",
            (20, 38),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (255, 255, 255),
            2
        )


        # =================================================
        # INFO
        # =================================================

        cv2.putText(
            display1,
            f"People: {count_person1}",
            (20, 335),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display1,
            f"Objects: {count_objects1}",
            (190, 335),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2
        )


        cv2.putText(
            display2,
            f"People: {count_person2}",
            (20, 335),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2
        )

        cv2.putText(
            display2,
            f"Objects: {count_objects2}",
            (190, 335),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2
        )


        # =================================================
        # COMBINE
        # =================================================

        combined = cv2.hconcat(
            [
                display1,
                display2
            ]
        )


        # =================================================
        # FPS
        # =================================================

        fps_frames += 1

        current_time = (
            time.perf_counter()
        )

        elapsed = (
            current_time - fps_start
        )

        if elapsed >= 1.0:

            display_fps = (
                fps_frames / elapsed
            )

            fps_frames = 0

            fps_start = current_time


        # =================================================
        # GLOBAL FPS
        # =================================================

        cv2.rectangle(
            combined,
            (0, 55),
            (200, 95),
            (0, 0, 0),
            -1
        )

        cv2.putText(
            combined,
            f"FPS: {display_fps:.1f}",
            (15, 84),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 255, 0),
            2
        )


        # =================================================
        # DISPLAY
        # =================================================

        cv2.imshow(
            WINDOW_NAME,
            combined
        )


        # =================================================
        # KEYBOARD
        # =================================================

        key = (
            cv2.waitKey(1)
            & 0xFF
        )


        # Q
        if key == ord("q"):

            break


        # ESC
        if key == 27:

            break


finally:

    # =====================================================
    # CLEANUP
    # =====================================================

    print("\n[EXIT] Closing cameras...")

    if cam1 is not None:
        cam1.release()

    if cam2 is not None:
        cam2.release()

    cv2.destroyAllWindows()

    print("[EXIT] Done.")