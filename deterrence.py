"""
AgroSonic Defence - Adaptive Acoustic & Visual Deterrence Simulation Module
Implements:
1. Multi-frequency ultrasonic acoustic deterrence (20 kHz - 65 kHz simulation)
2. Habituation mitigation engine (dynamic frequency hopping, chirp sweeps, chaos pulses)
3. Windows local audio actuation via winsound (audible acoustic translation thread)
4. Synchronized visual LED strobe simulation logic
"""

import time
import queue
import random
import threading
from telemetry import telemetry
from telegram_notifier import telegram_notifier

# Try importing winsound for native Windows sound actuation
try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

class AudioActuatorWorker(threading.Thread):
    """
    Dedicated non-blocking background thread for audible acoustic feedback on Windows.
    Translates the simulated 20-65 kHz ultrasonic sweeps into audible acoustic cues
    so observers and judges can hear the physical actuation during demonstrations.
    """
    def __init__(self):
        super().__init__(daemon=True)
        self.cmd_queue = queue.Queue(maxsize=10)
        self.running = True

    def run(self):
        while self.running:
            try:
                task = self.cmd_queue.get(timeout=0.2)
                if task is None:
                    break
                pattern_type, base_freq, habituation_level, duration = task
                self._play_acoustic_pattern(pattern_type, base_freq, habituation_level, duration)
                self.cmd_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                print(f"[AcousticWorker] Playback notice: {e}")

    def _play_acoustic_pattern(self, pattern_type, base_freq, habituation_level, duration):
        if not HAS_WINSOUND or not telemetry.local_audio_enabled:
            time.sleep(0.3)
            return

        if pattern_type in ("NONE", None):
            return

        try:
            # Continuous Siren Modulation:
            # Instead of discrete electronic beeps, step frequencies in rapid contiguous
            # increments (12-18ms) to synthesize an authentic continuous analog siren wail.
            if pattern_type in ("URGENT_YELP_SIREN", "RAPID_CHIRP", "CHAOS_MODULATION") or habituation_level >= 3:
                # Fast Urgent Yelp Siren (fast rising/falling frequency sweep: 650 Hz <-> 1450 Hz)
                for _ in range(3):
                    for f in range(650, 1450, 55):
                        winsound.Beep(f, 12)
                    for f in range(1450, 650, -55):
                        winsound.Beep(f, 12)
            elif pattern_type in ("EMERGENCY_WAIL_SIREN", "DESCENDING_SWEEP") or habituation_level >= 2:
                # Authentic Emergency Perimeter Wail Siren (continuous smooth sweep: 480 Hz <-> 1260 Hz)
                for _ in range(2):
                    for f in range(480, 1260, 32):
                        winsound.Beep(f, 18)
                    for f in range(1260, 480, -32):
                        winsound.Beep(f, 18)
            elif pattern_type in ("SECURITY_HORN_SWEEP", "PULSED_NUDGE"):
                # Lower-frequency security warning horn sweep (420 Hz <-> 850 Hz)
                for f in range(420, 850, 30):
                    winsound.Beep(f, 20)
                for f in range(850, 420, -30):
                    winsound.Beep(f, 20)
            else:
                # Standard Emergency Perimeter Siren
                for f in range(500, 1200, 35):
                    winsound.Beep(f, 18)
                for f in range(1200, 500, -35):
                    winsound.Beep(f, 18)
        except Exception as e:
            # Non-fatal if audio device is unavailable
            pass

    def queue_actuation(self, pattern_type, base_freq, habituation_level, duration):
        if pattern_type in ("NONE", None):
            return
        if not self.cmd_queue.full():
            try:
                self.cmd_queue.put_nowait((pattern_type, base_freq, habituation_level, duration))
            except queue.Full:
                pass


class HabituationDeterrenceEngine:
    """
    Core intelligence engine that analyzes detected intruder categories, evaluates
    encounter repetition history (habituation index), and calculates the optimum
    multi-frequency acoustic profile & visual strobe pattern.
    """
    def __init__(self):
        self.audio_worker = AudioActuatorWorker()
        self.audio_worker.start()
        self.last_trigger_time = 0
        self.cooldown_seconds = 1.2  # Prevent spamming audio while maintaining responsiveness
        
        # Category acoustic profiles within the 20 kHz to 65 kHz ultrasonic spectrum
        self.category_profiles = {
            "Birds": {
                "freq_min": 32.0,
                "freq_max": 62.0,
                "default_pattern": "URGENT_YELP_SIREN",
                "strobe_base_hz": 18,
                "sound_db": 118,
                "strategies": [
                    "High-Frequency Acoustic Chirp (34 kHz)",
                    "Dual Harmonic Burst Sweep (42-58 kHz)",
                    "Randomized Ultrasonic Hop (35-62 kHz)",
                    "Acoustic Disruptor with Multi-Strobe (48 kHz)",
                    "Maximum Dynamic Chaos Agitator (20-65 kHz Full Band)"
                ]
            },
            "Wild Animals": {
                "freq_min": 21.0,
                "freq_max": 46.0,
                "default_pattern": "EMERGENCY_WAIL_SIREN",
                "strobe_base_hz": 24,
                "sound_db": 125,
                "strategies": [
                    "Penetrating Ultrasonic Sweep (24-38 kHz)",
                    "Dual-Wave High-SPL Pulsing (28-44 kHz)",
                    "Erratic Frequency Shift Sweep (22-46 kHz)",
                    "Predator Alarm Synthesizer + 24Hz Strobe",
                    "Max Force Multi-Spectral Ultrasonic Shockwave"
                ]
            },
            "Livestock": {
                "freq_min": 20.0,
                "freq_max": 28.0,
                "default_pattern": "SECURITY_HORN_SWEEP",
                "strobe_base_hz": 6,
                "sound_db": 98,
                "strategies": [
                    "Gentle Acoustic Boundary Pulse (22 kHz)",
                    "Harmonic Soft Redirection Nudge (24 kHz)",
                    "Intermittent Low-Intensity Sweep (21-27 kHz)",
                    "Pulsed Acoustic Barrier Alert (26 kHz)",
                    "Dynamic Grazing Herd Repellent (20-28 kHz)"
                ]
            }
        }

    def evaluate_and_deter(self, category, confidence, class_name="Target"):
        """
        Called when a target entity is detected.
        Applies habituation mitigation algorithms to calculate frequency, strobe, and actuation.
        """
        if category not in self.category_profiles:
            return None

        now = time.time()
        
        # Debounce to prevent audio buffer saturation
        if now - self.last_trigger_time < self.cooldown_seconds:
            return None

        self.last_trigger_time = now

        profile = self.category_profiles[category]
        
        # Habituation Mitigation Logic:
        # Check time since last encounter with this category.
        # If seen within 120 seconds, pests may be habituating -> increment mitigation level!
        h_info = telemetry.habituation_counters.get(category, {"count": 0, "level": 1, "last_seen": 0})
        time_since_last = now - h_info["last_seen"]
        
        if time_since_last < 120 and h_info["last_seen"] > 0:
            h_info["count"] += 1
            # Escalate habituation mitigation level (1 to 5)
            h_info["level"] = min(5, 1 + (h_info["count"] // 2))
        else:
            # If long absence, gradually decay habituation level
            h_info["count"] = max(0, h_info["count"] - 1)
            h_info["level"] = max(1, h_info["level"])
            
        h_info["last_seen"] = now
        level = h_info["level"]
        telemetry.habituation_counters[category] = h_info

        # Select strategy matching habituation mitigation level
        strategy_index = min(level - 1, len(profile["strategies"]) - 1)
        strategy_name = profile["strategies"][strategy_index]

        # Calculate exact target ultrasonic frequency within 20 - 65 kHz range
        freq_min = profile["freq_min"]
        freq_max = profile["freq_max"]
        
        # Higher habituation levels inject dynamic frequency agility to prevent acoustic accommodation
        if level == 1:
            target_freq = freq_min + (freq_max - freq_min) * 0.4
            pattern = profile["default_pattern"]
            strobe_hz = profile["strobe_base_hz"]
        elif level == 2:
            target_freq = freq_min + (freq_max - freq_min) * 0.7
            pattern = profile["default_pattern"]
            strobe_hz = min(30, profile["strobe_base_hz"] + 4)
        elif level == 3:
            # Pseudo-random frequency hopping
            target_freq = random.uniform(freq_min, freq_max)
            pattern = "CHAOS_MODULATION"
            strobe_hz = min(30, profile["strobe_base_hz"] + 8)
        elif level >= 4:
            # Broad-spectrum chaotic sweeping
            target_freq = random.uniform(20.5, 64.5)
            pattern = "CHAOS_MODULATION"
            strobe_hz = min(30, profile["strobe_base_hz"] + 12)

        duration = 3.0  # seconds
        sound_db = profile["sound_db"] + (level * 2)

        # Trigger telemetry state update
        telemetry.trigger_deterrence(
            category=category,
            frequency_khz=target_freq,
            strategy=strategy_name,
            habituation_level=level,
            strobe_hz=strobe_hz,
            sound_db=sound_db,
            duration=duration
        )

        # Automated Telegram Bot Alert Hook (Animals & Birds only - Never humans)
        is_human = any(h in str(category).lower() or h in str(class_name).lower() for h in ("human", "person", "people", "man", "woman"))
        if not is_human:
            try:
                telegram_notifier.send_detection_alert(
                    category=category,
                    class_name=class_name,
                    confidence=confidence,
                    sector="Sector 4 (North Orchard)",
                    strategy=strategy_name,
                    frequency_khz=target_freq,
                    habituation_level=level
                )
            except Exception as e:
                print(f"[DeterrenceEngine] Telegram notify exception: {e}")

        # Actuate local sound simulation in background worker
        self.audio_worker.queue_actuation(pattern, target_freq, level, duration)

        return {
            "category": category,
            "frequency_khz": target_freq,
            "strategy": strategy_name,
            "habituation_level": level,
            "strobe_hz": strobe_hz,
            "sound_db": sound_db
        }

# Global singleton
deterrence_engine = HabituationDeterrenceEngine()
