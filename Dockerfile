FROM python:3.12-slim

# selenium + chromium(headless)용
RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    ca-certificates fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# requirements.txt가 없으면 아래 방식으로라도 고정 권장
RUN pip install --no-cache-dir flask selenium webdriver-manager

# DB를 볼륨으로 빼기 위해 코드에서 경로를 env로 받는 걸 권장
ENV PYTHONUNBUFFERED=1