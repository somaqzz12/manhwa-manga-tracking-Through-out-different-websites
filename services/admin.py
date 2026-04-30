from __future__ import annotations


def admin_users_overview(conn) -> tuple[dict, list[dict], list[dict], list[dict]]:
    totals = conn.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM users) AS total_users,
            (SELECT COUNT(*) FROM bookmarks) AS total_bookmarks,
            (SELECT COUNT(*) FROM reading_progress) AS total_progress
        """
    ).fetchone()
    users = conn.execute(
        """
        SELECT
            u.id,
            u.username,
            u.email,
            u.created_at,
            (SELECT COUNT(*) FROM bookmarks b WHERE b.user_id = u.id) AS bookmark_count,
            (SELECT COUNT(*) FROM reading_progress rp WHERE rp.user_id = u.id) AS progress_count
        FROM users u
        ORDER BY u.created_at DESC, u.id DESC
        """
    ).fetchall()
    latest_users = conn.execute(
        """
        SELECT id, username, email, created_at
        FROM users
        ORDER BY created_at DESC, id DESC
        LIMIT 10
        """
    ).fetchall()
    latest_bookmarks = conn.execute(
        """
        SELECT b.id, b.title, b.url, b.created_at, b.user_id, u.username
        FROM bookmarks b
        LEFT JOIN users u ON u.id = b.user_id
        ORDER BY b.created_at DESC, b.id DESC
        LIMIT 10
        """
    ).fetchall()
    return totals, users, latest_users, latest_bookmarks


def admin_user_detail_rows(conn, user_id: int) -> tuple[dict | None, list[dict], list[dict]]:
    user = conn.execute(
        "SELECT id, username, email, created_at FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if not user:
        return None, [], []
    bookmarks = conn.execute(
        """
        SELECT id, title, url, latest_seen, latest_seen_num, new_update, created_at
        FROM bookmarks
        WHERE user_id = ?
        ORDER BY id DESC
        """,
        (user_id,),
    ).fetchall()
    progress = conn.execute(
        """
        SELECT
            rp.id,
            rp.bookmark_id,
            rp.chapter_num,
            rp.chapter_label,
            rp.source_url,
            rp.seen_at,
            b.title AS bookmark_title
        FROM reading_progress rp
        LEFT JOIN bookmarks b ON b.id = rp.bookmark_id
        WHERE rp.user_id = ?
        ORDER BY rp.seen_at DESC, rp.id DESC
        LIMIT 300
        """,
        (user_id,),
    ).fetchall()
    return user, bookmarks, progress


def admin_source_registry_rows(source_registry_module) -> list[dict]:
    rows = source_registry_module.sources_with_health()
    return sorted(rows, key=lambda r: ((r.get("registry_origin") or "zzz"), r.get("display_name") or r.get("id") or ""))

