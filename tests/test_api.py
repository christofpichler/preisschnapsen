import json
import uuid

import pytest

from tests.conftest import ADMIN, DASH, WRITE, basic


def post(client, path, body=None, headers=None, method="post"):
    h = dict(WRITE)
    if headers:
        h.update(headers)
    return client.request(method.upper(), path, content=json.dumps(body or {}), headers=h)


def rid():
    return {"X-Request-Id": str(uuid.uuid4())}


READ_PATHS = ["/dashboard/", "/dashboard/api/state", "/dashboard/api/events?once=1"]
ADMIN_READ = ["/admin/", "/admin/api/state", "/admin/api/events?once=1", "/admin/druck",
              "/admin/api/export.csv", "/admin/api/backup.json"]


REALM = 'Basic realm="Preisschnapsen", charset="UTF-8"'


def test_root_redirects_to_dashboard_after_login(client):
    assert client.get("/").status_code == 401
    for h in (DASH, ADMIN):
        r = client.get("/", headers=h, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == "/dashboard/"
    assert client.get("/dashboard", follow_redirects=False).headers["location"] == "/dashboard/"
    assert client.get("/admin", follow_redirects=False).headers["location"] == "/admin/"


def test_static_needs_no_auth(client):
    assert client.get("/static/css/app.css").status_code == 200
    assert client.get("/static/img/suits.svg").status_code == 200
    assert client.get("/static/fonts/alegreya-sc-latin-400-normal.woff2").status_code == 200


@pytest.mark.parametrize("path", ["/"] + READ_PATHS + ADMIN_READ)
def test_no_login_401_same_realm_everywhere(client, path):
    r = client.get(path)
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == REALM


@pytest.mark.parametrize("path", READ_PATHS)
def test_dashboard_user_and_admin(client, path):
    assert client.get(path, headers=DASH).status_code == 200
    assert client.get(path, headers=ADMIN).status_code == 200


@pytest.mark.parametrize("path", ADMIN_READ)
def test_admin_area_user_403_admin_200(client, path):
    r = client.get(path, headers=DASH)
    assert r.status_code == 403 and "www-authenticate" not in r.headers
    assert "Kein Zugriff" in r.text
    assert client.get(path, headers=ADMIN).status_code == 200


def test_user_403_html_page(client):
    r = client.get("/admin/", headers={**DASH, "Accept": "text/html"})
    assert r.status_code == 403 and "<html" in r.text and "nur für Admin" in r.text


def test_role_in_state(client):
    assert client.get("/dashboard/api/state", headers=DASH).json()["role"] == "user"
    assert client.get("/dashboard/api/state", headers=ADMIN).json()["role"] == "admin"
    assert client.get("/admin/api/state", headers=ADMIN).json()["role"] == "admin"


@pytest.mark.parametrize("path", READ_PATHS)
def test_dashboard_area_same_realm(client, path):
    assert client.get(path, headers=basic("x", "y")).headers["www-authenticate"] == REALM


def test_wrong_credentials(client):
    for h in (basic("admin", "falsch"), basic("user", "adminpw"), basic("admin", "userpw"), basic("x", "y"),
              {"Authorization": "Basic !!!"}, {"Authorization": "Bearer abc"}):
        assert client.get("/admin/api/state", headers=h).status_code == 401
        assert client.get("/dashboard/api/state", headers=h).status_code == 401


def test_user_cannot_write(client):
    h = {**DASH, "X-Schnapsen": "1", "Content-Type": "application/json"}
    assert client.post("/admin/api/players", content='{"name":"X"}', headers=h).status_code == 403
    assert client.post("/admin/api/undo", content="{}", headers=h).status_code == 403
    assert client.post("/dashboard/api/state", content="{}", headers=h).status_code == 405
    assert client.get("/admin/api/state", headers=ADMIN).json()["derived"]["players"] == []


def test_csrf_header_and_content_type_required(client):
    body = '{"name":"X"}'
    r = client.post("/admin/api/players", content=body, headers={**ADMIN, "Content-Type": "application/json"})
    assert r.status_code == 403
    r = client.post("/admin/api/players", content=body, headers={**ADMIN, "X-Schnapsen": "1", "Content-Type": "text/plain"})
    assert r.status_code == 403
    r = client.post("/admin/api/players", content=body, headers={**ADMIN, "X-Schnapsen": "1"})
    assert r.status_code == 403
    r = client.post("/admin/api/players", content=body, headers={**WRITE, "Origin": "http://evil.example"})
    assert r.status_code == 403
    r = client.post("/admin/api/players", content=body, headers={**WRITE, "Origin": "http://testserver"})
    assert r.status_code == 200
    r = client.post("/admin/api/players", content=body, headers={**WRITE, "Referer": "http://evil.example/x"})
    assert r.status_code == 403


def test_idempotency_by_request_id(client):
    h = rid()
    r1 = post(client, "/admin/api/players", {"name": "Einmal"}, h)
    r2 = post(client, "/admin/api/players", {"name": "Einmal"}, h)
    assert r1.status_code == r2.status_code == 200 and r2.headers.get("x-idempotent-replay") == "1"
    assert r1.json() == r2.json()
    players = client.get("/admin/api/state", headers=ADMIN).json()["derived"]["players"]
    assert len(players) == 1
    post(client, "/admin/api/players", {"name": "Zweimal"}, rid())
    post(client, "/admin/api/players", {"name": "Zweimal"}, rid())       # different id -> new entry
    assert len(client.get("/admin/api/state", headers=ADMIN).json()["derived"]["players"]) == 3


def test_errors_as_json(client):
    r = post(client, "/admin/api/players", {"name": "  "})
    assert r.status_code == 422 and r.json()["ok"] is False and "Name" in r.json()["error"]
    r = post(client, "/admin/api/tournament/start")
    assert r.status_code == 409


def test_sse_sends_version(client):
    r = client.get("/dashboard/api/events?once=1", headers=DASH)
    assert r.status_code == 200 and "text/event-stream" in r.headers["content-type"]
    assert "event: version" in r.text and '"v"' in r.text


def test_dashboard_state_is_reduced(client):
    post(client, "/admin/api/players", {"name": "Geheim", "ng_paid": False})
    s = client.get("/dashboard/api/state", headers=DASH).json()
    txt = json.dumps(s)
    assert "audit" not in s and "note" not in txt and "ng_paid" not in txt and s["cash"] is None


def test_mini_tournament_via_api(client):
    A = lambda path, body=None, method="post": post(client, path, body, rid(), method)
    for n in ["Anna", "Bert", "Cilli", "Dori", "Emil"]:
        assert A("/admin/api/players", {"name": n}).status_code == 200
    r = A("/admin/api/tournament/start")
    assert r.status_code == 200 and r.json()["state"]["derived"]["phase"] == "ready"
    # after the start, late registration requires confirmation
    assert A("/admin/api/players", {"name": "Fritz"}).json()["code"] == "late_confirm"
    r = A("/admin/api/players", {"name": "Fritz", "confirm_late": True})
    assert r.status_code == 200
    d = r.json()["state"]["derived"]
    assert len(d["players"]) == 6
    guard = 0
    while not d["finished"] and guard < 30:
        guard += 1
        if d["nk_pending"]:
            for n in d["nk_pending"]:
                d = A(f"/admin/api/players/{n['id']}/nk", {"decision": "yes_paid" if guard % 2 else "no"}).json()["state"]["derived"]
            continue
        r = A("/admin/api/rounds/draw")
        assert r.status_code == 200, r.text
        d = r.json()["state"]["derived"]
        draft = d["draft"]
        n_active = len(d["draw_ids"])
        assert len([p for p in draft["pairings"] if p["bye"]]) == n_active % 2
        # the draft is invisible on the dashboard
        pub = client.get("/dashboard/api/state", headers=DASH).json()
        assert all(r_["number"] != draft["number"] for r_ in pub["rounds"])
        d = A("/admin/api/rounds/publish").json()["state"]["derived"]
        for pr in [p for p in d["rounds"][-1]["pairings"] if not p["bye"]]:
            d = A(f"/admin/api/pairings/{pr['id']}/result", {"winner_id": pr["a"]}).json()["state"]["derived"]
        r = A(f"/admin/api/rounds/{d['current_round']}/close")
        assert r.status_code == 200
        d = r.json()["state"]["derived"]
    assert d["finished"] and d["winner"] is not None
    assert d["warnings"] == []
    st = client.get("/admin/api/state", headers=ADMIN).json()
    assert st["tournament"]["status"] == "finished"
    # exports
    assert client.get("/admin/api/export.csv", headers=ADMIN).content.startswith(b"\xef\xbb\xbfNr.;Name;NG;NK;R1")
    html = client.get("/admin/druck", headers=ADMIN).text
    assert "A4 landscape" in html and "Anna" in html
    bk = client.get("/admin/api/backup.json", headers=ADMIN).json()
    assert bk["format"] == "schnapsen-backup" and len(bk["players"]) == 6
    # import creates a new tournament
    r = A("/admin/api/import", bk)
    assert r.status_code == 200 and len(r.json()["state"]["tournaments"]) == 2


def test_undo_via_api(client):
    post(client, "/admin/api/players", {"name": "A"}, rid())
    post(client, "/admin/api/players", {"name": "B"}, rid())
    st = client.get("/admin/api/state", headers=ADMIN).json()
    assert st["undo"]["available"] and len(st["derived"]["players"]) == 2
    r = post(client, "/admin/api/undo", {}, rid())
    assert r.status_code == 200 and len(r.json()["state"]["derived"]["players"]) == 1
    post(client, "/admin/api/undo", {}, rid())
    r = post(client, "/admin/api/undo", {}, rid())
    assert r.status_code == 409


def test_delete_and_reset_need_confirmation(client):
    r = post(client, "/admin/api/tournament/reset", {}, rid())
    assert r.status_code == 422
    r = post(client, "/admin/api/tournament/reset", {"confirm": True}, rid())
    assert r.status_code == 200
    r = post(client, "/admin/api/tournaments", {"name": "Neu"}, rid())
    tid = r.json()["id"]
    first = [t for t in r.json()["state"]["tournaments"] if t["id"] != tid][0]["id"]
    assert post(client, f"/admin/api/tournaments/{first}", {}, rid(), "delete").status_code == 422
    assert post(client, f"/admin/api/tournaments/{first}", {"confirm": True}, rid(), "delete").status_code == 200


def test_dashboard_settings_validation(client):
    r = post(client, "/admin/api/dashboard", {"rotate_seconds": 30, "pinned": "matrix", "views": ["tables", "matrix"]}, rid(), "patch")
    assert r.status_code == 200
    b = r.json()["state"]["tournament"]["dashboard"]
    assert b["rotate_seconds"] == 30 and b["pinned"] == "matrix" and b["views"] == ["tables", "matrix"]
    assert post(client, "/admin/api/dashboard", {"pinned": "evil"}, rid(), "patch").status_code == 422
    assert post(client, "/admin/api/dashboard", {"rotate_seconds": 1}, rid(), "patch").status_code == 422


def test_manual_draw_via_api(client):
    ids = []
    for n in "ABCDE":
        ids.append(post(client, "/admin/api/players", {"name": n}, rid()).json()["state"]["derived"]["players"][-1]["id"])
    post(client, "/admin/api/tournament/start", {}, rid())
    bad = post(client, "/admin/api/rounds/draw-manual", {"assignment": {str(i): 1 for i in ids}}, rid())
    assert bad.status_code == 422
    good = {str(ids[0]): 1, str(ids[1]): 1, str(ids[2]): 2, str(ids[3]): 2, str(ids[4]): "F"}
    r = post(client, "/admin/api/rounds/draw-manual", {"assignment": good}, rid())
    assert r.status_code == 200
    dr = r.json()["state"]["derived"]["draft"]
    assert dr["mode"] == "manual" and sorted(p["table"] or 0 for p in dr["pairings"]) == [0, 1, 2]


def test_remove_all_players(client):
    A = lambda path, body=None, method="post": post(client, path, body, rid(), method)
    for n in ["Anna", "Bert", "Cilli"]:
        assert A("/admin/api/players", {"name": n}).status_code == 200
    assert A("/admin/api/tournament/start").status_code == 200
    assert A("/admin/api/rounds/draw").status_code == 200
    assert A("/admin/api/rounds/publish").status_code == 200
    # confirmation is mandatory
    assert A("/admin/api/players/remove-all", {}).status_code == 422
    r = A("/admin/api/players/remove-all", {"confirm": True})
    assert r.status_code == 200 and r.json()["removed"] == 3
    st = r.json()["state"]
    assert st["derived"]["players"] == [] and st["derived"]["rounds"] == [] and st["derived"]["draft"] is None
    assert st["tournament"]["status"] == "signup"
    # numbering starts again at 1
    r = A("/admin/api/players", {"name": "Dora"})
    assert [p["number"] for p in r.json()["state"]["derived"]["players"]] == [1]
    # undo twice: first the new player, then the removal
    A("/admin/api/undo")
    r = A("/admin/api/undo")
    d = r.json()["state"]["derived"]
    assert len(d["players"]) == 3 and len(d["rounds"]) == 1
    # the user role cannot use it
    h = dict(DASH)
    h.update({"Content-Type": "application/json", "X-Schnapsen": "1"})
    assert client.post("/admin/api/players/remove-all", content=json.dumps({"confirm": True}), headers=h).status_code == 403


def test_pages_reference_versioned_assets(client):
    html = client.get("/dashboard/", headers=DASH).text
    assert '/static/css/dashboard.css?v=' in html and '/static/js/suits.js?v=' in html
    assert "/static/js/admin.js?v=" in client.get("/admin/", headers=ADMIN).text
    v = html.split('/static/css/app.css?v=')[1].split('"')[0]
    r = client.get("/static/css/app.css?v=" + v)
    assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
    assert client.get("/static/css/app.css").headers["cache-control"] == "no-cache"
    assert client.get("/dashboard/", headers=DASH).headers["cache-control"] == "no-store"


def test_dashboard_contains_card_pool(client):
    html = client.get("/dashboard/", headers=DASH).text
    raw = html.split('<script id="cards-data" type="application/json">')[1].split("</script>")[0]
    cards = json.loads(raw)
    assert isinstance(cards, list)
    assert all(c.startswith("/static/img/cards/") and "?v=" in c for c in cards)
    for c in cards:
        assert client.get(c).status_code == 200


def test_replay_animation(client):
    before = client.get("/dashboard/api/state", headers=DASH).json()["anim_event"]
    r = post(client, "/admin/api/dashboard/animate", {}, rid())
    assert r.status_code == 200 and r.json()["anim_event"] == before + 1
    st = client.get("/dashboard/api/state", headers=DASH).json()
    assert st["anim_event"] == before + 1
    h = dict(DASH)
    h.update({"Content-Type": "application/json", "X-Schnapsen": "1"})
    assert client.post("/admin/api/dashboard/animate", content="{}", headers=h).status_code == 403
