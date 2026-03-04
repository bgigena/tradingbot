import os
from dotenv import load_dotenv
from bot.auth import CTraderAuth
from bot.client import CTraderBotClient

# Cargar .env principal
load_dotenv()

def main():
    print("=========================================")
    print("🤖 Iniciando cTrader Bot (Twisted Async)")
    print("=========================================")
    
    # 1. Autenticación y Refresh de Tokens
    try:
        auth_manager = CTraderAuth()
        print("Obteniendo/Refrescando access token...")
        auth_manager.refresh_access_token()
    except Exception as e:
        print(f"Error de autenticación: {e}")
        print("💡 Recuerda correr 'python setup_auth.py' por primera vez.")
        return

    # 2. Iniciar cliente y reactor (bloqueante)
    try:
        bot = CTraderBotClient(auth_manager)
        bot.start()
    except KeyboardInterrupt:
        print("\nBot apagado manualmente.")
    except Exception as e:
        print(f"Error crítico en runtime: {e}")

if __name__ == "__main__":
    main()
