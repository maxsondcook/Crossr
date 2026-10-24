FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# Railway sets $PORT; "::" listens on IPv4 and IPv6 (Railway private networking).
CMD ["sh", "-c", "uvicorn crossr_api.app:app --host :: --port ${PORT:-8000}"]
