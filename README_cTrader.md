# Trading Bot - MetaTrader 5 + cTrader Open API Migration

## cTrader Version (Docker / Headless)
Instalación y ejecución del bot versión cTrader (no requiere MT5 abierto).

### 1. Setup inicial (Una sola vez)
Debes autorizar tu cuenta de cTrader con el bot para que este pueda operar:
1. Instala las dependencias: `pip install -r requirements.txt`
2. Ejecuta el script de autenticación interactivo: `python setup_auth.py`
3. Sigue las instrucciones en consola. Esto guardará el `CTRADER_REFRESH_TOKEN` en tu archivo `.env`.

### 2. Ejecutar con Docker
```bash
docker-compose up -d
```
El bot correrá en segundo plano y se auto-reiniciará si la PC se reinicia o el contenedor falla.
Para ver los logs en vivo:
```bash
docker-compose logs -f tradingbot
```

### 3. Ejecutar localmente (Sin Docker)
```bash
python main_ctrader.py
```
