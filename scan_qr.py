# scan_qr.py
import cv2
from pyzbar.pyzbar import decode
import requests
import time

# Flask server URL — must match your app.py route
SERVER_URL = "http://127.0.0.1:5000/scan_qr"

# Cooldown time (in seconds) to prevent double-scanning the same QR locally
COOLDOWN_TIME = 5  # keep short for testing

def scan_qr():
    cap = cv2.VideoCapture(0)
    print("📷 QR Scanner started. Press 'q' to quit.\n")

    last_scan = None
    last_time = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("⚠️ Unable to access camera.")
            break

        # Decode QR codes in the frame
        for qr in decode(frame):
            vehicle_number = qr.data.decode('utf-8').strip()

            # Prevent spam scanning (same QR within cooldown time)
            now = time.time()
            if last_scan == vehicle_number and (now - last_time < COOLDOWN_TIME):
                continue

            last_scan = vehicle_number
            last_time = now

            print(f"✅ Detected vehicle (raw): {vehicle_number}")

            # Send QR data to Flask backend
            try:
                response = requests.post(SERVER_URL, json={"plate_number": vehicle_number})
                if response.status_code == 429:
                    print("⏱ Server cooldown:", response.json().get("message"))
                elif response.status_code >= 400:
                    print("❌ Server returned error:", response.status_code, response.text)
                else:
                    print("🚗 Server response:", response.json())
            except requests.exceptions.ConnectionError:
                print("❌ Cannot connect to Flask server. Make sure it's running at 127.0.0.1:5000")
            except requests.exceptions.RequestException as e:
                print("⚠️ Request failed:", e)

            # Draw a rectangle around the QR for visual feedback
            (x, y, w, h) = qr.rect
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 3)

        # Show the camera window
        cv2.imshow("QR Scanner", frame)

        # Quit when pressing 'q'
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    scan_qr()
