from __future__ import annotations


def register_account_routes(app, handlers: dict[str, callable], limiter, get_remote_address) -> None:
    """Account settings, RSS, public list slug, and source request pages."""
    app.add_url_rule(
        "/onboarding/dismiss",
        endpoint="onboarding_dismiss",
        view_func=handlers["onboarding_dismiss"],
        methods=["POST"],
    )
    app.add_url_rule(
        "/account/delete",
        endpoint="delete_account",
        view_func=handlers["delete_account"],
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/account/settings",
        endpoint="account_settings",
        view_func=handlers["account_settings"],
        methods=["GET", "POST"],
    )
    app.add_url_rule(
        "/list/<slug>",
        endpoint="public_library",
        view_func=handlers["public_library"],
        methods=["GET"],
    )

    source_requests_handler = limiter.limit("12/hour", methods=["POST"], key_func=get_remote_address)(
        handlers["source_requests_page"]
    )
    app.add_url_rule(
        "/source-requests",
        endpoint="source_requests_page",
        view_func=source_requests_handler,
        methods=["GET", "POST"],
    )
    vote_handler = limiter.limit("40/hour", methods=["POST"], key_func=get_remote_address)(
        handlers["source_requests_vote"]
    )
    app.add_url_rule(
        "/source-requests/<int:req_id>/vote",
        endpoint="source_requests_vote",
        view_func=vote_handler,
        methods=["POST"],
    )
    app.add_url_rule(
        "/feeds/rss/<token>",
        endpoint="user_rss_feed",
        view_func=handlers["user_rss_feed"],
        methods=["GET"],
    )
