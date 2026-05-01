from __future__ import annotations


def register_library_routes(app, handlers: dict[str, callable], csrf) -> None:
    """Register library/app routes with stable endpoint names."""
    app.add_url_rule("/app", endpoint="index", view_func=handlers["index"], methods=["GET"])
    app.add_url_rule("/dashboard", endpoint="index_dashboard_alias", view_func=handlers["index"], methods=["GET"])
    app.add_url_rule("/app/add", endpoint="app_add_url", view_func=handlers["app_add_url"], methods=["GET"])
    app.add_url_rule("/add-url", endpoint="app_add_url_alias", view_func=handlers["app_add_url"], methods=["GET"])
    app.add_url_rule(
        "/api/library/add-from-preview",
        endpoint="api_library_add_from_preview",
        view_func=csrf.exempt(handlers["api_library_add_from_preview"]),
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/series/ensure",
        endpoint="ensure_series",
        view_func=csrf.exempt(handlers["ensure_series"]),
        methods=["POST"],
    )
    app.add_url_rule(
        "/api/progress",
        endpoint="save_progress",
        view_func=csrf.exempt(handlers["save_progress"]),
        methods=["POST"],
    )

