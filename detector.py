"""
AgroSonic Defence - High-Performance Real-Time YOLOv8 Vision & Classification Engine
Architecture:
1. Dedicated Camera Grabber Thread: Drops stale hardware buffers to achieve ZERO latency.
2. Asynchronous YOLOv8 Inference Worker: Runs object detection concurrently without blocking video.
3. Smooth 30+ FPS Video Renderer: Draws tactical HUD, bounding boxes, and strobe flasher in real time.
4. Simultaneous native OpenCV window (cv2.imshow) & MJPEG web stream generator.
"""

import cv2
import time
import math
import random
import threading
import numpy as np
from ultralytics import YOLO
from telemetry import telemetry
from deterrence import deterrence_engine
from telegram_notifier import telegram_notifier

# Mapping COCO dataset classes to AgroSonic target intruder categories
CATEGORY_MAP = {
    # Birds
    "bird": "Birds",
    
    # Wild Animals (Agricultural crop destroyer wildlife)
    "elephant": "Wild Animals",
    "bear": "Wild Animals",
    "pig": "Wild Animals",
    "boar": "Wild Animals",
    "zebra": "Wild Animals",
    "giraffe": "Wild Animals",
    
    # Livestock & Domestic Animals
    "cow": "Livestock",
    "sheep": "Livestock",
    "horse": "Livestock",
    "dog": "Livestock",
    "cat": "Livestock"
}

# Agricultural context aliases (displays user-friendly species names)
CLASS_DISPLAY_NAMES = {
    "bear": "Wild Boar",
    "pig": "Wild Boar",
    "boar": "Wild Boar",
    "elephant": "Elephant",
    "dog": "Dog",
    "bird": "Bird",
    "cow": "Cattle",
    "sheep": "Sheep",
    "horse": "Horse",
    "zebra": "Zebra",
    "giraffe": "Giraffe",
    "cat": "Cat"
}

# Color palette for bounding boxes and HUD (BGR format for OpenCV)
COLOR_PALETTE = {
    "Birds": (11, 158, 245),       # Amber / Orange
    "Wild Animals": (68, 68, 239),  # Ruby / Crimson Red
    "Livestock": (212, 229, 6),    # Bright Cyan
    "Safe": (129, 185, 16)         # Emerald Green
}

class AgroVisionEngine:
    def __init__(self, model_path="yolov8n.pt"):
        print("[AgroVision] Loading Ultralytics YOLOv8 model...")
        self.model = YOLO(model_path)
        print("[AgroVision] YOLOv8 loaded successfully.")
        
        self.cap = None
        self.camera_index = 0
        self.is_simulated = False
        
        # Test image injection override
        self.test_image_override = None
        self.test_override_expiry = 0
        
        # Thread-safe frame buffers
        self.raw_frame = None
        self.raw_frame_lock = threading.Lock()
        
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.running = True
        
        # Asynchronous Detection State (persisted across inference intervals)
        self.detection_lock = threading.Lock()
        self.cached_detection = {
            "detected": False,
            "category": "None",
            "class_name": "None",
            "confidence": 0.0,
            "bbox": [],
            "expiry": 0
        }
        
        # Performance metrics
        self.fps = 0.0
        self.frame_count = 0
        self.last_fps_time = time.time()
        self.strobe_phase = 0
        self.flip_horizontal = True  # Flips camera horizontally to correct mirror inversion
        
        # Initialize hardware capture
        self._init_camera()
        
        # Start background threads for ZERO latency
        self._start_workers()

    def toggle_flip(self):
        """Toggle horizontal mirror flip on/off."""
        self.flip_horizontal = not self.flip_horizontal
        print(f"[AgroVision] Camera horizontal mirror flip set to: {self.flip_horizontal}")
        return self.flip_horizontal

    def _init_camera(self):
        """Attempts to open physical webcam; falls back to synthetic farm feed if absent."""
        try:
            self.cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW)
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_index)
                
            if self.cap.isOpened():
                # Minimize hardware buffer size to 1 to completely eliminate video lag
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 30)
                
                # Test frame grab
                ret, test_frame = self.cap.read()
                if ret and test_frame is not None:
                    print(f"[AgroVision] Connected to Hardware Webcam #{self.camera_index} (Lag-Free 30 FPS).")
                    telemetry.camera_source = f"Webcam (Hardware Device #{self.camera_index})"
                    self.is_simulated = False
                    telegram_notifier.send_system_event(
                        "Hardware Camera Online",
                        f"Connected to Hardware Webcam #{self.camera_index} at 30 FPS.",
                        "SUCCESS"
                    )
                    return
        except Exception as e:
            print(f"[AgroVision] Camera init notice: {e}")
            telegram_notifier.send_error_alert("Camera Module", f"Webcam initialization notice: {e}")

        print("[AgroVision] Physical webcam not accessible. Initializing Farm Vision Simulator.")
        self.is_simulated = True
        telemetry.camera_source = "AgroSonic Farm Vision Simulator (Synthetic Feed)"
        telegram_notifier.send_system_event(
            "Vision Mode Active",
            "Physical webcam not found. AgroSonic Farm Vision Simulator active.",
            "INFO"
        )
        if self.cap:
            self.cap.release()
            self.cap = None

    def _start_workers(self):
        """Starts decoupled camera reader and YOLO inference worker threads."""
        # 1. Thread that constantly reads fresh frames from webcam to avoid buffer buildup
        self.grabber_thread = threading.Thread(target=self._camera_grabber_loop, daemon=True)
        self.grabber_thread.start()
        
        # 2. Thread that runs YOLOv8 asynchronously without blocking video playback
        self.inference_thread = threading.Thread(target=self._yolo_inference_loop, daemon=True)
        self.inference_thread.start()

    def _camera_grabber_loop(self):
        """Dedicated high-speed thread to grab latest frames and purge buffer."""
        while self.running:
            frame = None
            now = time.time()
            
            # Check for sample image injection first
            if self.test_image_override is not None:
                if now < self.test_override_expiry:
                    frame = self.test_image_override.copy()
                else:
                    self.test_image_override = None

            if frame is None:
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret and frame is not None:
                        if self.flip_horizontal:
                            frame = cv2.flip(frame, 1)
                    else:
                        frame = self._generate_simulated_frame()
                else:
                    frame = self._generate_simulated_frame()

            with self.raw_frame_lock:
                self.raw_frame = frame

            # Cap capture loop at ~35 FPS
            time.sleep(0.015)

    @staticmethod
    def _box_overlap_ratio(box_animal, box_person):
        """Calculates area of intersection over animal bounding box area."""
        ax1, ay1, ax2, ay2 = box_animal
        px1, py1, px2, py2 = box_person
        ix1 = max(ax1, px1)
        iy1 = max(ay1, py1)
        ix2 = min(ax2, px2)
        iy2 = min(ay2, py2)
        if ix2 <= ix1 or iy2 <= iy1:
            return 0.0
        inter_area = (ix2 - ix1) * (iy2 - iy1)
        animal_area = max(1, (ax2 - ax1) * (ay2 - ay1))
        return inter_area / animal_area

    def _yolo_inference_loop(self):
        """Asynchronous worker that performs YOLOv8 detection on the freshest frame."""
        print("[AgroVision] Asynchronous YOLOv8 inference thread active.")
        while self.running:
            target_frame = None
            with self.raw_frame_lock:
                if self.raw_frame is not None:
                    target_frame = self.raw_frame.copy()

            if target_frame is not None:
                try:
                    H, W = target_frame.shape[:2]
                    candidates = []
                    person_detections = []

                    # Pass 1: Standard upright frame (0 deg)
                    results = self.model(
                        target_frame,
                        conf=max(0.35, telemetry.confidence_threshold),
                        imgsz=384,
                        verbose=False
                    )
                    det_result = results[0]
                    for box in det_result.boxes:
                        cls_id = int(box.cls[0].item())
                        conf = float(box.conf[0].item())
                        name = det_result.names[cls_id]
                        bbox_coords = [int(v) for v in box.xyxy[0].tolist()]

                        # Track human/person detections
                        if name in ("person", "human"):
                            person_detections.append({
                                "confidence": conf,
                                "bbox": bbox_coords
                            })
                        elif name in CATEGORY_MAP:
                            # Domestic pets (dog/cat) need higher threshold to prevent shirt/shadow false positives
                            min_conf = 0.50 if name in ("dog", "cat") else 0.38
                            if conf >= min_conf:
                                candidates.append({
                                    "name": name,
                                    "category": CATEGORY_MAP[name],
                                    "confidence": conf,
                                    "bbox": bbox_coords,
                                    "orient": 0
                                })

                    # Anti-False-Positive Filter:
                    # If a human/person is in the frame, filter out any animal box that overlaps with the human body!
                    if person_detections:
                        valid_candidates = []
                        for cand in candidates:
                            is_on_human = any(
                                self._box_overlap_ratio(cand["bbox"], p["bbox"]) > 0.20
                                for p in person_detections
                            )
                            if not is_on_human:
                                valid_candidates.append(cand)
                            else:
                                print(f"[AgroVision] Suppressed false-positive '{cand['name']}' on human body.")
                        candidates = valid_candidates

                    # Pass 2: Multi-Orientation Check (Only run if NO human is in frame AND no animal detected at 0 deg)
                    # Running rotation on a human turns them horizontal and tricks YOLO into detecting a dog!
                    has_human = len(person_detections) > 0
                    if not has_human and len(candidates) == 0:
                        rot_ccw = cv2.rotate(target_frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                        res_ccw = self.model(
                            rot_ccw,
                            conf=max(0.40, telemetry.confidence_threshold),
                            imgsz=384,
                            verbose=False
                        )[0]
                        for box in res_ccw.boxes:
                            cls_id = int(box.cls[0].item())
                            conf = float(box.conf[0].item())
                            name = res_ccw.names[cls_id]
                            if name in CATEGORY_MAP:
                                min_conf = 0.55 if name in ("dog", "cat") else 0.42
                                if conf >= min_conf:
                                    xr1, yr1, xr2, yr2 = [int(v) for v in box.xyxy[0].tolist()]
                                    orig_x1 = max(0, min(W - 1, W - 1 - yr2))
                                    orig_x2 = max(0, min(W - 1, W - 1 - yr1))
                                    orig_y1 = max(0, min(H - 1, xr1))
                                    orig_y2 = max(0, min(H - 1, xr2))
                                    candidates.append({
                                        "name": name,
                                        "category": CATEGORY_MAP[name],
                                        "confidence": conf,
                                        "bbox": [orig_x1, orig_y1, orig_x2, orig_y2],
                                        "orient": 90
                                    })

                    detected = False
                    detected_cat = "None"
                    detected_class = "None"
                    highest_conf = 0.0
                    best_bbox = []
                    total_count = len(candidates)

                    if candidates:
                        # Rank candidates: prioritize large wildlife over ambiguous birds
                        def candidate_rank(c):
                            mammal_bonus = 0.15 if c["name"] in ("elephant", "bear", "pig", "boar") else 0.0
                            return c["confidence"] + mammal_bonus

                        candidates.sort(key=candidate_rank, reverse=True)
                        top = candidates[0]
                        detected = True
                        detected_cat = top["category"]
                        raw_name = top["name"]
                        detected_class = CLASS_DISPLAY_NAMES.get(raw_name, raw_name.capitalize())
                        highest_conf = top["confidence"]
                        best_bbox = top["bbox"]

                    now = time.time()
                    with self.detection_lock:
                        if detected:
                            self.cached_detection = {
                                "detected": True,
                                "category": detected_cat,
                                "class_name": detected_class,
                                "confidence": highest_conf,
                                "bbox": best_bbox,
                                "expiry": now + 0.50  # Keep bbox stable for 500ms
                            }
                            # Trigger deterrence actuation
                            deterrence_engine.evaluate_and_deter(detected_cat, highest_conf, class_name=detected_class)
                        elif now > self.cached_detection["expiry"]:
                            self.cached_detection = {
                                "detected": False,
                                "category": "None",
                                "class_name": "None",
                                "confidence": 0.0,
                                "bbox": [],
                                "expiry": 0
                            }

                    # Update telemetry state
                    telemetry.update_detection(
                        detected=self.cached_detection["detected"],
                        category=self.cached_detection["category"],
                        class_name=self.cached_detection["class_name"],
                        confidence=self.cached_detection["confidence"],
                        bbox=self.cached_detection["bbox"],
                        count=total_count
                    )

                except Exception as e:
                    print(f"[AgroVision] Async inference error: {e}")
                    telegram_notifier.send_error_alert("YOLOv8 Inference Worker", str(e))

            # Sleep briefly to free CPU for rendering (~15-20 detections/sec is optimal)
            time.sleep(0.04)

    def inject_sample_image(self, image_path, hold_seconds=12.0):
        """Directly inject a sample intruder image into the vision engine for testing."""
        img = cv2.imread(image_path)
        if img is not None:
            img = cv2.resize(img, (640, 480))
            self.test_image_override = img
            self.test_override_expiry = time.time() + hold_seconds
            return True
        return False

    def clear_sample_injection(self):
        self.test_image_override = None
        self.test_override_expiry = 0

    def _generate_simulated_frame(self):
        """Generates an aesthetic simulated camera feed if no physical webcam is plugged in."""
        w, h = 640, 480
        frame = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Landscape
        frame[:260, :] = [45, 25, 15]
        frame[260:, :] = [20, 45, 25]
        
        t = time.time()
        for x in range(0, w, 60):
            cv2.line(frame, (x, 260), (int(x + (x - 320) * 0.8), 480), (35, 70, 40), 1)
        for y in range(270, 480, 35):
            cv2.line(frame, (0, y), (w, y), (35, 70, 40), 1)

        cv2.putText(frame, "SIMULATED SENSOR NODE 01 - NORTH ORCHARD", (15, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (100, 200, 100), 1, cv2.LINE_AA)
        cv2.putText(frame, "[Hold animal photo to camera OR use 'Test Intruder' buttons]", (15, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (180, 180, 180), 1, cv2.LINE_AA)
        
        radar_x = int(320 + 200 * math.sin(t * 1.5))
        radar_y = int(360 + 40 * math.cos(t * 1.5))
        cv2.circle(frame, (radar_x, radar_y), 4, (0, 255, 180), -1)
        cv2.circle(frame, (radar_x, radar_y), 12, (0, 255, 180), 1)
        
        return frame

    def _draw_hud_and_strobe(self, frame, category, confidence, class_name, bbox):
        """Draws high-tech bounding boxes, HUD telemetry, and visual LED strobe effects."""
        h, w = frame.shape[:2]
        is_deterring = telemetry.deterrence_state["active"]
        
        # 1. VISUAL LED STROBE SIMULATION OVERLAY
        if is_deterring:
            self.strobe_phase = (self.strobe_phase + 1) % 4
            if self.strobe_phase < 2:
                strobe_bgr = COLOR_PALETTE.get(category, (68, 68, 239))
                border_thick = 14
                cv2.rectangle(frame, (0, 0), (w, h), strobe_bgr, border_thick)
                
                cv2.rectangle(frame, (w//2 - 240, 10), (w//2 + 240, 52), (0, 0, 0), -1)
                cv2.rectangle(frame, (w//2 - 240, 10), (w//2 + 240, 52), strobe_bgr, 2)
                alert_text = f"!!! ACTIVE STROBE & ULTRASONIC SWEEP ({telemetry.deterrence_state['frequency_khz']} kHz) !!!"
                cv2.putText(frame, alert_text, (w//2 - 228, 38),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.44, (255, 255, 255), 2, cv2.LINE_AA)

        # 2. BOUNDING BOX & INTRUDER CATEGORY TAG
        if category and category != "None" and bbox and len(bbox) == 4:
            x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
            color = COLOR_PALETTE.get(category, (0, 255, 255))
            
            line_len = 24
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.line(frame, (x1, y1), (x1 + line_len, y1), color, 4)
            cv2.line(frame, (x1, y1), (x1, y1 + line_len), color, 4)
            cv2.line(frame, (x2, y1), (x2 - line_len, y1), color, 4)
            cv2.line(frame, (x2, y1), (x2, y1 + line_len), color, 4)
            cv2.line(frame, (x1, y2), (x1 + line_len, y2), color, 4)
            cv2.line(frame, (x1, y2), (x1, y2 - line_len), color, 4)
            cv2.line(frame, (x2, y2), (x2 - line_len, y2), color, 4)
            cv2.line(frame, (x2, y2), (x2, y2 - line_len), color, 4)
            
            badge_text = f"[{category.upper()}] {class_name.capitalize()} {int(confidence * 100)}%"
            (txt_w, txt_h), _ = cv2.getTextSize(badge_text, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
            cv2.rectangle(frame, (x1, int(max(0, y1 - 26))), (int(x1 + txt_w + 12), int(max(26, y1))), color, -1)
            cv2.putText(frame, badge_text, (int(x1 + 6), int(max(18, y1 - 8))),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.52, (10, 10, 10), 2, cv2.LINE_AA)

        # 3. HUD TELEMETRY OVERLAY (Bottom status bar)
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, h - 42), (w, h), (10, 15, 20), -1)
        cv2.addWeighted(overlay, 0.82, frame, 0.18, 0, frame)
        
        status_text = f"SYS: {telemetry.system_status} | FPS: {int(self.fps)} | ULTRASONIC: {telemetry.deterrence_state['frequency_display']}"
        cv2.putText(frame, status_text, (15, h - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (220, 220, 220), 1, cv2.LINE_AA)
        
        time_str = time.strftime("%H:%M:%S")
        cv2.putText(frame, time_str, (w - 90, h - 16),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (16, 185, 129), 1, cv2.LINE_AA)

        return frame

    def run_cv_loop(self):
        """
        Main Video Render & Display Thread:
        Executes at full 30+ FPS, rendering the HUD and latest detections on top of the
        real-time camera frame with ZERO LAG.
        """
        print("[AgroVision] Main render & display loop running at 30+ FPS.")
        window_created = False
        
        while self.running:
            # Calculate instantaneous render FPS
            self.frame_count += 1
            now = time.time()
            if now - self.last_fps_time >= 1.0:
                self.fps = self.frame_count / (now - self.last_fps_time)
                self.frame_count = 0
                self.last_fps_time = now

            # Fetch freshest raw frame
            curr_frame = None
            with self.raw_frame_lock:
                if self.raw_frame is not None:
                    curr_frame = self.raw_frame.copy()

            if curr_frame is None:
                curr_frame = self._generate_simulated_frame()

            # Retrieve latest asynchronous detections
            with self.detection_lock:
                det = dict(self.cached_detection)

            # Draw HUD and bounding boxes (extremely fast: < 1ms)
            annotated_frame = self._draw_hud_and_strobe(
                curr_frame,
                det["category"],
                det["confidence"],
                det["class_name"],
                det["bbox"]
            )

            # Update latest frame buffer for web streaming
            with self.frame_lock:
                self.latest_frame = annotated_frame

            # OpenCV Window (cv2.imshow) handling
            if telemetry.cv_window_active:
                try:
                    window_title = "AgroSonic Defence - Real-Time Vision & Deterrence Feed"
                    cv2.imshow(window_title, annotated_frame)
                    window_created = True
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        print("[AgroVision] 'q' pressed in CV window; closing desktop window.")
                        telemetry.cv_window_active = False
                        cv2.destroyWindow(window_title)
                        window_created = False
                except Exception:
                    pass
            elif window_created:
                try:
                    cv2.destroyAllWindows()
                    window_created = False
                except Exception:
                    pass

            # ~30 FPS frame pacing
            time.sleep(0.025)

        if self.cap:
            self.cap.release()
        cv2.destroyAllWindows()

    def get_jpeg_frame(self):
        """Returns current frame as fast JPEG bytes for Flask MJPEG response."""
        with self.frame_lock:
            if self.latest_frame is None:
                blank = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(blank, "Connecting to AgroSonic Sensor...", (160, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 180), 2)
                ret, buffer = cv2.imencode('.jpg', blank)
                return buffer.tobytes()
            # Fast JPEG encoding at quality 75 for optimal latency & network efficiency
            ret, buffer = cv2.imencode('.jpg', self.latest_frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
            if ret:
                return buffer.tobytes()
            return None

# Global vision engine singleton
vision_engine = AgroVisionEngine()
