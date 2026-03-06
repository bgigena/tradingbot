import os
import time
import pandas as pd
from datetime import datetime, timezone
from twisted.internet import reactor, task, threads
from ctrader_open_api import Client, Protobuf, TcpProtocol
from ctrader_open_api.endpoints import EndPoints
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *

from src.utils.settings import trading_settings, session_settings
from .telegram import send_msg
from .strategy import get_signals

class CTraderBotClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager
        
        # OpenApiPy base elements
        print(f"📡 Inicializando cliente en {EndPoints.PROTOBUF_DEMO_HOST}:{EndPoints.PROTOBUF_PORT}...")
        self.client = Client(EndPoints.PROTOBUF_DEMO_HOST, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message_received)
        
        self.account_id = None
        self.balance = None
        self.symbol_data = {} # symbol_name -> {period: bars}
        # State
        self.connected = False
        self.authorized = False
        self.reconnect_delay = 5 # segundos
        self.loop = None
        self.heartbeat = None

    def start(self):
        print("🚀 Iniciando servicio de cliente y reactor...")
        self.client.startService()
        reactor.run()
        
    def _on_connected(self, client):
        print("Conectado a cTrader API (TCP TLS). Autorizando app...")
        self.connected = True
        
        # Autorizar App
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.auth.client_id
        req.clientSecret = self.auth.client_secret
        self.client.send(req, responseTimeoutInSeconds=20).addCallbacks(self._on_app_authorized, self._on_error)

    def _on_app_authorized(self, message):
        print("✅ App Autorizada.")
        token = self.auth.get_token()
        req = ProtoOAGetAccountListByAccessTokenReq()
        req.accessToken = token
        self.client.send(req, responseTimeoutInSeconds=20).addCallbacks(self._on_account_list, self._on_error)
        
    def _on_account_list(self, result):
        response = Protobuf.extract(result)
        print(f"DEBUG: Response type in _on_account_list: {type(response).__name__}")
        
        if not hasattr(response, "ctidTraderAccount"):
            print(f"❌ Error: El mensaje no contiene ctidTraderAccount. Respuesta: {response}")
            return
            
        accounts = response.ctidTraderAccount
        if not accounts:
            print("❌ No hay cuentas asociadas a este token.")
            return
            
        # Elegimos la primera cuenta
        self.account_id = accounts[0].ctidTraderAccountId
        print(f"Cuenta seleccionada: {self.account_id}")
        
        # Ahora autorizamos la cuenta
        req = ProtoOAAccountAuthReq()
        req.ctidTraderAccountId = self.account_id
        req.accessToken = self.auth.get_token()
        self.client.send(req, responseTimeoutInSeconds=20).addCallbacks(self._on_account_authorized, self._on_error)

    def _on_account_authorized(self, result):
        response = Protobuf.extract(result)
        print(f"✅ Cuenta {self.account_id} autorizada.")
        
        # Pedir detalles de la cuenta para obtener el balance inicial
        self._request_account_details()
        
        # Pedir lista de símbolos para mapear nombres a IDs
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self.account_id
        req.includeArchivedSymbols = False
        self.client.send(req, responseTimeoutInSeconds=20).addCallbacks(self._on_symbols_list, self._on_error)

    def _request_account_details(self):
        req = ProtoOATraderReq()
        req.ctidTraderAccountId = self.account_id
        self.client.send(req, responseTimeoutInSeconds=20).addCallbacks(self._on_account_details, self._on_error)

    def _on_account_details(self, result):
        response = Protobuf.extract(result)
        if hasattr(response, "trader") and hasattr(response.trader, "balance"):
            # Balance viene en centavos/unidades minimas segun la moneda, cTrader suele enviarlo escalado
            # Para la mayoría de las cuentas es balance / 100
            self.balance = response.trader.balance / 100
            print(f"💰 Balance actualizado: {self.balance}")
        self.authorized = True

    def _on_symbols_list(self, result):
        response = Protobuf.extract(result)
        print(f"Mapeando símbolos para cuenta {self.account_id}...")
        
        # Extraer símbolos que nos interesan (de .env o hardcoded)
        target_symbols = trading_settings.SYMBOLS
        self.symbol_map = {} # name -> id
        # Mapeo estático de dígitos para evitar más requests
        self.symbol_digits = {
            "EURUSD": 5, "GBPUSD": 5, "AUDUSD": 5, "NZDUSD": 5, "USDCAD": 5,
            "USDJPY": 3, "EURJPY": 3, "GBPJPY": 3, "XAUUSD": 2
        }
        
        for s in response.symbol:
            if s.symbolName in target_symbols:
                self.symbol_map[s.symbolName] = s.symbolId
                print(f"  - {s.symbolName} -> ID: {s.symbolId}")
        
        # Guardamos la lista inversa para saber el nombre por el ID
        self.id_map = {v: k for k, v in self.symbol_map.items()}
        
        # Iniciar el loop principal del bot
        self._start_bot_loop()

    def _start_bot_loop(self):
        balance_str = f"${self.balance:.2f}" if self.balance is not None else "Cargando..."
        send_msg(f"✅ <b>Bot Online</b> (cTrader Docker)\nCuenta: <code>{self.account_id}</code>\nBalance: <b>{balance_str}</b>")
        
        print("Iniciando escaneo de símbolos y heartbeats...")
        
        # 1. Heartbeats para mantener viva la conexión TCP (cada 25 seg)
        if self.heartbeat and self.heartbeat.running:
            self.heartbeat.stop()
        self.heartbeat = task.LoopingCall(self._send_heartbeat)
        self.heartbeat.start(25.0)

        # 2. Loop principal de escaneo
        if self.loop and self.loop.running:
            self.loop.stop()
        self.loop = task.LoopingCall(self._tick)
        self.loop.start(60.0) # Aumentado a 60s para dar tiempo al throttling

    def _send_heartbeat(self):
        if self.connected:
            req = ProtoHeartbeatEvent()
            # Silently handle heartbeat errors/timeouts to avoid "Unhandled error in Deferred"
            self.client.send(req, responseTimeoutInSeconds=10).addErrback(lambda _: None)

    def _tick(self):
        """Reemplazo del while True: time.sleep(30), ahora cada 60s con throttling."""
        if not self._is_market_open():
            print(f"⏸ Mercado cerrado ({datetime.now().strftime('%H:%M:%S')}). Esperando...")
            return

        print(f"\n--- Escaneo (Throttled): {datetime.now().strftime('%H:%M:%S')} ---")
        
        if not self.authorized:
            print("⏳ Esperando autorización completa...")
            return

        # Actualizar balance
        self._request_account_details()

        # Procesar símbolos uno por uno con delay para evitar rate limits
        symbols_to_process = list(self.symbol_map.items())
        self._process_next_symbol(symbols_to_process)

    def _process_next_symbol(self, queue):
        if not queue:
            return

        symbol_name, symbol_id = queue.pop(0)
        
        now_ms = int(time.time() * 1000)
        
        if symbol_name not in self.symbol_data:
             self.symbol_data[symbol_name] = {}
        
        print(f"  - [{symbol_name}] Solicitando H1...")
        # H1
        from_h1 = now_ms - (210 * 60 * 60 * 1000)
        self._request_trendbars(symbol_id, 9, from_h1, now_ms)
        
        # M15 (encadenar con un pequeño delay interno de 1s para ser aún más conservadores)
        print(f"  - [{symbol_name}] Agendando M15 en 1s...")
        from_m15 = now_ms - (130 * 15 * 60 * 1000)
        reactor.callLater(1.0, self._request_trendbars, symbol_id, 7, from_m15, now_ms)

        # Agendar el siguiente símbolo en 3 segundos
        if queue:
            print(f"  - Agendando próximo símbolo en 3s...")
            reactor.callLater(3.0, self._process_next_symbol, queue)

    def _is_market_open(self):
        """Verifica si el mercado Forex está abierto usando SessionSettings."""
        now = datetime.now(timezone.utc)
        weekday = now.weekday()  # 0=Mon, ..., 6=Sun
        hour = now.hour

        # Abierto desde Domingo (por defecto 21:00 UTC / 22:00 CET)
        if weekday == session_settings.MARKET_OPEN_WEEKDAY:
            return hour >= session_settings.MARKET_OPEN_HOUR
        
        # Abierto Lunes, Martes, Miércoles, Jueves
        if 0 <= weekday <= 3:
            return True
        
        # Cerrado desde Viernes (por defecto 22:00 UTC / 23:00 CET)
        if weekday == session_settings.MARKET_CLOSE_WEEKDAY:
            return hour < session_settings.MARKET_CLOSE_HOUR
        
        # Sábado siempre cerrado
        return False
            
        return True

    def _request_trendbars(self, symbol_id, period, from_ts, to_ts):
        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.period = period
        req.fromTimestamp = from_ts
        req.toTimestamp = to_ts
        self.client.send(req, responseTimeoutInSeconds=20).addCallbacks(self._on_trendbars, self._on_error)

    def _on_trendbars(self, result):
        response = Protobuf.extract(result)
        
        if type(response).__name__ == "ProtoOAErrorRes":
            print(f"❌ Error de cTrader en Trendbars: {response.errorCode} - {response.description}")
            return

        symbol_id = getattr(response, "symbolId", None)
        if not symbol_id:
            print(f"❓ Respuesta inesperada (sin symbolId): {response}")
            return
            
        symbol_name = self.id_map.get(symbol_id, "Unknown")
        period_name = "H1" if response.period == 9 else "M15"
        
        if symbol_name != "Unknown":
            self.symbol_data[symbol_name][period_name] = response.trendbar
            
            # Si ya tenemos ambos timeframes para este símbolo, procesar estrategia
            if "H1" in self.symbol_data[symbol_name] and "M15" in self.symbol_data[symbol_name]:
                self._process_strategy(symbol_name)
                # Limpiamos para el próximo tick
                self.symbol_data[symbol_name] = {}

    def _process_strategy(self, symbol_name):
        bars_h1 = self.symbol_data[symbol_name]["H1"]
        bars_m15 = self.symbol_data[symbol_name]["M15"]
        
        df_h1 = self._bars_to_df(bars_h1, symbol_name)
        df_m15 = self._bars_to_df(bars_m15, symbol_name)
        
        if df_h1.empty or df_m15.empty:
            return

        print(f"[{symbol_name}] Procesando señales... (H1: {len(df_h1)}, M15: {len(df_m15)})")
        signal, atr = get_signals(symbol_name, df_h1, df_m15)
        
        if signal and atr:
            balance_str = f"${self.balance:.2f}" if self.balance is not None else "N/A"
            last_price = df_m15['close'].iloc[-1]
            print(f"🔥 SEÑAL DETECTADA en {symbol_name}: {signal} | ATR: {atr:.5f} | Price: {last_price:.5f} (Balance: {balance_str})")
            self._execute_trade(symbol_name, signal, atr, last_price)

    def _execute_trade(self, symbol_name, signal, atr, entry_price):
        symbol_id = self.symbol_map[symbol_name]
        lot_size = trading_settings.LOT_SIZE
        # En cTrader el volumen es en unidades base (1 lot = 100,000 para FX)
        volume = int(lot_size * 100000)
        
        # SL and TP calculation based on ATR (Risk Mgmt)
        # Ratio 1:2
        atr_multiplier = trading_settings.ATR_MULTIPLIER if hasattr(trading_settings, 'ATR_MULTIPLIER') and trading_settings.ATR_MULTIPLIER else 1.5
        reward_ratio = trading_settings.REWARD_RATIO if hasattr(trading_settings, 'REWARD_RATIO') and trading_settings.REWARD_RATIO else 2.0
        
        if signal == "BUY":
            sl_price = entry_price - (atr * atr_multiplier)
            tp_price = entry_price + (atr * atr_multiplier * reward_ratio)
            trade_side = ProtoOATradeSide.BUY
        else:
            sl_price = entry_price + (atr * atr_multiplier)
            tp_price = entry_price - (atr * atr_multiplier * reward_ratio)
            trade_side = ProtoOATradeSide.SELL
        
        req = ProtoOANewOrderReq()
        req.ctidTraderAccountId = self.account_id
        req.symbolId = symbol_id
        req.orderType = ProtoOAOrderType.MARKET
        req.tradeSide = trade_side
        req.volume = volume
        
        # Asignamos stopLoss y takeProfit absolutos
        req.stopLoss = sl_price
        req.takeProfit = tp_price
        
        print(f"🚀 Enviando orden {signal} para {symbol_name} ({volume} unidades) | SL: {sl_price:.5f} | TP: {tp_price:.5f}")
        self.client.send(req, responseTimeoutInSeconds=20).addCallbacks(
            lambda res: self._on_order_sent(symbol_name, signal, volume, sl_price, tp_price),
            self._on_error
        )

    def _on_order_sent(self, symbol_name, signal, volume, sl, tp):
        balance_str = f"${self.balance:.2f}" if self.balance is not None else "N/A"
        print(f"✅ Orden enviada con éxito para {symbol_name}")
        send_msg(f"🚀 <b>ORDEN EJECUTADA</b>\nPar: <code>{symbol_name}</code>\nAcción: <b>{signal}</b>\nVolumen: {volume}\nSL: <code>{sl:.5f}</code>\nTP: <code>{tp:.5f}</code>\nBalance: <b>{balance_str}</b>")

    def _bars_to_df(self, bars, symbol_name):
        data = []
        digits = self.symbol_digits.get(symbol_name, 5)
        factor = 10**digits
        
        for b in bars:
            data.append({
                "timestamp": b.utcTimestampInMinutes * 60,
                "low": b.low / factor,
                "high": (b.low + b.deltaHigh) / factor,
                "open": (b.low + b.deltaOpen) / factor,
                "close": (b.low + b.deltaClose) / factor,
                "volume": b.volume
            })
        df = pd.DataFrame(data)
        if not df.empty:
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
        return df

    def _on_message_received(self, client, msg):
        # Escuchar eventos asíncronos (cierres de ordenes, etc)
        # ProtoOAExecutionEvent etc.
        if msg.payloadType == ProtoOAExecutionEvent().payloadType:
            event = Protobuf.extract(msg)
            # Procesar el evento de ejecución
            # Para rastrear TakeProfit o StopLoss
            pass

    def _on_disconnected(self, client, reason):
        print(f"❌ Desconectado de cTrader API: {reason}")
        self.connected = False
        self.authorized = False
        
        # Detener loops
        if self.loop and self.loop.running:
            self.loop.stop()
        if self.heartbeat and self.heartbeat.running:
            self.heartbeat.stop()

        # Reintentar reconexión
        print(f"⏳ Reconectando en {self.reconnect_delay} segundos...")
        # Usamos reactor.callLater para no bloquear y permitir que Twisted maneje el delay
        reactor.callLater(self.reconnect_delay, self._reconnect)

    def _reconnect(self):
        print("🔄 Intentando reconexión. Ejecutando refresh_access_token en hilo secundario...")
        
        d = threads.deferToThread(self.auth.refresh_access_token)
        
        def on_success(token):
            print("🔄 Token refrescado. Iniciando servicio...")
            self.client.startService()
            
        def on_error(failure):
            print(f"⚠️ Error en intento de reconexión: {failure.getErrorMessage()}")
            reactor.callLater(self.reconnect_delay, self._reconnect)
            
        d.addCallbacks(on_success, on_error)

    def _on_error(self, failure):
        err_msg = failure.getErrorMessage()
        print(f"❌ Error en request cTrader: {err_msg}")
        
        # Si es un timeout, no desconectamos, solo lo dejamos pasar para el siguiente tick
        if failure.check(TimeoutError):
            print("⏳ La petición expiró. Posible saturación o lag en el servidor.")
            return

        # Si el error sugiere que el token expiró, forzamos desconexión para gatillar el flujo de re-auth
        err_str = str(failure).upper()
        if "CH_ACCESS_TOKEN_INVALID" in err_str or "ACCESS_DENIED" in err_str or "UNAUTHORIZED" in err_str:
            print("🔑 Token inválido detectado. Forzando reconexión...")
            self.client.stopService()

