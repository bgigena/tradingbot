import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import time
import requests
import os
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Cargamos variables de entorno
load_dotenv()

# ==========================================
# ⚙️ CONFIGURACIÓN GENERAL
# ==========================================
TELEGRAM_TOKEN  = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
MT5_PATH        = os.getenv("MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe")

SYMBOLS          = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD"]
RISK_PERCENT     = float(os.getenv("RISK_PERCENT",    "0.01"))
REWARD_RATIO     = int(os.getenv("REWARD_RATIO",      "3"))
MAGIC_NUMBER     = int(os.getenv("MAGIC_NUMBER",      "987654"))
EQUITY_PROTECTION = float(os.getenv("EQUITY_PROTECTION", "0.80"))

# --- Filtro de sesión (hora UTC) ---
SESSION_START_UTC = 7   # Apertura Londres
SESSION_END_UTC   = 20  # Cierre Nueva York

# --- Filtro de spread máximo (en pips) ---
MAX_SPREAD_PIPS = 3.0

# --- ATR para SL dinámico ---
ATR_MULTIPLIER = 1.5    # SL = ATR * multiplicador
ATR_PERIOD     = 14

# --- Breakeven / Trailing ---
BREAKEVEN_TRIGGER_R = 1.0  # Mueve SL a BE cuando el precio avanza 1R
TRAILING_STEP_PIPS  = 10   # Pasos del trailing stop en pips

# Memoria para no repetir notificaciones de Telegram
notified_deals = set()

# ==========================================
# 📡 FUNCIONES DE COMUNICACIÓN
# ==========================================
def send_telegram_msg(message):
    url     = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error Telegram: {e}")

# ==========================================
# 🛡️ GESTIÓN DE RIESGO Y LOTAJE
# ==========================================
def get_lot_size(symbol, sl_points):
    account_info = mt5.account_info()
    if account_info is None:
        return 0.01
    balance = account_info.balance

    if balance < 500:
        return 0.01

    risk_amount = balance * RISK_PERCENT
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return 0.01

    tick_value = symbol_info.trade_tick_value
    tick_size  = symbol_info.trade_tick_size
    point      = symbol_info.point

    # Valor monetario del SL en la divisa de la cuenta
    sl_ticks = sl_points / tick_size
    sl_money  = sl_ticks * tick_value

    if sl_money == 0:
        return 0.01

    lot = risk_amount / sl_money
    return max(symbol_info.volume_min, min(symbol_info.volume_max, round(lot, 2)))

def is_session_active():
    """Filtra sesión Londres + Nueva York (07:00 – 20:00 UTC)."""
    now_utc = datetime.now(timezone.utc)
    # Cierre anticipado los viernes a las 20:00 UTC (ya lo maneja check_security)
    return SESSION_START_UTC <= now_utc.hour < SESSION_END_UTC

def is_spread_ok(symbol):
    """Verifica que el spread actual no supere MAX_SPREAD_PIPS."""
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    if info is None or tick is None:
        return False
    spread_pips = (tick.ask - tick.bid) / (info.point * 10)
    return spread_pips <= MAX_SPREAD_PIPS

def check_security():
    acc = mt5.account_info()
    if acc is None:
        return False
    if acc.equity < (acc.balance * EQUITY_PROTECTION):
        close_all_positions("Protección de Capital activada (Drawdown del 20%)")
        return False

    now = datetime.now()
    if now.weekday() == 4 and now.hour >= 20:
        close_all_positions("Cierre de fin de semana para evitar Gaps")
        return False
    return True

def close_all_positions(reason):
    positions = mt5.positions_get()
    if positions:
        for p in positions:
            if p.magic == MAGIC_NUMBER:
                tick    = mt5.symbol_info_tick(p.symbol)
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
# 🔄 BREAKEVEN / TRAILING STOP
# ==========================================
def manage_open_positions():
    """
    Para cada posición abierta del bot:
    - Mueve SL a breakeven cuando el precio avanza >= 1R
    - Aplica trailing stop cada TRAILING_STEP_PIPS
    """
    positions = mt5.positions_get()
    if not positions:
        return

    for p in positions:
        if p.magic != MAGIC_NUMBER:
            continue

        info  = mt5.symbol_info(p.symbol)
        tick  = mt5.symbol_info_tick(p.symbol)
        point = info.point
        step  = TRAILING_STEP_PIPS * 10 * point  # en precio

        if p.type == mt5.ORDER_TYPE_BUY:
            current_price = tick.bid
            profit_dist   = current_price - p.price_open
            sl_distance   = p.price_open - p.sl if p.sl != 0 else None

            if sl_distance is None:
                continue

            # 1. Breakeven
            if profit_dist >= sl_distance and p.sl < p.price_open:
                new_sl = round(p.price_open + point, info.digits)
                _modify_sl(p, new_sl)

            # 2. Trailing: si el precio sube más de un paso desde el SL actual
            elif p.sl > 0 and current_price - p.sl > sl_distance + step:
                new_sl = round(current_price - sl_distance, info.digits)
                if new_sl > p.sl:
                    _modify_sl(p, new_sl)

        elif p.type == mt5.ORDER_TYPE_SELL:
            current_price = tick.ask
            profit_dist   = p.price_open - current_price
            sl_distance   = p.sl - p.price_open if p.sl != 0 else None

            if sl_distance is None:
                continue

            # 1. Breakeven
            if profit_dist >= sl_distance and p.sl > p.price_open:
                new_sl = round(p.price_open - point, info.digits)
                _modify_sl(p, new_sl)

            # 2. Trailing
            elif p.sl > 0 and p.sl - current_price > sl_distance + step:
                new_sl = round(current_price + sl_distance, info.digits)
                if new_sl < p.sl:
                    _modify_sl(p, new_sl)

def _modify_sl(position, new_sl):
    req = {
        "action":   mt5.TRADE_ACTION_SLTP,
        "position": position.ticket,
        "sl":       new_sl,
        "tp":       position.tp,
    }
    mt5.order_send(req)

# ==========================================
# 🧠 LÓGICA DE TRADING (DOBLE TEMPORALIDAD)
# ==========================================
def get_signals(symbol):
    # --- 1. FILTRO MACRO (Tendencia en 1 Hora) ---
    rates_h1 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 200)
    if rates_h1 is None or len(rates_h1) < 200:
        return None, None
    df_h1 = pd.DataFrame(rates_h1)
    df_h1['sma200'] = ta.sma(df_h1['close'], length=200)

    close_h1      = df_h1['close'].iloc[-2]   # ✅ Vela CERRADA ([-2])
    sma_h1        = df_h1['sma200'].iloc[-2]
    tendencia_macro = "ALCISTA" if close_h1 > sma_h1 else "BAJISTA"

    # --- 2. FILTRO MICRO (Entrada en 15 Minutos, vela cerrada) ---
    rates_m15 = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 115)
    if rates_m15 is None or len(rates_m15) < 115:
        return None, None
    df_m15 = pd.DataFrame(rates_m15)

    # ✅ Usamos la vela [-2] (última cerrada) para todas las señales
    rsi        = ta.rsi(df_m15['close'], length=14).iloc[-2]
    last_close = df_m15['close'].iloc[-2]

    # ATR para SL dinámico
    atr_series = ta.atr(df_m15['high'], df_m15['low'], df_m15['close'], length=ATR_PERIOD)
    atr_value  = atr_series.iloc[-2] if atr_series is not None else None

    # Soportes y Resistencias de las últimas 50 velas en M15 (excluyendo vela actual)
    resistencia = df_m15['high'].iloc[:-1].rolling(window=50).max().iloc[-1]
    soporte     = df_m15['low'].iloc[:-1].rolling(window=50).min().iloc[-1]

    direction = None

    # ✅ RSI umbrales más estrictos: <30 sobreventa / >70 sobrecompra
    if tendencia_macro == "ALCISTA":
        if last_close <= (soporte * 1.001) and rsi < 30:
            direction = "BUY"

    elif tendencia_macro == "BAJISTA":
        if last_close >= (resistencia * 0.999) and rsi > 70:
            direction = "SELL"

    # Dashboard visual en consola
    rsi_str = f"{rsi:4.1f}" if rsi == rsi else " N/A"
    print(f"[{symbol:^7}] H1: {tendencia_macro:^7} | M15 RSI: {rsi_str} | Acción: {'ESPERANDO' if not direction else direction}")
    return direction, atr_value

def open_position(symbol, direction, atr_value):
    s_info = mt5.symbol_info(symbol)
    tick   = mt5.symbol_info_tick(symbol)
    point  = s_info.point

    # ✅ SL dinámico basado en ATR
    if atr_value and atr_value > 0:
        sl_distance = atr_value * ATR_MULTIPLIER
    else:
        sl_distance = 200 * point  # fallback a 20 pips

    price = tick.ask if direction == "BUY" else tick.bid
    sl    = round(price - sl_distance, s_info.digits) if direction == "BUY" else round(price + sl_distance, s_info.digits)
    tp    = round(price + sl_distance * REWARD_RATIO, s_info.digits) if direction == "BUY" else round(price - sl_distance * REWARD_RATIO, s_info.digits)
    lot   = get_lot_size(symbol, sl_distance)

    sl_pips = round(sl_distance / (point * 10), 1)

    request = {
        "action":       mt5.TRADE_ACTION_DEAL,
        "symbol":       symbol,
        "volume":       lot,
        "type":         mt5.ORDER_TYPE_BUY if direction == "BUY" else mt5.ORDER_TYPE_SELL,
        "price":        price,
        "sl":           sl,
        "tp":           tp,
        "magic":        MAGIC_NUMBER,
        "comment":      "Bot Gemini v2",
        "type_time":    mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        msg = (f"🚀 <b>ORDEN EXITOSA</b>\n"
               f"Par: {symbol} | {direction}\n"
               f"Lote: {lot} | SL: {sl_pips:.1f} pips (ATR)\n"
               f"Precio: {price:.5f}\n"
               f"SL: {sl:.5f} | TP: {tp:.5f}")
        send_telegram_msg(msg)
        print(f"[{symbol}] Operación {direction} abierta. SL={sl_pips:.1f} pips | Lot={lot}")
    else:
        send_telegram_msg(f"❌ Error al abrir en {symbol}: {result.comment}")

# ==========================================
# 🔄 BUCLE PRINCIPAL
# ==========================================
if mt5.initialize(path=MT5_PATH):
    acc_info = mt5.account_info()
    login_msg = (f"✅ <b>Bot Online v2</b>\n"
                 f"Cuenta: {acc_info.login}\n"
                 f"Balance: ${acc_info.balance:.2f}\n"
                 f"Sesión activa: {SESSION_START_UTC}:00 – {SESSION_END_UTC}:00 UTC\n"
                 f"Spread máx: {MAX_SPREAD_PIPS} pips | SL: ATR×{ATR_MULTIPLIER}")
    send_telegram_msg(login_msg)
    print("Conexión exitosa a MT5. Iniciando escaneo...")

    try:
        while True:
            if check_security():
                print(f"\n--- Escaneo: {datetime.now().strftime('%H:%M:%S')} ---")

                # ✅ Filtro de sesión de mercado
                if not is_session_active():
                    print("⏸  Fuera de sesión (Londres/NY). Esperando...")
                    time.sleep(60)
                    continue

                # 1. RASTREADOR DE CIERRES (Para avisar por Telegram)
                from_date    = datetime.now() - timedelta(minutes=15)
                history_deals = mt5.history_deals_get(from_date, datetime.now())

                if history_deals:
                    for deal in history_deals:
                        if deal.magic == MAGIC_NUMBER and deal.entry == mt5.DEAL_ENTRY_OUT:
                            if deal.ticket not in notified_deals:
                                resultado   = "✅ TAKE PROFIT" if deal.profit > 0 else "❌ STOP LOSS"
                                msg_cierre  = (f"🔔 <b>OPERACIÓN CERRADA</b>\n"
                                               f"Par: {deal.symbol}\n"
                                               f"Resultado: {resultado}\n"
                                               f"Profit: ${deal.profit:.2f}")
                                send_telegram_msg(msg_cierre)
                                notified_deals.add(deal.ticket)

                # 2. GESTIÓN DE POSICIONES ABIERTAS (Breakeven / Trailing)
                manage_open_positions()

                # 3. ESCANEO DE SÍMBOLOS Y SEÑALES
                for sym in SYMBOLS:
                    pos = mt5.positions_get(symbol=sym)
                    active_bot_pos = [p for p in pos if p.magic == MAGIC_NUMBER] if pos else []

                    if not active_bot_pos:
                        # ✅ Filtro de spread antes de entrar
                        if not is_spread_ok(sym):
                            print(f"[{sym:^7}] Spread elevado – omitiendo.")
                            continue

                        signal, atr_val = get_signals(sym)
                        if signal:
                            open_position(sym, signal, atr_val)
                    else:
                        print(f"[{sym:^7}] Posición activa. Monitoreando...")

            time.sleep(30)

    except KeyboardInterrupt:
        print("\nBot detenido manualmente por el usuario.")
        mt5.shutdown()
else:
    print("Error al iniciar MT5. Revisa la ruta (MT5_PATH) y que el programa esté cerrado/ejecutado como administrador.")