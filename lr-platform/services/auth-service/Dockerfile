FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

COPY backend /app/backend
COPY shared /app/shared
COPY services/auth-service /app/services/auth-service

RUN pip install --no-cache-dir -r /app/backend/requirements.txt

WORKDIR /app/services/auth-service

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
