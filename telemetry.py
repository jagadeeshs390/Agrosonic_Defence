"""
AgroSonic Defence - IoT Telemetry & State Management Module
Maintains thread-safe state for live detections, deterrence status, ESP32 IoT node telemetry,
and circular event logging for judge demo inspection.
"""

import time
import threading
from collections import deque
from datetime import datetime

class AgroTelemetry:
    def __init__(self):
        self.lock = threading.Lock()
        
        # System State: 'ARMED', 'DETERRING', 'IDLE', 'STANDBY'
        self.system_status = "ARMED"
        self.camera_source = "Webcam (Index 0)"
        self.cv_window_active = True
        self.local_audio_enabled = True
        self.confidence_threshold = 0.45
        
        # Real-time Detection State
        self.current_detection = {
            "detected": False,
            "category": "None",       # 'Birds', 'Wild Animals', 'Livestock'
            "class_name": "None",     # 'bird', 'elephant', 'cow', etc.
            "confidence": 0.0,
            "bbox": [],               # [x1, y1, x2, y2]
            "timestamp": None,
            "count": 0
        }
        
        # Deterrence Actuation State
        self.deterrence_state = {
            "active": False,
            "category": "None",
            "frequency_khz": 0.0,     # e.g., 28.5 kHz
            "frequency_display": "Idle (0 kHz)",
            "spectrum_range": "20 kHz - 65 kHz",
            "habituation_level": 1,   # 1 to 5
            "strategy": "Standby",
            "strobe_active": False,
            "strobe_hz": 0,           # e.g., 15 Hz
            "strobe_color": "#10b981",# Emerald when safe, Ruby/Amber when deterrring
            "sound_db": 0,            # Simulated SPL (e.g. 115 dB)
            "start_time": 0,
            "duration": 3.0,
            "cooldown_until": 0
        }
        
        # Category Habituation Tracking
        # Counts encounters within rolling window to adjust mitigation strategy
        self.habituation_counters = {
            "Birds": {"count": 0, "level": 1, "last_seen": 0},
            "Wild Animals": {"count": 0, "level": 1, "last_seen": 0},
            "Livestock": {"count": 0, "level": 1, "last_seen": 0}
        }
        
        # Simulated ESP32 IoT Node Hardware Telemetry
        self.esp32_telemetry = {
            "node_id": "ESP32-AGRO-NODE-01",
            "sector": "Sector 4 (North Orchard)",
            "battery_volts": 12.6,
            "battery_percent": 96,
            "solar_watts_m2": 435.0,
            "transducer_status": "ONLINE (Array 4x Piezo)",
            "piezo_boost_volts": 12.0, # boosts to 48V during deterrence
            "duty_cycle_pct": 0,
            "ambient_temp_c": 27.8,
            "ambient_humidity_pct": 58.4,
            "lux_level": 8200,
            "rssi_dbm": -62,
            "uptime_seconds": 0,
            "firmware_version": "v2.4.1-sonic"
        }
        
        self.start_epoch = time.time()
        
        # Circular Event Log (Keeps last 60 events for live dashboard and judges)
        self.event_log = deque(maxlen=60)
        self.event_counter = 0

    def update_detection(self, detected, category, class_name, confidence, bbox, count=1):
        """Update the latest detection state and record log if valid."""
        with self.lock:
            now_iso = datetime.now().strftime("%H:%M:%S")
            self.current_detection = {
                "detected": detected,
                "category": category,
                "class_name": class_name,
                "confidence": round(float(confidence), 2),
                "bbox": [int(b) for b in bbox] if bbox else [],
                "timestamp": now_iso,
                "count": count
            }

    def trigger_deterrence(self, category, frequency_khz, strategy, habituation_level, strobe_hz, sound_db=115, duration=3.0):
        """Record deterrence actuation triggered by the habituation engine."""
        with self.lock:
            now = time.time()
            now_iso = datetime.now().strftime("%H:%M:%S")
            
            frequency_display = f"{round(float(frequency_khz), 1)} kHz"
            strobe_active = True
            status_str = "SUCCESSFUL_DEFENCE"
            
            # Map strobe color by category
            color_map = {
                "Birds": "#f59e0b",         # Warning Amber
                "Wild Animals": "#ef4444",  # High-Alert Ruby Red
                "Livestock": "#06b6d4"      # Harmless Cyan Pulse
            }
            strobe_color = color_map.get(category, "#ef4444")
            
            # Update ESP32 hardware telemetry simulation for active sonic sweep
            self.esp32_telemetry["piezo_boost_volts"] = 48.0
            self.esp32_telemetry["duty_cycle_pct"] = min(100, 40 + habituation_level * 12)
            self.esp32_telemetry["transducer_status"] = f"ACTIVE ({frequency_khz:.1f} kHz Sweep)"

            self.deterrence_state = {
                "active": True,
                "category": category,
                "frequency_khz": round(float(frequency_khz), 1),
                "frequency_display": frequency_display,
                "spectrum_range": "20 kHz - 65 kHz",
                "habituation_level": habituation_level,
                "strategy": strategy,
                "strobe_active": strobe_active,
                "strobe_hz": strobe_hz,
                "strobe_color": strobe_color,
                "sound_db": sound_db,
                "start_time": now,
                "duration": duration,
                "cooldown_until": now + duration + 1.0
            }
            
            self.system_status = "DETERRING"
            
            # Record into event history
            self.event_counter += 1
            event_item = {
                "id": self.event_counter,
                "timestamp": now_iso,
                "category": category,
                "strategy": strategy,
                "frequency_khz": round(float(frequency_khz), 1),
                "strobe_hz": strobe_hz,
                "habituation_level": habituation_level,
                "sound_db": sound_db,
                "status": status_str
            }
            self.event_log.appendleft(event_item)

    def check_deterrence_timeout(self):
        """Resets deterrence to idle when timer expires."""
        with self.lock:
            if self.deterrence_state["active"]:
                if time.time() - self.deterrence_state["start_time"] > self.deterrence_state["duration"]:
                    self.deterrence_state["active"] = False
                    self.deterrence_state["strobe_active"] = False
                    self.deterrence_state["frequency_display"] = "Standby (Awaiting Intruder)"
                    self.deterrence_state["strategy"] = "Standby (Scanning Field)"
                    self.system_status = "ARMED"
                    
                    # Reset ESP32 node actuation states
                    self.esp32_telemetry["piezo_boost_volts"] = 12.0
                    self.esp32_telemetry["duty_cycle_pct"] = 0
                    self.esp32_telemetry["transducer_status"] = "STANDBY (Array Ready)"

    def update_esp32_telemetry(self):
        """Simulate realistic sensor drift and battery fluctuations."""
        with self.lock:
            uptime = int(time.time() - self.start_epoch)
            self.esp32_telemetry["uptime_seconds"] = uptime
            
            # Natural micro-variations
            import random
            drift = (random.random() - 0.5) * 0.05
            self.esp32_telemetry["battery_volts"] = round(12.55 + drift, 2)
            self.esp32_telemetry["solar_watts_m2"] = round(430.0 + random.uniform(-10.0, 15.0), 1)
            self.esp32_telemetry["ambient_temp_c"] = round(27.8 + random.uniform(-0.3, 0.4), 1)
            self.esp32_telemetry["ambient_humidity_pct"] = round(58.4 + random.uniform(-0.5, 0.6), 1)
            self.esp32_telemetry["rssi_dbm"] = int(-62 + random.randint(-2, 2))

    def get_full_status(self):
        """Thread-safe snapshot for /api/status endpoint."""
        self.check_deterrence_timeout()
        self.update_esp32_telemetry()
        with self.lock:
            return {
                "system_status": self.system_status,
                "camera_source": self.camera_source,
                "cv_window_active": self.cv_window_active,
                "local_audio_enabled": self.local_audio_enabled,
                "confidence_threshold": self.confidence_threshold,
                "detection": dict(self.current_detection),
                "deterrence": dict(self.deterrence_state),
                "habituation": {k: dict(v) for k, v in self.habituation_counters.items()},
                "esp32": dict(self.esp32_telemetry),
                "events": list(self.event_log)[:15],
                "total_events": self.event_counter,
                "server_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    def clear_events(self):
        with self.lock:
            self.event_log.clear()

# Global telemetry singleton
telemetry = AgroTelemetry()
