from __future__ import annotations


def register_dashboard_routes(app, handlers: dict[str, callable]) -> None:
    """Logged-in dashboard pages, exports, and bookmark actions (HTML + JSON status)."""
    app.add_url_rule("/app/library", endpoint="app_library", view_func=handlers["app_library"], methods=["GET"])
    app.add_url_rule("/app/search", endpoint="app_search", view_func=handlers["app_search"], methods=["GET"])
    app.add_url_rule(
        "/app/series/<int:series_id>",
        endpoint="app_series_detail",
        view_func=handlers["app_series_detail"],
        methods=["GET"],
    )
    app.add_url_rule("/app/requests", endpoint="app_requests", view_func=handlers["app_requests"], methods=["GET"])
    app.add_url_rule("/app/settings", endpoint="app_settings", view_func=handlers["app_settings"], methods=["GET"])
    app.add_url_rule("/next", endpoint="next_up", view_func=handlers["next_up"], methods=["GET"])
    app.add_url_rule("/export", endpoint="export_data", view_func=handlers["export_data"], methods=["GET"])
    app.add_url_rule("/import", endpoint="import_data", view_func=handlers["import_data"], methods=["POST"])
    app.add_url_rule("/add", endpoint="add_bookmark", view_func=handlers["add_bookmark"], methods=["POST"])
    app.add_url_rule(
        "/check/<int:bookmark_id>",
        endpoint="check_bookmark",
        view_func=handlers["check_bookmark"],
        methods=["POST"],
    )
    app.add_url_rule("/check-story", endpoint="check_story_group", view_func=handlers["check_story_group"], methods=["POST"])
    app.add_url_rule("/check-all", endpoint="check_all_route", view_func=handlers["check_all_route"], methods=["POST"])
    app.add_url_rule(
        "/api/check-all/status",
        endpoint="check_all_status_api",
        view_func=handlers["check_all_status_api"],
        methods=["GET"],
    )
    app.add_url_rule(
        "/mark-seen/<int:bookmark_id>",
        endpoint="mark_seen",
        view_func=handlers["mark_seen"],
        methods=["POST"],
    )
    app.add_url_rule("/mark-all-seen", endpoint="mark_all_seen", view_func=handlers["mark_all_seen"], methods=["POST"])
    app.add_url_rule(
        "/bookmark/<int:bookmark_id>/read-through",
        endpoint="read_through",
        view_func=handlers["read_through"],
        methods=["POST"],
    )
    app.add_url_rule(
        "/bookmark/<int:bookmark_id>/edit",
        endpoint="edit_bookmark",
        view_func=handlers["edit_bookmark"],
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/delete/<int:bookmark_id>",
        endpoint="delete_bookmark",
        view_func=handlers["delete_bookmark"],
        methods=["POST"],
    )
    app.add_url_rule(
        "/library/<int:bookmark_id>/increment-current",
        endpoint="library_increment_current",
        view_func=handlers["library_increment_current"],
        methods=["POST"],
    )
    app.add_url_rule(
        "/library/<int:bookmark_id>/mark-caught-up",
        endpoint="library_mark_caught_up",
        view_func=handlers["library_mark_caught_up"],
        methods=["POST"],
    )
    app.add_url_rule(
        "/library/<int:bookmark_id>/update-chapters",
        endpoint="library_update_chapters",
        view_func=handlers["library_update_chapters"],
        methods=["POST"],
    )
