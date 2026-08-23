# WebToApp Forge — Render/Docker image
FROM python:3.12-slim-bookworm

# Java (javac), zip/unzip, curl, openssl — sve što forge treba
RUN apt-get update && apt-get install -y --no-install-recommends \
      openjdk-17-jdk-headless \
      zip unzip curl openssl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Pillow za obradu ikonica (opciono, ali lepše)
RUN pip install --no-cache-dir pillow

# Preuzmi minimalni Android SDK (platforma + build-tools) tokom builda
RUN bash setup_sdk.sh

# Render postavlja PORT env promenljivu (default 10000)
ENV PORT=10000
EXPOSE 10000

CMD ["python3", "server.py"]
