FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema necesarias para compilar paquetes (como Twisted/cryptography)
RUN apt-get update && apt-get install -y \
  gcc \
  python3-dev \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Limpiamos MT5 de los requirements ya que no corre en Linux/Docker python:slim
RUN sed -i '/MetaTrader5/d' requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Usar el main de cTrader
CMD ["python", "main_ctrader.py"]
