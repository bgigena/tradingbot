import MetaTrader5 as mt5

print("--- Iniciando Prueba de Conexión ---")

if not mt5.initialize():
    print("ERROR: No se pudo conectar a MT5. ¿Está abierto el programa?")
    mt5.shutdown()
else:
    print("CONECTADO CORRECTAMENTE")
    account = mt5.account_info()
    if account:
        print(f"Cuenta: {account.login}")
        print(f"Balance actual: {account.balance}")
        print(f"Trading Algorítmico permitido en MT5: {account.trade_expert}")
    else:
        print("No se pudo obtener info de la cuenta.")
    
mt5.shutdown()