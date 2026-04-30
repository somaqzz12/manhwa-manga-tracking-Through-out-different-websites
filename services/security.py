from __future__ import annotations

from flask import request

from auth.helpers import get_current_user


def admin_secret_from_request() -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-Admin-Token") or "").strip()


def admin_api_authorized(*, app_debug: bool, admin_api_token: str, admin_username: str) -> bool:
    if app_debug:
        return True
    if admin_api_token:
        provided = admin_secret_from_request()
        if provided and provided == admin_api_token:
            return True
    if admin_username:
        current = get_current_user()
        if current:
            try:
                if str(current.get("username") or "").strip().lower() == admin_username.strip().lower():
                    return True
            except Exception:
                pass
    return False


def admin_view_authorized(*, app_debug: bool, admin_api_token: str, admin_username: str) -> bool:
    if app_debug:
        return True
    current = get_current_user()
    if current and admin_username:
        try:
            current_username = str(current["username"] or "").strip().lower()
        except Exception:
            current_username = ""
        if current_username == admin_username:
            return True
    if admin_api_token:
        provided = admin_secret_from_request()
        if provided and provided == admin_api_token:
            return True
    return False


def admin_link_kw() -> dict:
    return {}

