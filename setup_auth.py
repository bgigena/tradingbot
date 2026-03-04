import os
import urllib.parse
from dotenv import set_key

def main():
    print("==============================================")
    print("   cTrader Open API - Configuración Inicial   ")
    print("==============================================")
    
    print("\n1. Ve a https://openapi.ctrader.com/")
    print("2. Crea una aplicación y obten el Client ID y Client Secret")
    print("3. Como 'Redirect URI' pon: http://localhost")
    print("----------------------------------------------")
    
    client_id = input("\nClient ID: ").strip()
    client_secret = input("Client Secret: ").strip()
    
    if not client_id or not client_secret:
        print("❌ Faltan datos.")
        return

    # Endpoint OAuth cTrader
    auth_url = (f"https://openapi.ctrader.com/apps/auth?"
                f"client_id={client_id}&redirect_uri=http://localhost"
                f"&scope=trading")
    
    print("\n==============================================")
    print("👉 Abre este enlace en el navegador:")
    print(auth_url)
    print("==============================================")
    print("\nDespués de autorizar, el navegador te redirigirá a una página que no carga (http://localhost/?code=XXX).")
    print("Copia el código que aparece en la URL (todo lo que está después de ?code=)")
    
    auth_code = input("\nCódigo de autorización (code=): ").strip()
    if not auth_code:
        print("❌ Código no proveído.")
        return

    print("\nObteniendo Refresh Token...")
    import requests
    token_url = "https://openapi.ctrader.com/apps/token"
    payload = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": "http://localhost"
    }

    try:
        res = requests.post(token_url, data=payload)
        res_data = res.json()
        
        if "refresh_token" in res_data:
            print("\n✅ Autenticación Exitosa!")
            print("Token obtenido, guardando en .env...")
            
            env_file = ".env"
            set_key(env_file, "CTRADER_CLIENT_ID", client_id)
            set_key(env_file, "CTRADER_CLIENT_SECRET", client_secret)
            set_key(env_file, "CTRADER_REFRESH_TOKEN", res_data["refresh_token"])
            set_key(env_file, "CTRADER_ACCESS_TOKEN", res_data["access_token"])
            
            # Asumiendo que obtuvimos la info de la cuenta
            # cTrader manda una lista de cuentas en algunos casos, esto lo manejamos luego en el bot
            print(f"Todo listo. Ahora podés correr el bot de trading.")
        else:
            print("\n❌ Error del servidor cTrader:")
            print(res_data)
    except Exception as e:
         print(f"Error HTTP: {e}")

if __name__ == "__main__":
    main()
