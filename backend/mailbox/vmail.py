"""VMail (vmail.dev / mail.22y.uk) 临时邮箱渠道适配器。

API 文档: https://mail.22y.uk/api-docs
Base: {api_base}/api/v1
鉴权: X-API-Key 或 Authorization: Bearer
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from backend.mailbox.utilities import extract_verification_code, generate_username, strip_html

API_BASE_DEFAULT = "https://mail.22y.uk"
HttpGet = Callable[..., Any]
HttpPost = Callable[..., Any]


def normalize_base(base_url: str = "") -> str:
    base = str(base_url or API_BASE_DEFAULT).strip().rstrip("/")
    if not base:
        base = API_BASE_DEFAULT
    if base.endswith("/api/v1"):
        return base
    if base.endswith("/api"):
        return f"{base}/v1"
    return f"{base}/api/v1"


def build_headers(api_key: str = "", content_type: bool = False) -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if content_type:
        headers["Content-Type"] = "application/json"
    key = (api_key or "").strip()
    if key:
        headers["X-API-Key"] = key
    return headers


def _response_data(resp, action: str) -> Any:
    try:
        payload = resp.json()
    except Exception as exc:
        preview = str(getattr(resp, "text", "") or "")[:300]
        raise Exception(f"VMail {action}返回非 JSON: {preview}") from exc
    if resp.status_code >= 400:
        if isinstance(payload, dict):
            err = payload.get("error") or payload
            if isinstance(err, dict):
                detail = err.get("message") or err.get("code") or str(err)
            else:
                detail = str(err)
        else:
            detail = str(payload)
        raise Exception(f"VMail {action}失败 HTTP {resp.status_code}: {detail}")
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def create_mailbox(
    http_post: HttpPost,
    api_base: str = "",
    api_key: str = "",
    *,
    domain: str = "",
    local_part: str = "",
    expires_in: int = 0,
) -> Tuple[str, str]:
    key = (api_key or "").strip()
    if not key:
        raise Exception("请配置 vmail_api_key（在 mail.22y.uk /api-docs 页面创建 API Key）")
    base = normalize_base(api_base)
    payload: Dict[str, Any] = {}
    name = (local_part or "").strip() or generate_username(10)
    payload["localPart"] = name
    cleaned_domain = (domain or "").strip()
    if cleaned_domain:
        payload["domain"] = cleaned_domain
    if expires_in and int(expires_in) > 0:
        payload["expiresIn"] = int(expires_in)
    resp = http_post(
        f"{base}/mailboxes",
        json=payload,
        headers=build_headers(key, content_type=True),
    )
    data = _response_data(resp, "创建邮箱")
    if not isinstance(data, dict):
        raise Exception(f"VMail 创建邮箱响应异常: {data}")
    address = str(data.get("address") or "").strip()
    mailbox_id = str(data.get("id") or "").strip()
    if not address:
        raise Exception(f"VMail 创建邮箱未返回 address: {data}")
    if not mailbox_id:
        raise Exception(f"VMail 创建邮箱未返回 id: {data}")
    print(f"[*] 已创建 VMail 邮箱: {address} (id={mailbox_id})")
    return address, mailbox_id


def list_messages(
    http_get: HttpGet,
    api_base: str,
    api_key: str,
    mailbox_id: str,
    *,
    page: int = 1,
    limit: int = 20,
) -> List[dict]:
    key = (api_key or "").strip()
    mid = str(mailbox_id or "").strip()
    if not key or not mid:
        return []
    base = normalize_base(api_base)
    resp = http_get(
        f"{base}/mailboxes/{mid}/messages",
        params={"page": page, "limit": limit, "sort": "desc"},
        headers=build_headers(key),
    )
    data = _response_data(resp, "查询邮件列表")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for field in ("messages", "items", "list", "rows"):
            items = data.get(field)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def get_message(
    http_get: HttpGet,
    api_base: str,
    api_key: str,
    mailbox_id: str,
    message_id: str,
) -> dict:
    key = (api_key or "").strip()
    mid = str(mailbox_id or "").strip()
    msg_id = str(message_id or "").strip()
    if not key or not mid or not msg_id:
        raise Exception("VMail 获取邮件详情参数不完整")
    base = normalize_base(api_base)
    resp = http_get(
        f"{base}/mailboxes/{mid}/messages/{msg_id}",
        headers=build_headers(key),
    )
    data = _response_data(resp, "获取邮件详情")
    return data if isinstance(data, dict) else {}


def wait_for_code(
    http_get: HttpGet,
    api_base: str,
    api_key: str,
    mailbox_id: str,
    email: str = "",
    *,
    timeout: int = 180,
    poll_interval: int = 3,
    raise_if_cancelled: Callable[[Optional[Callable[[], bool]]], None],
    sleep_with_cancel: Callable[[float, Optional[Callable[[], bool]]], None],
    log_callback: Optional[Callable[[str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
    resend_callback: Optional[Callable[[], None]] = None,
) -> str:
    if not (api_key or "").strip():
        raise Exception("VMail API Key 未配置")
    if not str(mailbox_id or "").strip():
        raise Exception("VMail mailbox id 为空")
    deadline = time.time() + timeout
    seen_ids = set()
    next_resend_at = time.time() + 35
    while time.time() < deadline:
        raise_if_cancelled(cancel_callback)
        if resend_callback and time.time() >= next_resend_at:
            try:
                resend_callback()
                if log_callback:
                    log_callback("[*] 已触发重新发送验证码")
            except Exception as exc:
                if log_callback:
                    log_callback(f"[Debug] 触发重发验证码失败: {exc}")
            next_resend_at = time.time() + 35
        try:
            messages = list_messages(http_get, api_base, api_key, mailbox_id)
        except Exception as exc:
            if log_callback:
                log_callback(f"[Debug] VMail 拉取邮件列表失败: {exc}")
            sleep_with_cancel(poll_interval, cancel_callback)
            continue
        if log_callback:
            log_callback(f"[Debug] VMail 本轮邮件数量: {len(messages)}")
        for msg in messages:
            msg_id = str(msg.get("id") or msg.get("messageId") or "").strip()
            if not msg_id or msg_id in seen_ids:
                continue
            try:
                detail = get_message(http_get, api_base, api_key, mailbox_id, msg_id)
            except Exception as exc:
                if log_callback:
                    log_callback(f"[Debug] VMail 获取邮件详情失败: {exc}")
                continue
            seen_ids.add(msg_id)
            parts: List[str] = []
            subject = str(detail.get("subject") or msg.get("subject") or "")
            preview = str(msg.get("preview") or "")
            if preview:
                parts.append(preview)
            text_body = detail.get("text") or detail.get("textContent") or ""
            if isinstance(text_body, str) and text_body.strip():
                parts.append(text_body)
            html_value = detail.get("html") or detail.get("htmlContent")
            if isinstance(html_value, str) and html_value.strip():
                parts.append(strip_html(html_value))
            elif isinstance(html_value, list):
                parts.extend(strip_html(item) for item in html_value if isinstance(item, str))
            combined = "\n".join(parts)
            if log_callback:
                log_callback(f"[Debug] VMail 收到邮件: {subject or msg_id}")
            code = extract_verification_code(f"{subject}\n{combined}", subject)
            if code:
                if log_callback:
                    log_callback(f"[*] VMail 从邮件中提取到验证码: {code}")
                return code
        sleep_with_cancel(poll_interval, cancel_callback)
    target = email or mailbox_id
    raise Exception(f"VMail 在 {timeout}s 内未收到验证码邮件（{target}）")
