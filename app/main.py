"""FastAPI app: routes, auth, CSRF checks, idempotency, SSE."""
from __future__ import annotations

import asyncio
import json
import os
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional
from urllib.parse import urlparse

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import exports
from .auth import Authenticator
from .config import Config
from .service import ApiError, Service

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
IDEM_TTL = 600

NO_ACCESS_HTML = """<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Kein Zugriff</title>
<link rel="icon" href="/static/img/favicon.svg"><link rel="stylesheet" href="/static/css/app.css"></head>
<body class="home"><main class="home-card"><h1>Kein Zugriff</h1><p>Dieser Bereich ist nur für Admin.</p>
<p><a class="btn" href="/dashboard/">Zum Dashboard</a></p></main></body></html>"""

def create_app(cfg: Optional[Config] = None) -> FastAPI:
    if cfg is None:
        from .config import load_config
        cfg = load_config()
    svc = Service(cfg)
    auth = Authenticator(cfg)
    app = FastAPI(title="Preisschnapsen", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.service = svc
    app.state.config = cfg
    idem: "OrderedDict[str, Any]" = OrderedDict()

    # ---------------------------------------------------------------- Auth
    REALM = "Preisschnapsen"

    def _role(request: Request) -> str:
        role = auth.check(request.headers.get("authorization"))
        if role is None:
            raise HTTPException(401, "Anmeldung erforderlich",
                                headers={"WWW-Authenticate": f'Basic realm="{REALM}", charset="UTF-8"'})
        return role

    def need_user(request: Request) -> str:
        return _role(request)

    def need_admin(request: Request) -> str:
        role = _role(request)
        if role != "admin":
            raise HTTPException(403, "Kein Zugriff – nur für Admin")
        return role

    def need_admin_write(request: Request, role: str = Depends(need_admin)) -> str:
        if request.headers.get("x-schnapsen") != "1":
            raise HTTPException(403, "Header X-Schnapsen fehlt.")
        if not request.headers.get("content-type", "").lower().startswith("application/json"):
            raise HTTPException(403, "Nur JSON-Requests erlaubt.")
        for h in ("origin", "referer"):
            v = request.headers.get(h)
            if v and v != "null":
                if urlparse(v).netloc != request.headers.get("host", ""):
                    raise HTTPException(403, "Origin passt nicht.")
        return role

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError) -> JSONResponse:
        return JSONResponse({"ok": False, "error": e.message, "code": e.code}, status_code=e.status)

    @app.exception_handler(HTTPException)
    async def _http_error(request: Request, e: HTTPException) -> JSONResponse:
        if e.status_code == 403 and "Kein Zugriff" in str(e.detail) and "text/html" in request.headers.get("accept", "") \
                and not request.url.path.startswith("/admin/api/"):
            return HTMLResponse(NO_ACCESS_HTML, status_code=403)
        return JSONResponse({"ok": False, "error": str(e.detail)}, status_code=e.status_code,
                            headers=getattr(e, "headers", None))

    @app.middleware("http")
    async def _headers(request: Request, call_next: Callable) -> Response:
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if not request.url.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # ---------------------------------------------------------------- idempotency
    def do(request: Request, fn: Callable[[], Optional[Dict[str, Any]]]) -> JSONResponse:
        rid = request.headers.get("x-request-id")
        with svc.lock:
            now = time.time()
            while idem and next(iter(idem.values()))[0] < now - IDEM_TTL:
                idem.popitem(last=False)
            if rid:
                hit = idem.get(rid)
                if hit and hit[1] == request.url.path:
                    return JSONResponse(hit[2], status_code=hit[3], headers={"X-Idempotent-Replay": "1"})
            extra = fn() or {}
            body = {"ok": True, **extra, "state": {**svc.admin_state(), "role": "admin"}}
            if rid:
                idem[rid] = (now, request.url.path, body, 200)
                while len(idem) > 3000:
                    idem.popitem(last=False)
            return JSONResponse(body)

    # ---------------------------------------------------------------- SSE
    async def sse(request: Request, once: bool) -> StreamingResponse:
        async def gen():
            last = None
            hb = time.time()
            yield "retry: 2000\n\n"
            while True:
                if svc.version != last:
                    last = svc.version
                    yield f"event: version\ndata: {json.dumps({'v': last})}\n\n"
                    hb = time.time()
                    if once:
                        return
                elif time.time() - hb > 10:
                    hb = time.time()
                    yield "event: hb\ndata: 1\n\n"
                await asyncio.sleep(0.25)
                if await request.is_disconnected():
                    return
        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    # ---------------------------------------------------------------- pages
    @app.get("/")
    def root(_: str = Depends(need_user)) -> RedirectResponse:
        return RedirectResponse("/dashboard/", status_code=307)

    @app.get("/dashboard")
    @app.get("/admin")
    def _redir(request: Request) -> RedirectResponse:
        return RedirectResponse(request.url.path + "/", status_code=307)

    @app.get("/dashboard/")
    def dash_page(_: str = Depends(need_user)) -> FileResponse:
        return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))

    @app.get("/dashboard/api/state")
    def dash_state(role: str = Depends(need_user)) -> JSONResponse:
        return JSONResponse({**svc.public_state(), "role": role})

    @app.get("/dashboard/api/events")
    async def dash_events(request: Request, once: int = 0, _: str = Depends(need_user)):
        return await sse(request, bool(once))

    @app.get("/admin/")
    def admin_page(_: str = Depends(need_admin)) -> FileResponse:
        return FileResponse(os.path.join(STATIC_DIR, "admin.html"))

    @app.get("/admin/api/state")
    def admin_state(_: str = Depends(need_admin)) -> JSONResponse:
        return JSONResponse({**svc.admin_state(), "role": "admin"})

    @app.get("/admin/api/events")
    async def admin_events(request: Request, once: int = 0, _: str = Depends(need_admin)):
        return await sse(request, bool(once))

    def _active_derived():
        with svc.lock:
            tid = svc.require_tid()
            raw = svc.load_raw(tid)
            from . import engine
            return raw["tournament"], engine.compute(raw), tid

    @app.get("/admin/druck")
    def admin_print(_: str = Depends(need_admin)) -> HTMLResponse:
        t, d, _tid = _active_derived()
        return HTMLResponse(exports.print_html(t, d))

    @app.get("/admin/api/export.csv")
    def admin_csv(_: str = Depends(need_admin)) -> Response:
        t, d, _tid = _active_derived()
        return Response(exports.csv_export(t, d), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="schnapsen-tabelle.csv"'})

    @app.get("/admin/api/backup.json")
    def admin_backup(_: str = Depends(need_admin)) -> Response:
        with svc.lock:
            snap = svc.export_snapshot(svc.require_tid())
        return Response(json.dumps(snap, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="schnapsen-backup.json"'})

    # ---------------------------------------------------------------- write endpoints
    W = Depends(need_admin_write)
    B = Body(default_factory=dict)

    @app.post("/admin/api/players")
    def r_player_add(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.add_player(p))

    @app.post("/admin/api/players/remove-all")
    def r_players_remove_all(request: Request, p: dict = B, _: str = W):
        if p.get("confirm") is not True:
            raise ApiError("Bestätigung fehlt.", 422)
        return do(request, lambda: {"removed": svc.remove_all_players()})

    @app.patch("/admin/api/players/{pid}")
    def r_player_upd(pid: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.update_player(pid, p))

    @app.delete("/admin/api/players/{pid}")
    def r_player_del(pid: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.delete_player(pid))

    @app.post("/admin/api/players/{pid}/withdraw")
    def r_withdraw(pid: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.withdraw_player(pid))

    @app.post("/admin/api/players/{pid}/nk")
    def r_nk(pid: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.set_nk(pid, str(p.get("decision", ""))))

    @app.post("/admin/api/rounds/draw")
    def r_draw(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.draw_digital())

    @app.post("/admin/api/rounds/draw-manual")
    def r_draw_manual(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.draw_manual(p.get("assignment") or {}))

    @app.post("/admin/api/rounds/discard")
    def r_discard(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.discard_draft())

    @app.post("/admin/api/rounds/publish")
    def r_publish(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.publish())

    @app.post("/admin/api/rounds/{number}/close")
    def r_close(number: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.close_round(number))

    @app.post("/admin/api/rounds/{number}/reopen")
    def r_reopen(number: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.reopen_round(number))

    @app.post("/admin/api/pairings/{pid}/result")
    def r_result(pid: int, request: Request, p: dict = B, _: str = W):
        w = p.get("winner_id")
        if w is not None and not isinstance(w, int):
            raise ApiError("winner_id ungültig.", 422)
        return do(request, lambda: svc.set_result(pid, w, bool(p.get("confirm"))))

    @app.post("/admin/api/placements")
    def r_place(request: Request, p: dict = B, _: str = W):
        order = p.get("order")
        if not isinstance(order, list) or not all(isinstance(i, int) for i in order) \
                or not isinstance(p.get("elim_round"), int):
            raise ApiError("Ungültige Platzierung.", 422)
        return do(request, lambda: svc.set_placement(p["elim_round"], order))

    @app.delete("/admin/api/placements/{elim}")
    def r_place_del(elim: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.clear_placement(elim))

    @app.post("/admin/api/tournaments")
    def r_t_create(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: {"id": svc.create_tournament(p)})

    @app.patch("/admin/api/tournament")
    def r_t_upd(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.update_tournament(p))

    @app.post("/admin/api/tournament/start")
    def r_t_start(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.start_tournament())

    @app.post("/admin/api/tournament/finish")
    def r_t_finish(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.finish_tournament())

    @app.post("/admin/api/tournament/reopen")
    def r_t_reopen(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.reopen_tournament())

    @app.post("/admin/api/tournament/reset")
    def r_t_reset(request: Request, p: dict = B, _: str = W):
        if p.get("confirm") is not True:
            raise ApiError("Bestätigung fehlt.", 422)
        return do(request, lambda: svc.reset_tournament())

    @app.post("/admin/api/tournaments/{tid}/activate")
    def r_t_activate(tid: int, request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.activate_tournament(tid))

    @app.delete("/admin/api/tournaments/{tid}")
    def r_t_delete(tid: int, request: Request, p: dict = B, _: str = W):
        if p.get("confirm") is not True:
            raise ApiError("Bestätigung fehlt.", 422)
        return do(request, lambda: svc.delete_tournament(tid))

    @app.patch("/admin/api/dashboard")
    def r_dashboard(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: svc.update_dashboard(p))

    @app.post("/admin/api/undo")
    def r_undo(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: {"undone": svc.undo()})

    @app.post("/admin/api/import")
    def r_import(request: Request, p: dict = B, _: str = W):
        return do(request, lambda: {"id": svc.import_snapshot(p)})

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
