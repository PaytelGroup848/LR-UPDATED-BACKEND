FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV SERVICE_NAME=gateway
ENV PORT=8004
ENV FLASK_DEBUG=false
ENV SOCKETIO_ASYNC_MODE=gevent
ENV SOCKETIO_WORKER_CONNECTIONS=5000

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY shared /app/shared

EXPOSE 8004

CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:8004 --workers 1 --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --worker-connections ${SOCKETIO_WORKER_CONNECTIONS} --timeout 120 --keep-alive 5 backend.main:app"]
