#!/usr/bin/env python3
"""Telegram 表情下载机器人(单个表情, 直接回传).

用法:
    发任意一个表情给机器人(静态 webp / 动态 tgs / 视频 webm),
    或发一个 GIF 文件 / 动图,
    机器人直接把文件发回聊天, 不用选格式:
      静态 webp  -> PNG(微信可用)
      动态 tgs   -> GIF(微信动图)
      视频 webm/mp4 -> GIF(微信动图)
      GIF 文件   -> GIF 原文件

运行:
    export TELEGRAM_BOT_TOKEN="123456:ABC..."
    python3 bot.py

依赖: python-telegram-bot>=21, Pillow, lottie, cairosvg
系统依赖: ffmpeg(视频转 GIF), libcairo2(lottie 渲染, 多数系统自带)
"""
import asyncio
import contextlib
import io
import logging
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image
from telegram import InputFile, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
BASE_DIR = Path(os.environ.get("STICKER_BOT_DATA", "/tmp/sticker-bot"))

# 只允许这些 Telegram 用户 ID 使用机器人(逗号分隔), 为空表示不限制。
# 查自己的 ID: 给 @userinfobot 发任意消息, 或看机器人日志里 "sticker from chat" 后面的数字
# (私聊时 chat id 就是你的用户 ID)。
ALLOWED_USER_IDS = {
    int(x) for x in os.environ.get("ALLOWED_USER_IDS", "").split(",") if x.strip()
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("sticker-bot")

GIF_FPS = 15
GIF_WIDTH = 512


# ---------- 工具函数 ----------

def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


def convert_webp_to_png(path: Path) -> Path:
    """webp -> PNG(保留透明通道), 删原文件, 返回新路径."""
    out = path.with_suffix(".png")
    with Image.open(path) as im:
        im.convert("RGBA").save(out, format="PNG")
    path.unlink()
    return out


def convert_tgs_to_gif(path: Path) -> Path:
    """动态贴纸 tgs -> GIF(lottie 逐帧渲染), 删原文件, 返回新路径."""
    from lottie.exporters.gif import export_gif
    from lottie.parsers.tgs import parse_tgs

    out = path.with_suffix(".gif")
    animation = parse_tgs(str(path))
    # export_gif 会往 stdout/stderr 打逐帧进度, 屏蔽掉保持日志干净
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        export_gif(animation, str(out))
    path.unlink()
    return out


def convert_video_to_gif(path: Path, fps: int = GIF_FPS, width: int = GIF_WIDTH) -> Path:
    """视频 webm/mp4 -> GIF(ffmpeg, 15fps/宽512/256色), 删原文件, 返回新路径."""
    out = path.with_suffix(".gif")
    cmd = [
        "ffmpeg", "-y", "-i", str(path),
        "-vf",
        f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tail = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else "unknown error"
        raise RuntimeError(f"ffmpeg 转 GIF 失败: {tail}")
    path.unlink()
    return out


# ---------- 处理流程 ----------

def is_allowed(update: Update) -> bool:
    """白名单检查: ALLOWED_USER_IDS 为空表示不限制, 否则只放行名单里的用户。"""
    if not ALLOWED_USER_IDS:
        return True
    user = update.effective_user
    return user is not None and user.id in ALLOWED_USER_IDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        user = update.effective_user
        logger.info("denied user %s", user.id if user else None)
        await update.message.reply_text("这个机器人是私用的，不对外开放。")
        return
    await update.message.reply_text(
        "发我一个表情, 我直接把文件发回来。\n\n"
        "静态表情 → PNG(微信可用)\n"
        "动态表情 → GIF(微信动图)\n"
        "视频表情 → GIF(微信动图)\n"
        "GIF 文件 → 原样发回"
    )


async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    if msg is None:
        return
    if not is_allowed(update):
        user = update.effective_user
        logger.info("denied user %s", user.id if user else None)
        await msg.reply_text("这个机器人是私用的，不对外开放。")
        return
    item = None
    if msg.sticker:
        st = msg.sticker
        if st.is_video:
            item = ("video", ".webm")
        elif st.is_animated:
            item = ("animated", ".tgs")
        else:
            item = ("static", ".webp")
        file_id = st.file_id
    elif msg.document and msg.document.mime_type == "image/gif":
        item = ("gif", ".gif")
        file_id = msg.document.file_id
    elif msg.animation:
        item = ("video", ".mp4")
        file_id = msg.animation.file_id
    if item is None:
        return

    kind, ext = item
    logger.info("sticker from chat %s kind=%s", msg.chat_id, kind)
    await context.bot.send_chat_action(chat_id=msg.chat_id, action="upload_document")
    workdir = BASE_DIR / os.urandom(8).hex()
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        f = await context.bot.get_file(file_id)
        src = workdir / f"sticker{ext}"
        await f.download_to_drive(src)

        # 转换是同步的 CPU 密集操作, 直接调会堵住事件循环(这期间收不到新消息),
        # 放线程里跑, 事件循环继续收发消息; 配合 concurrent_updates 实现多张并行转
        if kind == "static":
            out = await asyncio.to_thread(convert_webp_to_png, src)
        elif kind == "animated":
            out = await asyncio.to_thread(convert_tgs_to_gif, src)
        elif kind == "video":
            out = await asyncio.to_thread(convert_video_to_gif, src)
        else:  # gif 原文件
            out = src

        # 注意: InputFile 不接受 Path, load_file 会把 Path 原样当内容返回,
        # httpx 发送时报 'PosixPath' object has no attribute 'read',
        # 必须传 bytes 或打开的文件句柄(旧版直接传 Path 给 reply_document 能跑,
        # 是因为 parse_file_input 内部自己 open 了文件)
        doc = InputFile(out.read_bytes(), filename=f"sticker{out.suffix}")
        if out.suffix == ".gif":
            # Telegram 看到 image/gif 会把它当动图表情, 客户端保存时只能存进
            # Telegram 的 GIF 收藏或存成视频, 到不了手机文件; 声明成普通文件,
            # 客户端才会提供"存储到文件", 存到手机上再导入微信
            doc.mimetype = "application/octet-stream"
        await msg.reply_document(
            document=doc,
            caption=f"sticker{out.suffix} · {human_size(out.stat().st_size)}",
        )
    except Exception as e:
        logger.exception("download failed: %s", e)
        await msg.reply_text(f"下载/转换失败: {e}")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def main():
    if not TOKEN:
        raise SystemExit("请先设置环境变量 TELEGRAM_BOT_TOKEN")
    if shutil.which("ffmpeg") is None:
        logger.warning("未找到 ffmpeg, 视频表情转 GIF 将失败, 请安装 ffmpeg")
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    # 这台 VM 的出口代理偶尔很慢, 默认 5 秒超时不够, 启动时一次超时就直接退出,
    # 所以把超时放宽到 30 秒并允许启动重试 5 次
    app = (
        Application.builder()
        .token(TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(10)
        # 默认一次只处理一条消息, 发多张表情要排队等前一张转完;
        # 允许最多 4 条并行处理(配合 to_thread), 服务器 4 核刚好够用
        .concurrent_updates(4)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.ALL, on_message))
    logger.info("sticker bot started")
    app.run_polling(bootstrap_retries=5)


if __name__ == "__main__":
    main()
