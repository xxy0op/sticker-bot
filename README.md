# TG 表情下载机器人（单个表情，直接回传）

给机器人发**一个**表情，它只下载这一个（不下载整套表情包），
直接把文件发回聊天，不用选格式，自己存到手机，再导入微信表情。

## 功能

- 发一个表情 → 直接回传文件；也可以直接发 GIF 文件 / 动图
- 回传格式固定（微信可用）：
  - 静态表情：**PNG**
  - 动态表情（tgs）：**GIF（微信动图）**
  - 视频表情（webm/mp4）：**GIF（微信动图）**
  - GIF 文件：**GIF 原文件**
- 转换方式：
  - webp → PNG：Pillow
  - tgs → GIF：python-lottie 逐帧渲染（需系统装 libcairo2）
  - webm/mp4 → GIF：ffmpeg（15fps、宽 512、256 色）
- 文件发回聊天，附带大小；临时文件发送完即删

## 部署

### Docker 部署（推荐：直接拉镜像）

镜像由 GitHub Actions 自动构建并发布到 GitHub Container Registry
（`ghcr.io/xxy0op/sticker-bot:latest`），更新代码后会自动重新构建。
不用克隆仓库，一条命令就能跑：

```bash
docker run -d --name sticker-bot --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="你的token" \
  ghcr.io/xxy0op/sticker-bot:latest
```

或者用 compose 单文件部署（不用克隆仓库，不用 .env）：

把下面这个模板存成 `docker-compose.yml`，把 `TELEGRAM_BOT_TOKEN` 改成你的 token：

```yaml
services:
  sticker-bot:
    image: ghcr.io/xxy0op/sticker-bot:latest
    container_name: sticker-bot
    restart: unless-stopped
    environment:
      TELEGRAM_BOT_TOKEN: "你的token"
```

然后启动：

```bash
docker compose up -d
```

注意：这个文件里写了你的 token，只放服务器上，不要分享、不要提交到仓库。
（这个模板也在仓库里，叫 `docker-compose.standalone.yml`，也可以直接拉取：
`curl -O https://raw.githubusercontent.com/xxy0op/sticker-bot/main/docker-compose.standalone.yml`）

也可以克隆仓库后用自带的 compose 文件（配合 .env）：

```bash
git clone https://github.com/xxy0op/sticker-bot.git
cd sticker-bot
cp .env.example .env   # 把 TELEGRAM_BOT_TOKEN 改成你的 token
docker compose up -d
```

更新、看日志、停掉：

```bash
docker compose pull && docker compose up -d
docker logs -f sticker-bot
docker compose down
```

不想拉镜像、想自己构建也行：

```bash
docker build -t sticker-bot .
docker run -d --name sticker-bot --restart unless-stopped \
  -e TELEGRAM_BOT_TOKEN="你的token" sticker-bot
```

### 直接部署（不用 Docker）

1. 在 Telegram 里找 **@BotFather**，`/newbot` 创建机器人，拿到 token。
2. 系统依赖（Debian/Ubuntu）：

```bash
apt install -y ffmpeg libcairo2
```

3. 把本目录传到服务器，安装 Python 依赖：

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

4. 启动（前台测试）：

```bash
TELEGRAM_BOT_TOKEN="你的token" .venv/bin/python bot.py
```

也可以用 `run.sh` 启动，它会先停掉已在跑的旧实例再启动，避免多个实例同时跑互相抢消息：

```bash
TELEGRAM_BOT_TOKEN="你的token" bash run.sh
```

5. 常驻运行（systemd，见 `stickerbot.service`，把里面的 token 和路径改成你的）：

```bash
cp stickerbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now stickerbot
systemctl status stickerbot
```

## 使用

1. 在 Telegram 里打开机器人，`/start`
2. 发任意一个表情（或 GIF 文件 / 动图）
3. 文件直接发回聊天里，不用选
4. 手机上把文件保存下来：长按文件 → 另存为 → 存到“文件”或相册；GIF 在 Telegram 里会显示成动图，点“添加到 GIF 动图库”只是存进 Telegram 自己的收藏，到不了手机，一定要用“另存为”
5. 微信里：表情 → `+` → 从相册选 PNG 或 GIF 添加即可

## 限制说明

- 只下载你发的那一个表情，不下载整套表情包。
- tgs 转 GIF 是用 lottie 重新渲染，绝大多数贴纸效果和 Telegram 官方一致，
  极少数带特殊效果（表达式、复杂遮罩等）的可能渲染有差异或转失败，
  失败时会在聊天里回一条失败提示。
- GIF 是 256 色，转出来的动图体积和色彩会比原表情略差；微信单个自定义表情
  也有大小限制，太大的 GIF 可能加不进去。
- 下载文件先存服务器临时目录（默认 `/tmp/sticker-bot`，可用环境变量 `STICKER_BOT_DATA` 改），发送完即删。

## 能不能放 Cloudflare

不能直接放 Cloudflare Workers，两个原因：

1. Workers 是请求驱动的（收到请求才运行），跑不了长轮询；要上 Workers
   得改成 webhook 方式（Telegram 主动把消息推过来）。
2. 更关键的是，Workers 里跑不了 ffmpeg、lottie/cairo，tgs 和 webm 转 GIF
   做不了，而转 GIF 正是这个机器人的核心功能。

结论：放自己的服务器（VPS）上最合适，上面部署步骤就是按服务器写的。
如果硬要上 Cloudflare，只能拿它当前端入口（webhook），转换还得另找地方跑，
不划算。
