FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY backend /app/backend
COPY shared /app/shared
COPY services/user-service /app/services/user-service

RUN pip install --no-cache-dir -r /app/backend/requirements.txt

WORKDIR /app/services/user-service

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
