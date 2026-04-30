from __future__ import annotations


def register_system_routes(app, handlers: dict[str, callable], csrf) -> None:
    """Health, public registry snapshot, and stub import endpoints."""
    app.add_url_rule(
        "/api/import/mal",
        endpoint="api_import_mal_stub",
        view_func=csrf.exempt(handlers["api_import_mal_stub"]),
        methods=["POST"],
    )
    app.add_url_rule("/healthz", endpoint="healthz", view_func=handlers["healthz"], methods=["GET"])
    app.add_url_rule(
        "/api/registry/public",
        endpoint="api_registry_public",
        view_func=handlers["api_registry_public"],
        methods=["GET"],
    )
