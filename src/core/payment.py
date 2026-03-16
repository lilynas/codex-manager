"""
支付核心逻辑 — 生成 Plus/Team 支付链接、无痕打开浏览器、检测订阅状态
"""

import logging
import subprocess
import sys
from typing import Optional

from curl_cffi import requests as cffi_requests

from ..database.models import Account

logger = logging.getLogger(__name__)

PAYMENT_CHECKOUT_URL = "https://chatgpt.com/backend-api/payments/checkout"
TEAM_CHECKOUT_BASE_URL = "https://chatgpt.com/checkout/openai_llc/"


def _build_proxies(proxy: Optional[str]) -> Optional[dict]:
    if proxy:
        return {"http": proxy, "https": proxy}
    return None


def generate_plus_link(account: Account, proxy: Optional[str] = None) -> str:
    """生成 Plus 支付链接"""
    if not account.access_token:
        raise ValueError("账号缺少 access_token")

    headers = {
        "Authorization": f"Bearer {account.access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "plan_type": "plus",
        "checkout_ui_mode": "hosted",
        "cancel_url": "https://chatgpt.com/",
        "success_url": "https://chatgpt.com/",
    }

    resp = cffi_requests.post(
        PAYMENT_CHECKOUT_URL,
        headers=headers,
        json=payload,
        proxies=_build_proxies(proxy),
        timeout=30,
        impersonate="chrome110",
    )
    resp.raise_for_status()
    data = resp.json()
    if "url" in data:
        return data["url"]
    raise ValueError(data.get("detail", "API 未返回支付链接"))


def generate_team_link(
    account: Account,
    workspace_name: str = "MyTeam",
    price_interval: str = "month",
    seat_quantity: int = 5,
    proxy: Optional[str] = None,
) -> str:
    """生成 Team 支付链接"""
    if not account.access_token:
        raise ValueError("账号缺少 access_token")

    headers = {
        "Authorization": f"Bearer {account.access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "plan_name": "chatgptteamplan",
        "team_plan_data": {
            "workspace_name": workspace_name,
            "price_interval": price_interval,
            "seat_quantity": seat_quantity,
        },
        "promo_campaign": {
            "promo_campaign_id": "team-1-month-free",
            "is_coupon_from_query_param": True,
        },
        "checkout_ui_mode": "custom",
    }

    resp = cffi_requests.post(
        PAYMENT_CHECKOUT_URL,
        headers=headers,
        json=payload,
        proxies=_build_proxies(proxy),
        timeout=30,
        impersonate="chrome110",
    )
    resp.raise_for_status()
    data = resp.json()
    if "checkout_session_id" in data:
        return TEAM_CHECKOUT_BASE_URL + data["checkout_session_id"]
    raise ValueError(data.get("detail", "API 未返回 checkout_session_id"))


def open_url_incognito(url: str) -> bool:
    """调用本机浏览器以无痕模式打开 URL"""
    platform = sys.platform
    try:
        if platform == "win32":
            # 依次尝试 Chrome、Edge
            for browser, flag in [("chrome", "--incognito"), ("msedge", "--inprivate")]:
                try:
                    subprocess.Popen(
                        f'start {browser} {flag} "{url}"',
                        shell=True,
                    )
                    return True
                except Exception:
                    continue
        elif platform == "darwin":
            subprocess.Popen(
                ["open", "-a", "Google Chrome", "--args", "--incognito", url]
            )
            return True
        else:
            for binary in ["google-chrome", "chromium-browser", "chromium"]:
                try:
                    subprocess.Popen([binary, "--incognito", url])
                    return True
                except FileNotFoundError:
                    continue
    except Exception as e:
        logger.warning(f"无痕打开浏览器失败: {e}")
    return False


def check_subscription_status(account: Account, proxy: Optional[str] = None) -> str:
    """
    检测账号当前订阅状态。

    Returns:
        'free' / 'plus' / 'team'
    """
    if not account.access_token:
        raise ValueError("账号缺少 access_token")

    headers = {
        "Authorization": f"Bearer {account.access_token}",
        "Content-Type": "application/json",
    }

    resp = cffi_requests.get(
        "https://chatgpt.com/backend-api/me",
        headers=headers,
        proxies=_build_proxies(proxy),
        timeout=20,
        impersonate="chrome110",
    )
    resp.raise_for_status()
    data = resp.json()

    # 解析订阅类型
    plan = data.get("plan_type") or ""
    if "team" in plan.lower():
        return "team"
    if "plus" in plan.lower():
        return "plus"

    # 尝试从 orgs 或 workspace 信息判断
    orgs = data.get("orgs", {}).get("data", [])
    for org in orgs:
        settings_ = org.get("settings", {})
        if settings_.get("workspace_plan_type") in ("team", "enterprise"):
            return "team"

    return "free"
