import pandas as pd
import pandas_ta as ta

def get_signals(symbol, df_h1, df_m15):
    """
    MASTER STRATEGY (2026 Trends):
    1. Trend (H1): EMA 200. Only buy above, only sell below.
    2. Volatility (M15): Bollinger Bands (20, 2). Price must be near or outside bands.
    3. Momentum (M15): RSI 14 (Oversold < 35, Overbought > 65).
    4. Structure (M15): Breakout of the previous candle's High (Buy) or Low (Sell).
    
    Returns: (signal: str, atr: float) or (None, None)
    """
    if len(df_h1) < 200 or len(df_m15) < 20:
        return None, None

    # --- 1. FILTRO DE TENDENCIA (H1) ---
    df_h1['ema200'] = ta.ema(df_h1['close'], length=200)
    last_close_h1 = df_h1['close'].iloc[-1]
    last_ema_h1 = df_h1['ema200'].iloc[-1]
    
    is_bullish = last_close_h1 > last_ema_h1
    is_bearish = last_close_h1 < last_ema_h1
    
    # --- 2. FILTRO DE VOLATILIDAD Y MOMENTUM (M15) ---
    # Bollinger Bands
    bb = ta.bbands(df_m15['close'], length=20, std=2)
    df_m15['bb_lower'] = bb['BBL_20_2.0']
    df_m15['bb_upper'] = bb['BBU_20_2.0']
    
    # RSI y ATR
    df_m15['rsi'] = ta.rsi(df_m15['close'], length=14)
    df_m15['atr'] = ta.atr(df_m15['high'], df_m15['low'], df_m15['close'], length=14)
    
    last_close_m15 = df_m15['close'].iloc[-1]
    last_low_m15 = df_m15['low'].iloc[-1]
    last_high_m15 = df_m15['high'].iloc[-1]
    prev_high_m15 = df_m15['high'].iloc[-2]
    prev_low_m15 = df_m15['low'].iloc[-2]
    
    lower_band = df_m15['bb_lower'].iloc[-1]
    upper_band = df_m15['bb_upper'].iloc[-1]
    rsi = df_m15['rsi'].iloc[-1]
    atr = df_m15['atr'].iloc[-1]
    
    if pd.isna(atr):
        return None, None

    # --- 3. LÓGICA DE SEÑALES ---
    
    # SEÑAL DE COMPRA: Tendencia(H1) + Sobrevendido(RSI) + Banda Inferior + Breakout(H15)
    if is_bullish:
        # Check breakout: last close is higher than previous high
        if last_close_m15 > prev_high_m15:
            if last_low_m15 <= lower_band and rsi < 35:
                print(f"🎯 [STRATEGY] Señal BUY detectada en {symbol} (Breakout Alcista + Oversold)")
                return "BUY", atr
    
    # SEÑAL DE VENTA: Tendencia(H1) + Sobrecomprado(RSI) + Banda Superior + Breakout(M15)
    if is_bearish:
        # Check breakout: last close is lower than previous low
        if last_close_m15 < prev_low_m15:
            if last_high_m15 >= upper_band and rsi > 65:
                print(f"🎯 [STRATEGY] Señal SELL detectada en {symbol} (Breakout Bajista + Overbought)")
                return "SELL", atr
    
    return None, None
