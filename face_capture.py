import cv2
import os

def capture_face(user_name, save_path="faces"):
    # Create folder to save faces if it doesn't exist
    os.makedirs(save_path, exist_ok=True)

    video_capture = cv2.VideoCapture(0)
    if not video_capture.isOpened():
        print("Camera not detected.")
        return

    print(f"[INFO] Capturing face for '{user_name}'. Press 'q' to quit.")

    count = 0
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

    while True:
        ret, frame = video_capture.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

        for (x, y, w, h) in faces:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Save detected face region
            face_img = frame[y:y+h, x:x+w]
            count += 1
            cv2.imwrite(os.path.join(save_path, f"{user_name}_{count}.jpg"), face_img)

        cv2.imshow("Face Capture", frame)
        if cv2.waitKey(1) & 0xFF == ord('q') or count >= 20:
            # Stop after 20 samples or 'q'
            break

    video_capture.release()
    cv2.destroyAllWindows()
    print(f"[INFO] Captured {count} images for {user_name}.")
