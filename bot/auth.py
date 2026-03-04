import os
import requests
from dotenv import set_key
from src.utils.settings import integration_settings

class CTraderAuth:
    def __init__(self):
        self.env_path = os.path.join(os.getcwd(), ".env")
        
        self.client_id = integration_settings.CTRADER_CLIENT_ID
        self.client_secret = integration_settings.CTRADER_CLIENT_SECRET
        self.refresh_token = integration_settings.CTRADER_REFRESH_TOKEN
        self.access_token = integration_settings.CTRADER_ACCESS_TOKEN

    def refresh_access_token(self):
        """Refreshes the access token using the stored refresh token."""
        if not self.refresh_token:
            raise ValueError("No refresh token found. Please run setup_auth.py first.")

        url = "https://openapi.ctrader.com/apps/token"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        response = requests.post(url, data=payload)
        
        if response.status_code == 200:
            data = response.json()
            self.access_token = data.get("access_token")
            # El refresh_token también puede cambiar, lo actualizamos por las dudas
            new_refresh_token = data.get("refresh_token")
            if new_refresh_token:
                self.refresh_token = new_refresh_token
                set_key(self.env_path, "CTRADER_REFRESH_TOKEN", self.refresh_token)
            
            set_key(self.env_path, "CTRADER_ACCESS_TOKEN", self.access_token)
            print("✅ Token refrescado exitosamente.")
            return self.access_token
        else:
            print(f"❌ Error al refrescar token: {response.text}")
            raise Exception("No se pudo refrescar el token de cTrader. Reautenticar.")
        
    def get_token(self):
        # En una impl robusta verificaríamos la expiración antes.
        # Por simplicidad y asegurar que el bot no se caiga mientras corre semanas enteras,
        # lo refrescamos al iniciar.
        if not self.access_token or not self.refresh_token:
             raise ValueError("Faltan tokens. Correr setup_auth.py")
        return self.access_token
