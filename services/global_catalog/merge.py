from __future__ import annotations

from typing import Any


def merge_series(conn: Any, keep_id: int, drop_id: int) -> None:
    """Merge drop_id into keep_id: reassign FKs, then delete dropped series row."""
    if keep_id == drop_id:
        return

    for row in conn.execute(
        "SELECT id, provider, external_id FROM series_external_id WHERE series_id = ?",
        (drop_id,),
    ).fetchall():
        exists = conn.execute(
            "SELECT id FROM series_external_id WHERE series_id = ? AND provider = ? AND external_id = ?",
            (keep_id, row["provider"], row["external_id"]),
        ).fetchone()
        if exists:
            conn.execute("DELETE FROM series_external_id WHERE id = ?", (row["id"],))
        else:
            conn.execute(
                "UPDATE series_external_id SET series_id = ? WHERE id = ?",
                (keep_id, row["id"]),
            )

    for row in conn.execute("SELECT id, alias_normalized FROM series_alias WHERE series_id = ?", (drop_id,)).fetchall():
        exists = conn.execute(
            "SELECT id FROM series_alias WHERE series_id = ? AND alias_normalized = ?",
            (keep_id, row["alias_normalized"]),
        ).fetchone()
        if exists:
            conn.execute("DELETE FROM series_alias WHERE id = ?", (row["id"],))
        else:
            conn.execute("UPDATE series_alias SET series_id = ? WHERE id = ?", (keep_id, row["id"]))

    for row in conn.execute(
        "SELECT id, normalized_source_url FROM series_source_link WHERE series_id = ?",
        (drop_id,),
    ).fetchall():
        exists = conn.execute(
            "SELECT id FROM series_source_link WHERE series_id = ? AND normalized_source_url = ?",
            (keep_id, row["normalized_source_url"]),
        ).fetchone()
        if exists:
            conn.execute("DELETE FROM series_source_link WHERE id = ?", (row["id"],))
        else:
            conn.execute(
                "UPDATE series_source_link SET series_id = ? WHERE id = ?",
                (keep_id, row["id"]),
            )

    for row in conn.execute("SELECT id FROM series_source WHERE series_id = ?", (drop_id,)).fetchall():
        norm_row = conn.execute(
            "SELECT normalized_source_url FROM series_source WHERE id = ?",
            (row["id"],),
        ).fetchone()
        if not norm_row:
            continue
        nu = norm_row["normalized_source_url"]
        exists = conn.execute(
            "SELECT id FROM series_source WHERE series_id = ? AND normalized_source_url = ?",
            (keep_id, nu),
        ).fetchone()
        if exists:
            conn.execute("DELETE FROM series_source WHERE id = ?", (row["id"],))
        else:
            conn.execute("UPDATE series_source SET series_id = ? WHERE id = ?", (keep_id, row["id"]))

    for row in conn.execute("SELECT id, user_id FROM user_library_item WHERE series_id = ?", (drop_id,)).fetchall():
        exists = conn.execute(
            "SELECT id FROM user_library_item WHERE series_id = ? AND user_id = ?",
            (keep_id, row["user_id"]),
        ).fetchone()
        if exists:
            conn.execute("DELETE FROM user_library_item WHERE id = ?", (row["id"],))
        else:
            conn.execute(
                "UPDATE user_library_item SET series_id = ? WHERE id = ?",
                (keep_id, row["id"]),
            )

    conn.execute("DELETE FROM series WHERE id = ?", (drop_id,))
