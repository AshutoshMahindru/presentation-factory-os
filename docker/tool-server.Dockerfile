FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8003

CMD ["uvicorn", "tool_server.app:app", "--host", "0.0.0.0", "--port", "8003"]
