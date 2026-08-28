import cv2

CAMERA_1 = "/dev/video0"
CAMERA_2 = "/dev/video2"

def open_camera(device):
    cap = cv2.VideoCapture(device, cv2.CAP_V4L2)

    cap.set(
        cv2.CAP_PROP_FOURCC,
        cv2.VideoWriter_fourcc(*"MJPG")
    )

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)

    return cap


cam1 = open_camera(CAMERA_1)
cam2 = open_camera(CAMERA_2)

if not cam1.isOpened():
    print(f"❌ เปิด Webcam 1 ไม่ได้: {CAMERA_1}")

if not cam2.isOpened():
    print(f"❌ เปิด Webcam 2 ไม่ได้: {CAMERA_2}")

if not cam1.isOpened() and not cam2.isOpened():
    raise SystemExit("ไม่สามารถเปิดกล้องทั้งสองตัวได้")


print("================================")
print("       DUAL WEBCAM TEST")
print("================================")
print("Webcam 1 :", CAMERA_1)
print("Webcam 2 :", CAMERA_2)
print("กด Q เพื่อออก")


while True:

    # Webcam 1
    if cam1.isOpened():
        ret1, frame1 = cam1.read()

        if ret1:
            cv2.putText(
                frame1,
                "WEBCAM 1 - /dev/video0",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )

            cv2.imshow("Webcam 1", frame1)

    # Webcam 2
    if cam2.isOpened():
        ret2, frame2 = cam2.read()

        if ret2:
            cv2.putText(
                frame2,
                "WEBCAM 2 - /dev/video2",
                (20, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (0, 255, 0),
                2
            )

            cv2.imshow("Webcam 2", frame2)

    # Q = ออก
    if cv2.waitKey(1) & 0xFF == ord("q"):
        break


cam1.release()
cam2.release()
cv2.destroyAllWindows()