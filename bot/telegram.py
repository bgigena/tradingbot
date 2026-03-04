import requests
import os


TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_msg(message: str) -> None:
    """Envía un mensaje de texto al chat de Telegram configurado."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print(f"[Telegram] Token no configurado. Mensaje: {message}")
        return

    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if not resp.ok:
            print(f"[Telegram] Error HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[Telegram] Error de red: {e}")
