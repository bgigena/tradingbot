from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List

# load_dotenv ya se llama en main_ctrader.py


class TelegramSettings(BaseSettings):
    """Configuración para notificaciones de Telegram."""
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)

    TELEGRAM_TOKEN: str
    TELEGRAM_CHAT_ID: str


telegram_settings = TelegramSettings()


class TradingSettings(BaseSettings):
    """Configuración general de trading y gestión de riesgo."""
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)

    # El listado de símbolos Pydantic lo parseará automáticamente desde un string JSON en el .env
    SYMBOLS: List[str]
    RISK_PERCENT: float = 3.0
    REWARD_RATIO: int
    MAGIC_NUMBER: int
    EQUITY_PROTECTION: float
    MAX_SPREAD_PIPS: float
    ATR_MULTIPLIER: float
    ATR_PERIOD: int
    BREAKEVEN_TRIGGER_R: float
    TRAILING_STEP_PIPS: int
    LOT_SIZE: float


trading_settings = TradingSettings()


class SessionSettings(BaseSettings):
    """Configuración de las sesiones operativas (Horarios)."""
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)

    SESSION_START_UTC: int
    SESSION_END_UTC: int
    
    # Forex Market Hours (Matching CET 22:00 Sun - 23:00 Fri)
    MARKET_OPEN_WEEKDAY: int = 6  # Sunday
    MARKET_OPEN_HOUR: int = 21   # 21:00 UTC = 22:00 CET
    MARKET_CLOSE_WEEKDAY: int = 4  # Friday
    MARKET_CLOSE_HOUR: int = 22  # 22:00 UTC = 23:00 CET


session_settings = SessionSettings()


class IntegrationSettings(BaseSettings):
    """Configuraciones de integración con APIs externas (MT5 y cTrader)."""
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=True)

    MT5_PATH: str = r"C:\Program Files\MetaTrader 5\terminal64.exe"
    
    # Éstas pueden no estar todavía cargadas hasta que corra setup_auth.py, por eso les damos valor default opcional
    CTRADER_CLIENT_ID: str = ""
    CTRADER_CLIENT_SECRET: str = ""
    CTRADER_REFRESH_TOKEN: str = ""
    CTRADER_ACCESS_TOKEN: str = ""


integration_settings = IntegrationSettings()
