import os
import pandas as pd
import pandas_ta as ta

ATR_MULTIPLIER = 1.5
ATR_PERIOD = 14

def get_signals(client, symbol, account_id):
    """
    Evalúa las condiciones de mercado usando cTrader Open API.
    Filtro Macro: SMA200 en H1
    Filtro Micro: RSI(14) en M15
    """
    # Función dummy por ahora, se integrará con el cliente cuando lo definamos exacto
    pass
