from __future__ import annotations


def register_public_routes(app, handlers: dict[str, callable]) -> None:
    """Register public website routes with stable endpoint names."""
    app.add_url_rule("/", endpoint="home", view_func=handlers["home"], methods=["GET"])
    app.add_url_rule("/search", endpoint="public_search", view_func=handlers["public_search"], methods=["GET"])
    app.add_url_rule("/discover", endpoint="discover_page", view_func=handlers["discover_page"], methods=["GET"])
    app.add_url_rule("/series/<slug>", endpoint="public_series", view_func=handlers["public_series"], methods=["GET"])
    app.add_url_rule("/about", endpoint="about_page", view_func=handlers["about_page"], methods=["GET"])
    app.add_url_rule("/help", endpoint="help_page", view_func=handlers["about_page"], methods=["GET"])
    app.add_url_rule("/terms", endpoint="terms_page", view_func=handlers["terms_page"], methods=["GET"])
    app.add_url_rule("/dmca", endpoint="dmca_page", view_func=handlers["dmca_page"], methods=["GET"])
    app.add_url_rule("/extension", endpoint="extension_page", view_func=handlers["extension_page"], methods=["GET"])

