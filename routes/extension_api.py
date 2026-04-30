from __future__ import annotations


def register_extension_api_routes(app, handlers: dict[str, callable], csrf) -> None:
    app.add_url_rule(
        "/api/unread-count",
        endpoint="api_unread_count",
        view_func=csrf.exempt(handlers["api_unread_count"]),
        methods=["GET"],
    )
    app.add_url_rule(
        "/api/reader-overlay",
        endpoint="api_reader_overlay",
        view_func=csrf.exempt(handlers["api_reader_overlay"]),
        methods=["GET"],
    )

