import sys
import os
import cv2
import numpy as np
import face_recognition
from datetime import datetime
import sqlite3

from ultralytics import YOLO
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QGroupBox
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QImage, QPixmap

# ---------- PostgreSQL DB SETUP (replace sqlite3 parts) ----------
import psycopg2
from psycopg2.extras import RealDictCursor

# Put your Postgres credentials here (or read from env vars)
PG_HOST = "localhost"
PG_PORT = 5432
PG_DB   = "your_db_name"
PG_USER = "your_user"
PG_PASS = "your_password"

# Create connection (keep this open for app lifetime)
conn = psycopg2.connect(
    host=PG_HOST,
    port=PG_PORT,
    dbname=PG_DB,
    user=PG_USER,
    password=PG_PASS
)
# Use a regular cursor for simple operations
cursor = conn.cursor()

# Create attendance table if not exists
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    time TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
""")
conn.commit()


# ==========================
# HELPER FUNCTIONS
# ==========================


# ---------- markAttendance adapted for Postgres ----------
def markAttendance(name):
    """
    Insert only once per day for a name.
    Returns True if a new row was inserted, False otherwise.
    """
    # Check if a record exists for this name today
    cursor.execute(
        "SELECT 1 FROM attendance WHERE name = %s AND DATE(time) = CURRENT_DATE LIMIT 1;",
        (name,)
    )
    record = cursor.fetchone()
    if record is None:
        # Insert new attendance with current timestamp
        cursor.execute(
            "INSERT INTO attendance (name, time) VALUES (%s, NOW()) RETURNING id;",
            (name,)
        )
        conn.commit()
        return True
    return False


def loadImages(path):
    images = []
    classNames = []
    if not os.path.isdir(path):
        print(f"[WARN] Images folder '{path}' not found.")
        return images, classNames

    for cl in os.listdir(path):
        cur_path = os.path.join(path, cl)
        img = cv2.imread(cur_path)
        if img is None:
            continue
        images.append(img)
        classNames.append(os.path.splitext(cl)[0])
    return images, classNames


# ==========================
# MAIN APPLICATION
# ==========================
class AttendanceSystem(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Worker Attendance System")
        self.setGeometry(100, 100, 1200, 800)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.updateFrame)
        self.cap = cv2.VideoCapture(0)

        # ---- YOLO helmet model ----
        # Change this to where you saved hemletYoloV8_100epochs.pt
        model_path = r"hemletYoloV8_100epochs.pt"
        self.helmet_model = YOLO(model_path)
        print("Helmet model classes:", self.helmet_model.names)

        # auto-detect helmet class ids (class names containing 'helmet')
        self.HELMET_CLASS_IDS = [
            i for i, n in self.helmet_model.names.items()
            if "helmet" in str(n).lower()
        ]
        if not self.HELMET_CLASS_IDS:
            # fallback: treat all classes as helmet
            self.HELMET_CLASS_IDS = list(self.helmet_model.names.keys())
        print("Using helmet class ids:", self.HELMET_CLASS_IDS)

        self.encodeListKnown = []
        self.classNames = []
        self.knownFaces = {}  # to avoid double marking per session
        self.totalCount = 0

        self.initUI()
        self.startRecognition()

    # --------------------------
    # UI SETUP
    # --------------------------
    def initUI(self):
        centralWidget = QWidget(self)
        self.setCentralWidget(centralWidget)
        layout = QVBoxLayout(centralWidget)

        titleLabel = QLabel("Worker Attendance System", self)
        titleLabel.setAlignment(Qt.AlignCenter)
        titleLabel.setStyleSheet(
            "font-size: 28px; font-weight: bold; margin: 20px 0; color: #343a40;"
        )
        layout.addWidget(titleLabel)

        mainLayout = QHBoxLayout()
        layout.addLayout(mainLayout)

        # Left panel
        leftPanel = QVBoxLayout()
        mainLayout.addLayout(leftPanel, 1)

        self.startButton = QPushButton("Start Recognition", self)
        self.startButton.setStyleSheet(
            "font-size: 18px; padding: 10px; background-color: #007bff; color: white;"
        )
        self.startButton.clicked.connect(self.startRecognition)
        leftPanel.addWidget(self.startButton)

        self.quitButton = QPushButton("Quit", self)
        self.quitButton.setStyleSheet(
            "font-size: 18px; padding: 10px; background-color: #dc3545; color: white;"
        )
        self.quitButton.clicked.connect(self.closeApp)
        leftPanel.addWidget(self.quitButton)

        tableGroupBox = QGroupBox("Attendance Table")
        tableGroupBox.setStyleSheet(
            "font-size: 18px; font-weight: bold; margin-top: 20px; "
            "color: #343a40; padding: 10px; padding-bottom: 5px;"
        )
        leftPanel.addWidget(tableGroupBox)

        tableLayout = QVBoxLayout(tableGroupBox)
        self.tableWidget = QTableWidget(self)
        self.tableWidget.setColumnCount(2)
        self.tableWidget.setHorizontalHeaderLabels(["Name", "Time"])
        self.tableWidget.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.tableWidget.verticalHeader().setVisible(False)
        tableLayout.addWidget(self.tableWidget)

        self.totalCountLabel = QLabel("Total Workers Recognized: 0", self)
        self.totalCountLabel.setAlignment(Qt.AlignCenter)
        self.totalCountLabel.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #28a745; margin-top: 10px;"
        )
        leftPanel.addWidget(self.totalCountLabel)

        # Right panel
        rightPanel = QVBoxLayout()
        mainLayout.addLayout(rightPanel, 3)

        webcamGroupBox = QGroupBox("Webcam Feed")
        rightPanel.addWidget(webcamGroupBox)

        webcamLayout = QVBoxLayout(webcamGroupBox)
        self.imageLabel = QLabel(self)
        self.imageLabel.setAlignment(Qt.AlignCenter)
        webcamLayout.addWidget(self.imageLabel)

    # --------------------------
    # LOGIC
    # --------------------------
    def startRecognition(self):
        path = "images"
        images, classNames = loadImages(path)

        self.encodeListKnown = []
        self.classNames = []
        self.knownFaces.clear()
        self.totalCount = 0

        for img, name in zip(images, classNames):
            if img is None:
                print(f"[WARN] Could not read image for {name}")
                continue

            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            encodes = face_recognition.face_encodings(rgb_img)
            if len(encodes) == 0:
                print(f"[WARN] No face found in image for {name}, skipping")
                continue

            self.encodeListKnown.append(encodes[0])
            self.classNames.append(name)
            print(f"[INFO] Registered person: {name}")

        print(f"[INFO] Total registered people: {len(self.classNames)}")

        self.updateAttendanceTableFromDB()
        self.totalCountLabel.setText("Total Workers Recognized: 0")
        self.timer.start(30)

    def has_helmet_for_face(self, face_box, helmet_boxes):
        """
        face_box: (x1, y1, x2, y2) in full-res frame coordinates
        helmet_boxes: list of (hx1, hy1, hx2, hy2)
        """
        x1, y1, x2, y2 = face_box

        for hx1, hy1, hx2, hy2 in helmet_boxes:
            # horizontal overlap
            horizontal_overlap = not (hx2 < x1 or hx1 > x2)
            # helmet bounding box should intersect near top of face
            vertical_condition = (hy2 > y1) and (hy1 < y1)
            if horizontal_overlap and vertical_condition:
                return True
        return False

    def updateFrame(self):
        ret, frame = self.cap.read()
        if not ret:
            return

        # --------------------------
        # 1) HELMET DETECTION (YOLO)
        # --------------------------
        helmet_boxes = []
        try:
            results = self.helmet_model(frame, conf=0.5, verbose=False)
            for r in results:
                if r.boxes is None:
                    continue
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id in self.HELMET_CLASS_IDS:
                        x1, y1, x2, y2 = box.xyxy[0].tolist()
                        helmet_boxes.append(
                            (int(x1), int(y1), int(x2), int(y2))
                        )
        except Exception as e:
            print("Helmet detection error:", e)

        # --------------------------
        # 2) FACE RECOGNITION
        # --------------------------
        small_frame = cv2.resize(frame, (0, 0), None, 0.25, 0.25)
        rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)

        facesCurFrame = face_recognition.face_locations(rgb_small_frame)
        encodesCurFrame = face_recognition.face_encodings(
            rgb_small_frame, facesCurFrame
        )

        for encodeFace, faceLoc in zip(encodesCurFrame, facesCurFrame):
            if not self.encodeListKnown:
                continue

            matches = face_recognition.compare_faces(
                self.encodeListKnown, encodeFace, tolerance=0.5
            )
            faceDis = face_recognition.face_distance(
                self.encodeListKnown, encodeFace
            )
            best_match_index = np.argmin(faceDis)

            name = "Unrecognized"
            has_helmet = False

            # scale back to original frame
            top, right, bottom, left = faceLoc
            top *= 4
            right *= 4
            bottom *= 4
            left *= 4

            face_box = (left, top, right, bottom)

            if matches[best_match_index]:
                has_helmet = self.has_helmet_for_face(face_box, helmet_boxes)

                if has_helmet:
                    if best_match_index < len(self.classNames):
                        name = self.classNames[best_match_index].upper()
                    else:
                        name = "UNKNOWN"

                    # Only mark attendance when helmet is on
                    if name not in self.knownFaces and name not in ["UNKNOWN"]:
                        marked = markAttendance(name)
                        if marked:
                            self.totalCount += 1
                            self.totalCountLabel.setText(
                                f"Total Workers Recognized: {self.totalCount}"
                            )
                            self.updateAttendanceTable(name)
                        self.knownFaces[name] = True

            # Draw face box + label
            if name == "Unrecognized" or not has_helmet:
                color = (0, 0, 255)  # red
                label = "NO HELMET" if name != "Unrecognized" else name
            else:
                color = (0, 255, 0)  # green
                label = name

            cv2.rectangle(frame, (left, top), (right, bottom), color, 2)
            cv2.putText(
                frame,
                label,
                (left + 6, bottom - 6),
                cv2.FONT_HERSHEY_COMPLEX,
                1,
                (255, 255, 255),
                2,
            )

        # --------------------------
        # 3) OPTIONAL: DRAW HELMET BOXES FOR DEBUG
        # --------------------------
        for (hx1, hy1, hx2, hy2) in helmet_boxes:
            cv2.rectangle(frame, (hx1, hy1), (hx2, hy2), (255, 255, 0), 2)
            cv2.putText(
                frame,
                "Helmet",
                (hx1, hy1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 0),
                2,
            )

        # --------------------------
        # 4) SHOW IN QT LABEL
        # --------------------------
        img = QImage(
            frame.data,
            frame.shape[1],
            frame.shape[0],
            frame.strides[0],
            QImage.Format_BGR888,
        )
        self.imageLabel.setPixmap(QPixmap.fromImage(img))

    # --------------------------
    # ATTENDANCE TABLE
    # --------------------------
    def updateAttendanceTable(self, name):
        now = datetime.now().strftime('%H:%M:%S')
        rowPosition = self.tableWidget.rowCount()
        self.tableWidget.insertRow(rowPosition)
        self.tableWidget.setItem(rowPosition, 0, QTableWidgetItem(name))
        self.tableWidget.setItem(rowPosition, 1, QTableWidgetItem(now))

    # ---------- load attendance from DB for table ----------
    def updateAttendanceTableFromDB(self):
        """
        Replace the method in your class that reads DB rows and fills the table widget.
        Note: this function is meant to be used as a method (self.tableWidget, etc).
        """
        self.tableWidget.setRowCount(0)
        cursor.execute("SELECT name, time FROM attendance ORDER BY name;")
        rows = cursor.fetchall()
        for name, time in rows:
            rowPosition = self.tableWidget.rowCount()
            self.tableWidget.insertRow(rowPosition)
            self.tableWidget.setItem(rowPosition, 0, QTableWidgetItem(name))
            # time will be a Python datetime object; format it:
            self.tableWidget.setItem(rowPosition, 1, QTableWidgetItem(time.strftime('%Y-%m-%d %H:%M:%S')))
        self.totalCount = len(rows)
        self.totalCountLabel.setText(f"Total Workers Recognized: {self.totalCount}")

    # --------------------------
    # CLEANUP
    # --------------------------
    def closeApp(self):
        self.timer.stop()
        self.cap.release()
        cv2.destroyAllWindows()
        conn.close()
        self.close()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AttendanceSystem()
    window.show()
    sys.exit(app.exec_())
