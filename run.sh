#!/bin/bash
# 启动机器人: 先停掉已在跑的旧实例(只留一个), 再启动新实例。
# 注意: 机器人进程的命令行是 `.venv/bin/python bot.py`,
# pkill 的模式必须写成 "python bot[.]py" 才能匹配;
# 之前用的 "sticker-bot/bot[.]py" 匹配不到, 导致旧实例一直没停掉,
# 多个实例同时轮询, 互相报 409 Conflict。
# 用法: TELEGRAM_BOT_TOKEN=xxx bash run.sh
set -e
cd "$(dirname "$0")"
pkill -f "python bot[.]py" 2>/dev/null || true
sleep 2
echo "old instances remaining: $(ps aux | grep -c '[b]ot.py')"
exec env -u NO_PROXY -u no_proxy .venv/bin/python bot.py
