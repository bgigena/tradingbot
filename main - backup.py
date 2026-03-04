import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import time
import requests
from datetime import datetime, timedelta

# ==========================================
# ⚙️ CONFIGURACIÓN GENERAL
# ==========================================
TELEGRAM_TOKEN="8263520731:AAGMctdNPUpkfjn3ClcviZao8DBGauHvTt8"
TELEGRAM_CHAT_ID="920468935"
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe"

SYMBOLS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD"]
RISK_PERCENT = 0.01      # Riesgo del 1%
REWARD_RATIO = 3         # Ratio Beneficio/Riesgo 1:3
MAGIC_NUMBER = 987654    # Firma del bot
EQUITY_PROTECTION = 0.80 # Apagado de emergencia si se pierde el 20% del capital

# Memoria para no repetir notificaciones de Telegram
notified_deals = set()

# ==========================================
# 📡 FUNCIONES DE COMUNICACIÓN
# ==========================================
def send_telegram_msg(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

# ==========================================
# 🛡️ GESTIÓN DE RIESGO Y LOTAJE
# ==========================================
def get_lot_size(symbol, sl_pips):
    account_info = mt5.account_info()
    if account_info is None: return 0.01
    balance = account_info.balance
    
    # PARCHE DE SEGURIDAD: Si la cuenta es menor a $500, forzamos el lote mínimo (0.01)
    if balance < 500:
        return 0.01
        
    risk_amount = balance * RISK_PERCENT
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None: return 0.01
    
    tick_value = symbol_info.trade_tick_value
    lot = risk_amount / (sl_pips * tick_value)
    return max(symbol_info.volume_min, min(symbol_info.volume_max, round(lot, 2)))

def check_security():
    acc = mt5.account_info()
    if acc.equity < (acc.balance * EQUITY_PROTECTION):
        close_all_positions("Protección de Capital activada (Drawdown del 20%)")
        return False
        
    now = datetime.now()
    if now.weekday() == 4 and now.hour >= 20: # Cierre de Viernes a las 20:00 hs
        close_all_positions("Cierre de fin de semana para evitar Gaps")
        return False
    return True

def close_all_positions(reason):
    positions = mt5.positions_get()
    if positions:
        for p in positions:
            if p.magic == MAGIC_NUMBER:
                tick = mt5.symbol_info_tick(p.symbol)
                t_close = mt5.ORDER_TYPE_SELL if p.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
                p_close = tick.bid if p.type == mt5.ORDER_TYPE_BUY else tick.ask
                req = {
                    "action": mt5.TRADE_ACTION_DEAL, "symbol": p.symbol, "volume": p.volume,
                    "type": t_close, "position": p.ticket, "price": p_close,
                    "magic": MAGIC_NUMBER, "type_filling": mt5.ORDER_FILLING_IOC,
                }
                mt5.order_send(req)
        send_telegram_msg(f"🔒 <b>CIERRE TOTAL:</b> {reason}")

# ==========================================
# 🧠 LÓGICA DE TRADING (DOBLE TEMPORALIDAD)
# ==========================================
def get_signals(symbol):
    # --- 1. FILTRO MACRO (Tendencia en 1 Hora) ---
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 200)
    if rates_h1 is None or len(rates_h1) < 200: return None
    df_h1 = pd.DataFrame(rates_h1)
    df_h1['sma200'] = ta.sma(df_h1['close'], length=200)
    
    close_h1 = df_h1['close'].iloc[-1]
    sma_h1 = df_h1['sma200'].iloc[-1]
    tendencia_macro = "ALCISTA" if close_h1 > sma_h1 else "BAJISTA"

    # --- 2. FILTRO MICRO (Entrada en 15 Minutos) ---
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 100)
    if rates_m15 is None or len(rates_m15) < 100: return None
    df_m15 = pd.DataFrame(rates_m15)
    
    rsi = ta.rsi(df_m15['close'], length=14).iloc[-1]
    last_close = df_m15['close'].iloc[-1]
    
    # Soportes y Resistencias de las últimas 50 velas en M15
    resistencia = df_m15['high'].rolling(window=50).max().iloc[-1]
    soporte = df_m15['low'].rolling(window=50).min().iloc[-1]

    direction = None

    # Lógica de entrada alineando Macro (H1) con Micro (M15)
    if tendencia_macro == "ALCISTA":
        # Buscamos un rebote en el soporte con el RSI saliendo de sobreventa
        if last_close <= (soporte * 1.001) and rsi < 40:
            direction = "BUY"
            
    elif tendencia_macro == "BAJISTA":
        # Buscamos un rebote en la resistencia con el RSI saliendo de sobrecompra
        if last_close >= (resistencia * 0.999) and rsi > 60:
            direction = "SELL"

    # Dashboard visual en consola
    print(f"[{symbol:^7}] H1: {tendencia_macro:^7} | M15 RSI: {rsi:4.1f} | Acción: {'ESPERANDO' if not direction else direction}")
    return direction

def open_position(symbol, direction):
    s_info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    point = s_info.point
    sl_pips = 200 # 20 pips estándar
    
    price = tick.ask if direction == "BUY" else tick.bid
    sl = price - (sl_pips * point) if direction == "BUY" else price + (sl_pips * point)
    tp = price + (sl_pips * REWARD_RATIO * point) if direction == "BUY" else price - (sl_pips * REWARD_RATIO * point)
    lot = get_lot_size(symbol, 20)
    
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": MAGIC_NUMBER,
        "comment": "Bot Gemini",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        msg = f"🚀 <b>ORDEN EXITOSA</b>\nPar: {symbol}\nTipo: {direction}\nLote: {lot}\nPrecio: {price:.5f}\nSL: {sl:.5f} | TP: {tp:.5f}"
        send_telegram_msg(msg)
        print(f"[{symbol}] Operación {direction} abierta con éxito.")
    else:
        send_telegram_msg(f"❌ Error al abrir en {symbol}: {result.comment}")

# ==========================================
# 🔄 BUCLE PRINCIPAL
# ==========================================
if mt5.initialize(path=MT5_PATH):
    acc_info = mt5.account_info()
    login_msg = f"✅ <b>Bot Online</b>\nCuenta: {acc_info.login}\nBalance: ${acc_info.balance:.2f}"
    send_telegram_msg(login_msg)
    print("Conexión exitosa a MT5. Iniciando escaneo...")
    
    try:
        while True:
            if check_security():
                print(f"\n--- Escaneo de Mercado: {datetime.now().strftime('%H:%M:%S')} ---")
                
                # 1. RASTREADOR DE CIERRES (Para avisar por Telegram)
                from_date = datetime.now() - timedelta(minutes=15)
                history_deals = mt5.history_deals_get(from_date, datetime.now())
                
                if history_deals:
                    for deal in history_deals:
                        if deal.magic == MAGIC_NUMBER and deal.entry == mt5.DEAL_ENTRY_OUT:
                            if deal.ticket not in notified_deals:
                                resultado = "✅ TAKE PROFIT" if deal.profit > 0 else "❌ STOP LOSS"
                                msg_cierre = (f"🔔 <b>OPERACIÓN CERRADA</b>\n"
                                              f"Par: {deal.symbol}\n"
                                              f"Resultado: {resultado}\n"
                                              f"Profit: ${deal.profit:.2f}")
                                send_telegram_msg(msg_cierre)
                                notified_deals.add(deal.ticket)
                
                # 2. ESCANEO DE SÍMBOLOS Y SEÑALES
                for sym in SYMBOLS:
                    pos = mt5.positions_get(symbol=sym)
                    
                    # Verificamos si ya hay una posición abierta por el bot en este par
                    active_bot_pos = [p for p in pos if p.magic == MAGIC_NUMBER] if pos else []
                    
                    if not active_bot_pos:
                        signal = get_signals(sym)
                        if signal: 
                            open_position(sym, signal)
                    else:
                        print(f"[{sym:^7}] Posición activa en curso. Monitoreando...")
                        
            # Espera 30 segundos para no saturar el servidor ni tu PC
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\nBot detenido manualmente por el usuario.")
        mt5.shutdown()
else:
    print("Error al iniciar MT5. Revisa la ruta (MT5_PATH) y que el programa esté cerrado/ejecutado como administrador.")