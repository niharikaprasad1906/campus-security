
import cv2
import time
import datetime
from ultralytics import YOLO


def log_incident(incident_type, track_id=None):
    with open("incident_log.txt", "a") as file:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        file.write(
            f"{timestamp} | {incident_type} | "
            f"Person ID: {track_id} | Camera: Main Gate\n"
        )


after_hours_test = False  # Set to True to test after-hours movement detection
model = YOLO("yolo26n.pt")

video_path = "sample_videos/campus.avi"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("Error: Could not open video.")
    raise SystemExit

# Restricted zone: x1, y1, x2, y2
zone_x1, zone_y1 = 300, 150
zone_x2, zone_y2 = 600, 400
crowd_threshold = 5
loiter_start_times = {}
logged_after_hours = set()
logged_loitering = set()
crowd_logged = False

while True:
    success, frame = cap.read()

    if not success:
        break

    results = model.track(
        frame,
        persist=True,
        tracker="bytetrack.yaml",
        verbose=False,
    )

    if not results or len(results) == 0:
        continue

    output = results[0].plot()

    # Draw the restricted zone
    cv2.rectangle(
        output,
        (zone_x1, zone_y1),
        (zone_x2, zone_y2),
        (0, 0, 255),
        2,
    )

    people_in_zone = set()
    loitering_detected = False
    intrusion = False
    person_count = 0
    after_hours_alert = False

    for box in results[0].boxes:
        if box.cls is None or len(box.cls) == 0:
            continue

        class_id = int(box.cls[0])
        if model.names.get(class_id) != "person":
            continue

        if box.xyxy is None or len(box.xyxy) == 0:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])

        # Bottom-center point of the person
        foot_x = (x1 + x2) // 2
        foot_y = y2

        if zone_x1 <= foot_x <= zone_x2 and zone_y1 <= foot_y <= zone_y2:
            intrusion = True
            person_count += 1

            if box.id is not None and len(box.id) > 0:
                track_id = int(box.id[0])
                people_in_zone.add(track_id)

                if track_id not in loiter_start_times:
                    loiter_start_times[track_id] = time.time()

                elapsed_time = time.time() - loiter_start_times[track_id]

                cv2.putText(
                    output,
                    f"ID {track_id}: {int(elapsed_time)} sec",
                    (foot_x, foot_y - 15),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (255, 255, 0),
                    2,
                )

                current_hour = datetime.datetime.now().hour
                if after_hours_test or current_hour >= 22 or current_hour < 6:
                    after_hours_alert = True
                    if track_id not in logged_after_hours:
                        log_incident("After-Hours Movement", track_id)
                        logged_after_hours.add(track_id)

                if elapsed_time > 15:  # Loitering threshold in seconds
                    loitering_detected = True
                    if track_id not in logged_loitering:
                        log_incident("Loitering Detected", track_id)
                        logged_loitering.add(track_id)

            cv2.circle(
                output,
                (foot_x, foot_y),
                6,
                (0, 0, 255),
                -1,
            )

    if person_count > crowd_threshold:
        crowd_status = "WARNING: OVERCROWDING!"
        if not crowd_logged:
            log_incident("Overcrowding Detected")
            crowd_logged = True
    else:
        crowd_status = "Crowd Status: NORMAL"
        crowd_logged = False

    for track_id in list(loiter_start_times.keys()):
        if track_id not in people_in_zone:
            del loiter_start_times[track_id]

    if loitering_detected:
        cv2.putText(
            output,
            "WARNING: LOITERING DETECTED!",
            (20, 160),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )

    cv2.putText(
        output,
        f"People Count: {person_count}",
        (20, 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 255, 0),
        2,
    )
    cv2.putText(
        output,
        crowd_status,
        (20, 120),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 255) if person_count > crowd_threshold else (0, 255, 0),
        2,
    )

    if intrusion:
        cv2.putText(
            output,
            "WARNING: RESTRICTED ZONE ENTRY!",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 255),
            2,
        )
    else:
        cv2.putText(
            output,
            "Zone Status: CLEAR",
            (20, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2,
        )

    if after_hours_alert:
        cv2.putText(
            output,
            "WARNING: AFTER-HOURS MOVEMENT!",
            (20, 200),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
        )

    cv2.imshow("Campus Security - Zone Detection", output)

    if cv2.waitKey(1) & 0xFF == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()

