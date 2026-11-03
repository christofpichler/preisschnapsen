import os
import subprocess
import sys

from app import cli
from app.auth import Authenticator, hash_password, verify_password
from app.config import Config, check_config, load_config, parse_env_file, write_env_value
from tests.conftest import basic


def test_hash_format_and_verify():
    h = hash_password("geheim", n=2 ** 10)
    assert h.startswith("scrypt$1024$8$1$") and "geheim" not in h
    assert verify_password("geheim", h) and not verify_password("Geheim", h)
    assert not verify_password("x", "kaputt") and not verify_password("x", "scrypt$1$2$3$a$b")
    assert hash_password("geheim", n=2 ** 10) != h       # random salt


def test_auth_cache(cfg):
    a = Authenticator(cfg)
    hdr = basic("admin", "adminpw")["Authorization"]
    assert a.check(hdr) == "admin"
    assert len(a._cache) == 1 and a.check(hdr) == "admin"
    assert a.check(basic("user", "userpw")["Authorization"]) == "user"
    assert a.check(basic("user", "adminpw")["Authorization"]) is None
    assert a.check(None) is None


def test_config_env_file_and_environment(tmp_path):
    p = tmp_path / "c.env"
    p.write_text("# Kommentar\nSCHNAPSEN_PORT=9000\nSCHNAPSEN_ADMIN_USER='chef'\nSCHNAPSEN_DB=/x/y.db\n")
    c = load_config(str(p), env={"SCHNAPSEN_PORT": "9100"})
    assert c.port == 9100 and c.admin_user == "chef" and c.db == "/x/y.db" and c.backup_dir == "/x/backups"
    assert len(check_config(c)) == 2
    assert parse_env_file(str(tmp_path / "fehlt")) == {}


def test_passwd_cli_writes_hash(tmp_path):
    p = tmp_path / "s.env"
    p.write_text("SCHNAPSEN_PORT=8080\n")
    import io
    old = sys.stdin
    sys.stdin = io.StringIO("meinpasswort\n")
    try:
        assert cli.main(["--config", str(p), "passwd", "admin", "--stdin"]) == 0
    finally:
        sys.stdin = old
    c = load_config(str(p), env={})
    assert verify_password("meinpasswort", c.admin_hash) and c.port == 8080 and not c.dashboard_hash
    write_env_value(str(p), "SCHNAPSEN_ADMIN_USER", "x")
    assert load_config(str(p), env={}).admin_user == "x"


def test_server_refuses_to_start_without_hash(tmp_path):
    env = {**os.environ, "SCHNAPSEN_CONFIG": str(tmp_path / "leer.env"), "SCHNAPSEN_DB": str(tmp_path / "d.db")}
    for k in ("SCHNAPSEN_ADMIN_HASH", "SCHNAPSEN_DASHBOARD_HASH"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, "-m", "app"], env=env, capture_output=True, text=True, timeout=30,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 2 and "SCHNAPSEN_ADMIN_HASH" in r.stderr


def test_simulation_several_sizes():
    assert cli.main(["simulate", "--players", "2,3,5,19,24,40", "--seeds", "3"]) == 0


def test_demo_tournament(tmp_path):
    db = str(tmp_path / "demo.db")
    assert cli.main(["demo", "--db", db]) == 0
    from app.service import Service
    s = Service(Config(db=db))
    d = s.derive(s.require_tid())
    assert len(d["players"]) == 24 and d["current_round"] == 4 and d["phase"] == "running"
    assert d["round_progress"]["done"] < d["round_progress"]["total"]
    assert d["warnings"] == []


def test_passwd_alias_user(tmp_path):
    import io
    p = tmp_path / "s.env"
    old = sys.stdin
    sys.stdin = io.StringIO("meinpasswort\n")
    try:
        assert cli.main(["--config", str(p), "passwd", "user", "--stdin", "--user", "gast"]) == 0
    finally:
        sys.stdin = old
    c = load_config(str(p), env={})
    assert c.dashboard_user == "gast" and verify_password("meinpasswort", c.dashboard_hash)
