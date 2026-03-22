FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# We assume shared is accessible when building from root context
# or handled via docker-compose volume mapping for development
ENV PYTHONPATH=/app

CMD ["python", "main.py"]
