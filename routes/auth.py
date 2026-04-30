from __future__ import annotations


def register_auth_routes(app, handlers: dict[str, callable], limiter, auth_rate_limit_per_ip: str, auth_rate_limit_per_user: str, auth_username_key_func) -> None:
    auth_handler = limiter.limit(
        auth_rate_limit_per_ip,
        methods=["POST"],
        key_func=lambda: handlers["get_remote_address"](),
    )(
        limiter.limit(
            auth_rate_limit_per_user,
            methods=["POST"],
            key_func=auth_username_key_func,
        )(handlers["auth_page"])
    )
    app.add_url_rule("/auth", endpoint="auth_page", view_func=auth_handler, methods=["GET", "POST"])
    app.add_url_rule("/login", endpoint="login_alias", view_func=handlers["login_alias"], methods=["GET"])
    app.add_url_rule("/register", endpoint="register_alias", view_func=handlers["register_alias"], methods=["GET"])
    app.add_url_rule("/logout", endpoint="logout", view_func=handlers["logout"], methods=["POST"])

