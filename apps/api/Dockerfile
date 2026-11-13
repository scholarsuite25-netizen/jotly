FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VOICE_CLONING_ENABLED=false

WORKDIR /app

RUN groupadd --gid 10001 nexus && \
    useradd --uid 10001 --gid nexus --shell /bin/bash --create-home nexus

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R nexus:nexus /app

USER nexus

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
