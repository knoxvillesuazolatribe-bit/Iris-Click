"""Security audit: every admin API route refuses people who are not signed in as an admin."""

import re


PUBLIC = {"/api/auth/admin/login"}  # the admin sign-in itself


def admin_routes(app):
    """From the app's OpenAPI description (this FastAPI version nests included routers)."""
    for path, methods in app.openapi()["paths"].items():
        if "/admin" in path and path not in PUBLIC:
            for method in sorted(methods):
                yield method.upper(), re.sub(r"\{[^}]+\}", "1", path)


def call(api, method, path):
    return api.request(method, path, json={})


def test_there_are_admin_routes_to_check(api):
    assert len(list(admin_routes(api.app))) >= 40


def test_signed_out_people_get_no_admin_route(api):
    open_routes = [(m, p, r.status_code) for m, p in admin_routes(api.app)
                   if (r := call(api, m, p)).status_code not in (401, 403)]
    assert open_routes == []


def test_an_assistive_user_gets_no_admin_route(api, make_user):
    user_id = make_user("Ana Cruz")
    assert api.post("/api/assistive/select", json={"user_id": user_id}).status_code == 200
    open_routes = [(m, p, r.status_code) for m, p in admin_routes(api.app)
                   if (r := call(api, m, p)).status_code not in (401, 403)]
    assert open_routes == []
