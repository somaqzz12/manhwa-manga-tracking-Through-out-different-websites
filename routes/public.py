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
    app.add_url_rule("/roadmap", endpoint="roadmap_page", view_func=handlers["roadmap_page"], methods=["GET"])
    app.add_url_rule("/sources", endpoint="sources_page", view_func=handlers["sources_page"], methods=["GET"])
    app.add_url_rule("/privacy", endpoint="privacy_page", view_func=handlers["privacy_page"], methods=["GET"])
    app.add_url_rule("/check", endpoint="check_info_page", view_func=handlers["check_info_page"], methods=["GET"])
    app.add_url_rule("/changelog", endpoint="changelog_page", view_func=handlers["changelog_page"], methods=["GET"])
    app.add_url_rule("/demo", endpoint="demo_dashboard", view_func=handlers["demo_dashboard"], methods=["GET"])

