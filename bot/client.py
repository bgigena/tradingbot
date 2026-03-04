import os
from twisted.internet import reactor, task
from ctrader_open_api import Client, Protobuf, TcpProtocol, endpoints
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *

class CTraderBotClient:
    def __init__(self, auth_manager):
        self.auth = auth_manager
        
        # OpenApiPy base elements
        self.client = Client(endpoints.LIVE_HOST, endpoints.PORT, TcpProtocol)
        self.client.setConnectedCallback(self._on_connected)
        self.client.setDisconnectedCallback(self._on_disconnected)
        self.client.setMessageReceivedCallback(self._on_message_received)
        
        self.account_id = None
        
        # State
        self.connected = False
        self.authorized = False

    def start(self):
        self.client.startService()
        reactor.run()
        
    def _on_connected(self):
        print("Conectado a cTrader API (TCP TLS). Autorizando app...")
        self.connected = True
        
        # Autorizar App
        req = ProtoOAApplicationAuthReq()
        req.clientId = self.auth.client_id
        req.clientSecret = self.auth.client_secret
        self.client.send(req).addCallbacks(self._on_app_authorized, self._on_error)

    def _on_app_authorized(self, event):
        print("App Autorizada. Refrescando token y autorizando cuenta...")
        token = self.auth.get_token()
        
        # Con el access token podemos pedir la lista de cuentas
        req = ProtoOAGetAccountListByAccessTokenReq()
        req.accessToken = token
        self.client.send(req).addCallbacks(self._on_account_list, self._on_error)
        
    def _on_account_list(self, result):
        accounts = result.ctidTraderAccount
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
        self.client.send(req).addCallbacks(self._on_account_authorized, self._on_error)

    def _on_account_authorized(self, result):
        print(f"Cuenta {self.account_id} autorizada con éxito.")
        self.authorized = True
        
        # Iniciar el loop principal del bot
        self._start_bot_loop()

    def _start_bot_loop(self):
        from .telegram import send_msg
        send_msg(f"✅ <b>Bot Online</b> (cTrader Docker)\nConectado a cuenta: <code>{self.account_id}</code>")
        
        print("Iniciando escaneo de símbolos...")
        # Llama a _tick cada 30 segundos
        self.loop = task.LoopingCall(self._tick)
        self.loop.start(30.0)

    def _tick(self):
        """Este es el reemplazo del while True: time.sleep(30)"""
        print("\n--- Ejecutando ciclo del bot ---")
        # Aquí va la lógica de escaneo y gestión de posiciones
        # (se llamará a bot.strategy y bot.risk)
        pass

    def _on_message_received(self, msg):
        # Escuchar eventos asíncronos (cierres de ordenes, etc)
        # ProtoOAExecutionEvent etc.
        if msg.payloadType == ProtoOAExecutionEvent().payloadType:
            event = Protobuf.extract(msg)
            # Procesar el evento de ejecución
            # Para rastrear TakeProfit o StopLoss
            pass

    def _on_disconnected(self, reason):
        print(f"Desconectado de cTrader API: {reason}")
        self.connected = False
        self.authorized = False
        
    def _on_error(self, failure):
        print(f"❌ Error en request cTrader: {failure}")

