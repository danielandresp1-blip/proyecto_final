# Se construye desde la raiz del proyecto (usa src/datos.py para conectarse a Snowflake)
FROM python:3.12-slim

WORKDIR /app
COPY tablero/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY tablero/app.py tablero/app.py

EXPOSE 8501
CMD ["streamlit", "run", "tablero/app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]
