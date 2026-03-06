print("📢 [Global] Iniciando carga de .env...")
from dotenv import load_dotenv
load_dotenv(override=True)
print("✅ [Global] .env cargado.")

print("📢 [Global] Importando bot.auth y bot.client...")
from bot.auth import CTraderAuth
from bot.client import CTraderBotClient
print("✅ [Global] Importaciones completas.")

def main():
    print("=========================================")
    print("🤖 Iniciando cTrader Bot (Twisted Async)")
    print("=========================================")
    
    # 1. Autenticación y Refresh de Tokens
    try:
        print("🔑 Inicializando CTraderAuth...")
        auth_manager = CTraderAuth()
        print("🔄 Obteniendo/Refrescando access token...")
        auth_manager.refresh_access_token()
    except Exception as e:
        import traceback
        print(f"❌ Error de autenticación: {e}")
        traceback.print_exc()
        print("💡 Recuerda correr 'python setup_auth.py' por primera vez.")
        return

    # 2. Iniciar cliente y reactor (bloqueante)
    try:
        print("🏗️ Inicializando CTraderBotClient...")
        bot = CTraderBotClient(auth_manager)
        bot.start()
    except KeyboardInterrupt:
        print("\nBot apagado manualmente.")
    except Exception as e:
        print(f"Error crítico en runtime: {e}")

if __name__ == "__main__":
    main()
