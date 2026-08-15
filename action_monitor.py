#!/usr/bin/env python3
"""
币安合约仓位监控 - GitHub Actions 单次检查版
=============================================
每次运行只检查一次：
  1. 读取 state.json 中上次记录的持仓快照
  2. 查询当前持仓，与快照对比
  3. 有仓位消失 => 判定为平仓，查询已实现盈亏，推送微信通知
  4. 保存新快照到 state.json（由 workflow 提交回仓库）

所有密钥通过 GitHub Secrets 注入环境变量，代码中不含任何敏感信息。
"""

import hashlib
import hmac
import json
import logging
import os
import sys
import time
from datetime import datetime
from urllib.parse import urlencode

import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

API_KEY = os.environ.get("BINANCE_API_KEY", "")
API_SECRET = os.environ.get("BINANCE_API_SECRET", "")
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
BASE_URL = "https://fapi.binance.com"
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")


def signed_get(path, params=None):
    """发送签名 GET 请求到币安合约 API。GitHub 服务器在海外，无需代理。"""
    params = params or {}
    params["timestamp"] = int(time.time() * 1000)
    params["recvWindow"] = 10000
    query_string = urlencode(params)
    signature = hmac.new(
        API_SECRET.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    resp = requests.get(
        f"{BASE_URL}{path}?{query_string}&signature={signature}",
        headers={"X-MBX-APIKEY": API_KEY},
        timeout=20,
    )
    if resp.status_code == 401:
        raise ValueError("API Key/Secret 无效或无合约权限")
    if resp.status_code == 451:
        raise ValueError("IP 地区受限（不应发生在 GitHub 服务器上）")
    resp.raise_for_status()
    return resp.json()


def send_pushplus(title, content):
    """发送 PushPlus 微信通知。"""
    if not PUSHPLUS_TOKEN:
        logger.error("PUSHPLUS_TOKEN 未配置")
        return False
    try:
        resp = requests.post(
            "https://www.pushplus.plus/send",
            json={
                "token": PUSHPLUS_TOKEN,
                "title": title,
                "content": content,
                "template": "markdown",
            },
            timeout=20,
        )
        result = resp.json()
        if result.get("code") == 200:
            logger.info("PushPlus 通知已发送: %s", title)
            return True
        logger.error("PushPlus 发送失败: %s", result.get("msg", result))
        return False
    except Exception as e:
        logger.error("PushPlus 请求异常: %s", e)
        return False


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning("状态文件读取失败，将重建: %s", e)
    return {"positions": {}}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_recent_pnl(symbol):
    """查询某交易对最近 15 分钟成交的已实现盈亏和手续费。"""
    try:
        start = int(time.time() * 1000) - 15 * 60 * 1000
        trades = signed_get(
            "/fapi/v1/userTrades",
            {"symbol": symbol, "startTime": start, "limit": 50},
        )
        pnl = sum(float(t.get("realizedPnl", 0)) for t in trades)
        commission = sum(float(t.get("commission", 0)) for t in trades)
        return pnl, commission
    except Exception as e:
        logger.error("查询 %s 成交明细失败: %s", symbol, e)
        return None, None


def notify_position_close(symbol, old, pnl, commission):
    """发送平仓通知。"""
    old_amt = float(old.get("positionAmt", 0))
    side = "多头" if old_amt > 0 else "空头"
    entry = float(old.get("entryPrice", 0))
    qty = abs(old_amt)

    title = f"仓位平仓: {symbol} {side}"
    md = (
        f"**🏁 合约仓位已平仓**\n\n"
        f"**交易对**：{symbol}\n\n"
        f"**方向**：{side}\n\n"
        f"**入场价**：${entry:,.2f}\n\n"
        f"**持仓数量**：{qty}\n\n"
    )
    if pnl is not None:
        emoji = "💰" if pnl >= 0 else "📉"
        sign = "+" if pnl >= 0 else ""
        md += f"**{emoji} 已实现盈亏**：{sign}${pnl:,.2f} USDT\n\n"
        if commission is not None:
            md += f"**手续费**：-${abs(commission):,.4f} USDT\n\n"
            net = pnl - abs(commission)
            net_sign = "+" if net >= 0 else ""
            md += f"**净利润**：{net_sign}${net:,.2f} USDT\n\n"
    md += f"**平仓时间**：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return send_pushplus(title, md)


def main():
    if not API_KEY or not API_SECRET:
        logger.error("缺少 BINANCE_API_KEY / BINANCE_API_SECRET 环境变量")
        sys.exit(1)

    state = load_state()
    prev_positions = state.get("positions", {})
    logger.info("上次快照: %d 个持仓 %s", len(prev_positions), list(prev_positions.keys()) or "")

    # 查询当前持仓
    positions = signed_get("/fapi/v2/positionRisk")
    active = {p["symbol"]: p for p in positions if float(p.get("positionAmt", 0)) != 0}
    logger.info("当前持仓: %d 个 %s", len(active), list(active.keys()) or "")

    # 检测平仓：上次有、现在没有
    for symbol, old in prev_positions.items():
        if symbol in active:
            continue
        logger.info("检测到平仓: %s", symbol)
        pnl, commission = fetch_recent_pnl(symbol)
        notify_position_close(symbol, old, pnl, commission)

    # 检测新持仓（仅记日志）
    for symbol in active:
        if symbol not in prev_positions:
            p = active[symbol]
            amt = float(p.get("positionAmt", 0))
            side = "多头" if amt > 0 else "空头"
            logger.info(
                "检测到新持仓: %s %s 数量=%s 入场价=$%s",
                symbol, side, amt, p.get("entryPrice"),
            )

    # 保存新快照（只保留必要字段，避免快照膨胀）
    state["positions"] = {
        s: {
            "symbol": s,
            "positionAmt": p.get("positionAmt"),
            "entryPrice": p.get("entryPrice"),
            "leverage": p.get("leverage"),
        }
        for s, p in active.items()
    }
    state["last_check"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_state(state)
    logger.info("检查完成，快照已保存")


if __name__ == "__main__":
    main()
