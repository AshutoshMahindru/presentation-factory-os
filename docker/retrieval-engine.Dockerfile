FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

EXPOSE 8002

CMD ["uvicorn", "retrieval_engine.app:app", "--host", "0.0.0.0", "--port", "8002"]
