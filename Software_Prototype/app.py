"""
AgroSonic Defence - Production Web Server & IoT Telemetry Hub
Starts Flask web application, connects the real-time YOLOv8 Computer Vision thread,
and serves interactive dashboard telemetry and API hooks for hackathon judges.
"""

import os
import time
import threading
from flask import Flask, render_template, Response, jsonify, request, send_from_directory
from telemetry import telemetry
from deterrence import deterrence_engine
from detector import vision_engine
from telegram_notifier import telegram_notifier

app = Flask(__name__, static_folder="static", template_folder="templates")

# Sample intruders mapping
SAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_intruders")
AVAILABLE_SAMPLES = {
    "wild_boar": os.path.join(SAMPLE_DIR, "wild_boar.jpg"),
    "elephant": os.path.join(SAMPLE_DIR, "elephant.jpg"),
    "dog": os.path.join(SAMPLE_DIR, "dog.jpg"),
    "bird": os.path.join(SAMPLE_DIR, "bird.jpg"),
    "wild_animal": os.path.join(SAMPLE_DIR, "elephant.jpg"),
    "livestock": os.path.join(SAMPLE_DIR, "dog.jpg")
}

def gen_frames():
    """MJPEG streaming generator function for the web dashboard video element."""
    while True:
        frame_bytes = vision_engine.get_jpeg_frame()
        if frame_bytes:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        time.sleep(0.04)  # ~25-30 FPS web streaming

@app.route('/')
def index():
    """Main AgroSonic Defence Web Dashboard."""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """Live video stream route."""
    return Response(gen_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/status', methods=['GET'])
def get_status():
    """
    Primary API endpoint returning real-time telemetry:
    - Target intruder detection class & confidence
    - Active deterrence actuation (ultrasonic frequency, strobe state, sound SPL)
    - Habituation mitigation metrics & level
    - Simulated ESP32 IoT node telemetry (battery, solar, piezo transducer, RF)
    - Circular event logs for judge review
    """
    return jsonify(telemetry.get_full_status())

@app.route('/api/trigger_manual', methods=['GET', 'POST'])
def trigger_manual():
    """Allows judges or operators to manually fire an ultrasonic sweep & strobe burst."""
    data = (request.get_json(silent=True) or {}) if request.is_json else {}
    category = data.get("category", request.args.get("category", "Wild Animals"))
    result = deterrence_engine.evaluate_and_deter(category, 0.99)
    if result:
        telegram_notifier.send_system_event(
            "Manual Deterrence Actuated",
            f"Operator triggered manual acoustic deterrence for: {category}",
            "INFO"
        )
        return jsonify({"status": "success", "actuation": result})
    else:
        # Force trigger without debounce if manually requested
        telemetry.trigger_deterrence(
            category=category,
            frequency_khz=38.5,
            strategy="Manual Operator Override Sweep (38.5 kHz)",
            habituation_level=3,
            strobe_hz=20,
            sound_db=122,
            duration=3.0
        )
        deterrence_engine.audio_worker.queue_actuation("CHAOS_MODULATION", 38.5, 3, 3.0)
        telegram_notifier.send_system_event(
            "Manual Override Forced",
            f"Forced operator override sweep actuated for category: {category}",
            "INFO"
        )
        return jsonify({"status": "forced_override", "category": category})

@app.route('/api/test_sample/<sample_name>', methods=['GET', 'POST'])
def test_sample(sample_name):
    """
    Injects a curated high-res intruder image directly into the vision pipeline.
    This guarantees 100% flawless demonstration for judges even without a physical webcam!
    """
    if sample_name in AVAILABLE_SAMPLES and os.path.exists(AVAILABLE_SAMPLES[sample_name]):
        path = AVAILABLE_SAMPLES[sample_name]
        success = vision_engine.inject_sample_image(path, hold_seconds=12.0)
        telegram_notifier.send_system_event(
            "Demonstration Sample Injected",
            f"Test sample image '{sample_name}' injected into vision pipeline.",
            "INFO"
        )
        return jsonify({"status": "injected", "sample": sample_name, "success": success})
    return jsonify({"status": "error", "message": f"Sample '{sample_name}' not found."}), 404

@app.route('/api/clear_sample', methods=['GET', 'POST'])
def clear_sample():
    """Resets vision pipeline to real-time live camera feed."""
    vision_engine.clear_sample_injection()
    return jsonify({"status": "cleared", "source": telemetry.camera_source})

@app.route('/api/toggle_flip', methods=['GET', 'POST'])
def toggle_flip():
    """Toggles camera horizontal mirror flip."""
    new_state = vision_engine.toggle_flip()
    return jsonify({"status": "toggled", "flip_horizontal": new_state})

@app.route('/api/config', methods=['POST'])
def update_config():
    """Configures thresholds, audio muting, or toggles CV window."""
    data = request.get_json(silent=True) or {}
    if "confidence_threshold" in data:
        telemetry.confidence_threshold = float(data["confidence_threshold"])
    if "local_audio_enabled" in data:
        telemetry.local_audio_enabled = bool(data["local_audio_enabled"])
    if "cv_window_active" in data:
        telemetry.cv_window_active = bool(data["cv_window_active"])
    if data.get("clear_events"):
        telemetry.clear_events()
    return jsonify({"status": "updated", "config": {
        "confidence_threshold": telemetry.confidence_threshold,
        "local_audio_enabled": telemetry.local_audio_enabled,
        "cv_window_active": telemetry.cv_window_active
    }})

@app.errorhandler(500)
def internal_server_error(e):
    telegram_notifier.send_error_alert("Flask Web Server", f"Internal Server Error (500): {str(e)}")
    return jsonify({"error": "Internal server error", "details": str(e)}), 500

def start_vision_thread():
    """Spawns the computer vision and OpenCV window thread."""
    cv_thread = threading.Thread(target=vision_engine.run_cv_loop, daemon=True)
    cv_thread.start()
    return cv_thread

if __name__ == '__main__':
    print("\n=======================================================")
    print("   🌱 AGROSONIC DEFENCE - SMART CROP PROTECTION IoT   ")
    print("=======================================================")
    print(" [✓] Initializing Live Computer Vision & YOLOv8 Engine...")
    start_vision_thread()
    print(" [✓] Computer Vision desktop window launched simultaneously.")
    print(" [✓] Starting Flask Dashboard on http://127.0.0.1:5000")
    print("=======================================================\n")
    
    # Notify Telegram channel that system is online and armed
    telegram_notifier.send_system_event(
        "AgroSonic Defence System Online",
        "Vision pipeline & IoT deterrence hub initialized and monitoring.",
        "SUCCESS"
    )

    # Run Flask server
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
