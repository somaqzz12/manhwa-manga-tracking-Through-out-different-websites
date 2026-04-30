from __future__ import annotations

from typing import Optional

from flask import redirect, request, session, url_for, Response

from db import get_conn, DEFAULT_USER_EMAIL


def get_default_user_id() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT id FROM users WHERE email = ?", (DEFAULT_USER_EMAIL,)).fetchone()
    return int(row["id"])


def get_actor_user_id() -> int:
    user_id = session.get("user_id")
    if user_id:
        return int(user_id)
    return get_default_user_id()


def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    with get_conn() as conn:
        return conn.execute("SELECT id, username, email, created_at FROM users WHERE id = ?", (user_id,)).fetchone()


def login_required() -> bool:
    return session.get("user_id") is not None


def safe_internal_redirect_path(candidate: str | None) -> str | None:
    if not candidate:
        return None
    s = candidate.strip()
    if not s.startswith("/") or s.startswith("//") or "\n" in s or "\r" in s or "\\" in s:
        return None
    return s


def login_redirect_preserve_destination() -> Response:
    return redirect(url_for("auth_page", mode="login", next=request.full_path))


def api_session_user_id() -> Optional[int]:
    uid = session.get("user_id")
    if uid is None:
        return None
    try:
        return int(uid)
    except (TypeError, ValueError):
        return None

