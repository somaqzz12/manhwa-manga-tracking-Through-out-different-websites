from __future__ import annotations


def register_api_discovery_routes(app, handlers: dict[str, callable], csrf, limiter, rate_limit_key_func) -> None:
    """Register discovery API routes while preserving endpoint names."""
    resolve_handler = limiter.limit("20/minute", methods=["POST"], key_func=rate_limit_key_func)(
        csrf.exempt(handlers["api_resolve_url"])
    )
    search_live_handler = limiter.limit("12/minute", methods=["POST"], key_func=rate_limit_key_func)(
        csrf.exempt(handlers["api_discover_search_live"])
    )
    app.add_url_rule("/api/resolve-url", endpoint="api_resolve_url", view_func=resolve_handler, methods=["POST"])
    app.add_url_rule(
        "/api/discover/search-live",
        endpoint="api_discover_search_live",
        view_func=search_live_handler,
        methods=["POST"],
    )
    app.add_url_rule("/api/trending", endpoint="api_trending", view_func=handlers["api_trending"], methods=["GET"])

