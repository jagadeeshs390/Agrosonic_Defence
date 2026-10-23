"""
AgroSonic Defence - Telegram Bot Notification Service
Provides real-time alert dispatching and error monitoring via Telegram Bot API using the `requests` library.

Credentials loaded securely from environment variables:
- TELEGRAM_BOT_TOKEN: Bot token provided by @BotFather (e.g. 123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ)
- TELEGRAM_CHAT_ID: Numeric chat ID or group/channel ID (e.g. 987654321 or -100123456789)
"""

import os
import sys
import time
from datetime import datetime
import requests

# Ensure console supports UTF-8 on Windows
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def _load_env_file():
    """Lightweight .env loader without requiring external python-dotenv library."""
    env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        if key not in os.environ or not os.environ[key]:
                            os.environ[key] = val
        except Exception:
            pass

_load_env_file()


class TelegramNotifier:
    """
    Manages Telegram Bot API communication for intrusion alerts, system milestones,
    and exception logging.
    """

    def __init__(self):
        # Load from environment, .env file, or configured user bot credentials
        self.bot_token = (
            os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
            or "8834106204:AAE-zrf0RX7V4gI2emxI2jovh8SFRzlMAH0"
        )
        self.chat_id = (
            os.environ.get("TELEGRAM_CHAT_ID", "").strip()
            or "5446532869"
        )
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        
        # Debounce tracking to avoid spamming the chat during continuous video detection
        self.last_alert_time = 0
        self.cooldown_seconds = 8.0
        self.last_error_time = 0
        self.error_cooldown_seconds = 30.0

    def is_configured(self) -> bool:
        """Returns True if bot token and chat ID are both present."""
        # Dynamically reload from environment in case variables were set after import
        if not self.bot_token:
            self.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
            if self.bot_token:
                self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        if not self.chat_id:
            self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
            
        return bool(self.bot_token and self.chat_id)

    def _mask_token(self) -> str:
        if not self.bot_token:
            return "<UNSET>"
        if len(self.bot_token) > 12:
            return f"{self.bot_token[:6]}...{self.bot_token[-4:]}"
        return "***"

    def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """
        Sends a text message via Telegram Bot API using the `requests` library.
        Returns True on success, False otherwise.
        """
        if not self.is_configured():
            print(f"[Telegram] Bot token or chat ID not set. (TOKEN: {self._mask_token()}, CHAT_ID: {self.chat_id or '<UNSET>'})")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }

        try:
            response = requests.post(url, json=payload, timeout=12.0)
            if response.status_code == 200:
                print(f"[Telegram] [OK] Notification delivered to chat {self.chat_id}")
                return True
            else:
                print(f"[Telegram] API error {response.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"[Telegram] Network/connection error sending message: {e}")
            return False

    def send_detection_alert(self, category: str, class_name: str, confidence: float,
                             sector: str = "Sector 4 (North Orchard)", strategy: str = None,
                             frequency_khz: float = None, habituation_level: int = 1) -> bool:
        """
        Dispatches a structured intruder alert to Telegram with anti-spam debounce.
        Filters out any human/person detection.
        """
        # User constraint: Do not send Telegram alert if human/person
        cat_lower = str(category).lower().strip()
        class_lower = str(class_name).lower().strip()
        if any(h in cat_lower or h in class_lower for h in ("human", "person", "people", "man", "woman")):
            print(f"[Telegram] Suppressed alert: target '{class_name}' ({category}) is identified as human.")
            return False

        now = time.time()
        if now - self.last_alert_time < self.cooldown_seconds:
            return False

        self.last_alert_time = now
        conf_pct = int(confidence * 100) if confidence <= 1.0 else int(confidence)
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Pick appropriate category icon
        cat_upper = category.upper()
        if "BIRD" in cat_upper:
            icon = "🦅"
        elif "WILD" in cat_upper:
            icon = "🐗"
        elif "LIVESTOCK" in cat_upper:
            icon = "🐄"
        else:
            icon = "⚠️"

        strat_line = f"\n⚡ <b>Mitigation:</b> <code>{strategy}</code>" if strategy else ""
        freq_line = f"\n🔊 <b>Ultrasonic Frequency:</b> <code>{frequency_khz:.1f} kHz</code>" if frequency_khz else ""

        message = (
            f"{icon} <b>AGROSONIC DEFENCE ALERT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Target:</b> <b>{class_name.capitalize()}</b> ({category})\n"
            f"📊 <b>Confidence:</b> <code>{conf_pct}%</code>\n"
            f"📍 <b>Location:</b> {sector}\n"
            f"🛡️ <b>Habituation Level:</b> <b>L{habituation_level}</b>"
            f"{strat_line}"
            f"{freq_line}\n"
            f"⏱️ <b>Timestamp:</b> <code>{timestamp_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ <i>Automated multi-spectral ultrasonic actuation triggered.</i>"
        )

        return self.send_message(message, parse_mode="HTML")

    def send_system_event(self, title: str, details: str, status: str = "INFO") -> bool:
        """
        Sends an operational or administrative system event notification.
        """
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        status_icon = "🟢" if status == "SUCCESS" else ("🟡" if status == "INFO" else "🔴")

        message = (
            f"{status_icon} <b>AGROSONIC SYSTEM NOTIFICATION</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>Event:</b> {title}\n"
            f"📝 <b>Details:</b> {details}\n"
            f"⏱️ <b>Time:</b> <code>{timestamp_str}</code>"
        )
        return self.send_message(message, parse_mode="HTML")

    def send_error_alert(self, component: str, error_message: str) -> bool:
        """
        Sends a critical error alert with cooldown to avoid cascading error loops.
        """
        now = time.time()
        if now - self.last_error_time < self.error_cooldown_seconds:
            return False

        self.last_error_time = now
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        message = (
            f"🚨 <b>AGROSONIC SYSTEM ERROR ALERT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>Component:</b> <code>{component}</code>\n"
            f"❌ <b>Error:</b> <code>{error_message}</code>\n"
            f"⏱️ <b>Time:</b> <code>{timestamp_str}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"ℹ️ <i>Check host terminal logs for complete traceback.</i>"
        )
        return self.send_message(message, parse_mode="HTML")


# Global singleton instance
telegram_notifier = TelegramNotifier()


if __name__ == "__main__":
    print("\n=======================================================")
    print("   AGROSONIC TELEGRAM BOT NOTIFICATION SERVICE TEST   ")
    print("=======================================================")
    
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    print(f"[*] TELEGRAM_BOT_TOKEN : {'Set (' + token[:6] + '...' + token[-4:] + ')' if token else 'NOT SET'}")
    print(f"[*] TELEGRAM_CHAT_ID   : {chat_id if chat_id else 'NOT SET'}\n")

    if not telegram_notifier.is_configured():
        print("[!] To send real messages to your Telegram account:")
        print("    1. Create a bot via @BotFather on Telegram to get your TELEGRAM_BOT_TOKEN.")
        print("    2. Start your bot and message @userinfobot to get your TELEGRAM_CHAT_ID.")
        print("    3. In your terminal run:")
        print('       $env:TELEGRAM_BOT_TOKEN="your_bot_token_here"')
        print('       $env:TELEGRAM_CHAT_ID="your_chat_id_here"')
        print("    4. Re-run this script: python telegram_notifier.py\n")
    else:
        print("[+] Sending test alert to Telegram chat...")
        success = telegram_notifier.send_detection_alert(
            category="Wild Animals",
            class_name="Wild Boar",
            confidence=0.96,
            sector="Sector 4 (North Orchard)",
            strategy="Penetrating Ultrasonic Sweep (24-38 kHz)",
            frequency_khz=34.5,
            habituation_level=2
        )
        if success:
            print("[OK] Test alert delivered successfully!")
        else:
            print("[FAIL] Failed to deliver test alert. Check token and chat_id.")
