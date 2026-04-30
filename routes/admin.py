from __future__ import annotations


def register_admin_routes(app, handlers: dict[str, callable]) -> None:
    app.add_url_rule("/admin/users", endpoint="admin_users", view_func=handlers["admin_users"], methods=["GET"])
    app.add_url_rule(
        "/admin/users/<int:user_id>",
        endpoint="admin_user_detail",
        view_func=handlers["admin_user_detail"],
        methods=["GET"],
    )
    app.add_url_rule(
        "/admin/source-registry-status",
        endpoint="admin_source_registry_status",
        view_func=handlers["admin_source_registry_status"],
        methods=["GET"],
    )

