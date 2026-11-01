
import cv2
from ultralytics import YOLO

model = YOLO("yolo26n.pt")

video_path = "sample_videos/campus.avi"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("Error: Could not open video.")
    raise SystemExit

# Restricted zone: x1, y1, x2, y2
zone_x1, zone_y1 = 300, 150
zone_x2, zone_y2 = 600, 400

while True:
    success, frame = cap.read()

    if not success:
        break

    results = model(frame, verbose=False)
    output = results[0].plot()

    # Draw the restricted zone
    cv2.rectangle(
        output,
        (zone_x1, zone_y1),
        (zone_x2, zone_y2),
        (0, 0, 255),
        2
    )

    intrusion = False

    for box in results[0].boxes:
        class_id = int(box.cls[0])

        if model.names[class_id] != "person":
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # Bottom-centre point of the person
        foot_x = (x1 + x2) // 2
        foot_y = y2

        if (
            zone_x1 <= foot_x <= zone_x2
            and zone_y1 <= foot_y <= zone_y2
        ):
            intrusion = True
            cv2.circle(
                output,
                (foot_x, foot_y),
                6,
                (0, 0, 255),
                -1
            )

    if intrusion:
        cv2.putText(
            output,
            "WARNING: RESTRICTED ZONE ENTRY!",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2
        )
    else:
        cv2.putText(
            output,
            "Zone Status: CLEAR",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

    cv2.imshow("Campus Security - Zone Detection", output)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
