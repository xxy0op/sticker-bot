# TG 表情下载机器人: 发一个表情, 直接把 PNG/GIF 文件发回聊天
FROM python:3.12-slim

# 系统依赖: ffmpeg(视频转 GIF)、libcairo2(lottie/tgs 渲染)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libcairo2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot.py .

# 临时文件目录(容器内 /tmp, 发送完即删, 不会堆积)
ENV STICKER_BOT_DATA=/tmp/sticker-bot

# token 不要写进镜像, 运行时用环境变量或 .env 传入:
#   docker run -e TELEGRAM_BOT_TOKEN="你的token" ...
#   或 docker compose up -d(配合 .env)
CMD ["python", "bot.py"]
