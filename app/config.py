"""Configuration: env file plus environment variables."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

DEFAULT_CONFIG_PATH = "/etc/schnapsen/schnapsen.env"


@dataclass
class Config:
    host: str = "0.0.0.0"
    port: int = 8080
    db: str = "/var/lib/schnapsen/schnapsen.db"
    backup_dir: str = ""
    admin_user: str = "admin"
    admin_hash: str = ""
    dashboard_user: str = "user"  # account of the "user" role (variable name kept for compatibility)
    dashboard_hash: str = ""

    def __post_init__(self) -> None:
        if not self.backup_dir:
            self.backup_dir = os.path.join(os.path.dirname(os.path.abspath(self.db)), "backups")


def config_path() -> str:
    return os.environ.get("SCHNAPSEN_CONFIG", DEFAULT_CONFIG_PATH)


def parse_env_file(path: str) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "'\"":
                    val = val[1:-1]
                values[key] = val
    except FileNotFoundError:
        pass
    return values


def load_config(path: Optional[str] = None, env: Optional[Dict[str, str]] = None) -> Config:
    env = os.environ if env is None else env
    path = path or env.get("SCHNAPSEN_CONFIG", DEFAULT_CONFIG_PATH)
    vals = parse_env_file(path)
    for k, v in env.items():
        if k.startswith("SCHNAPSEN_") and k != "SCHNAPSEN_CONFIG":
            vals[k] = v

    def g(key: str, default: str) -> str:
        v = vals.get("SCHNAPSEN_" + key)
        return default if v is None or v == "" else v

    return Config(
        host=g("HOST", "0.0.0.0"),
        port=int(g("PORT", "8080")),
        db=g("DB", "/var/lib/schnapsen/schnapsen.db"),
        backup_dir=g("BACKUP_DIR", ""),
        admin_user=g("ADMIN_USER", "admin"),
        admin_hash=g("ADMIN_HASH", ""),
        dashboard_user=g("DASHBOARD_USER", "user"),
        dashboard_hash=g("DASHBOARD_HASH", ""),
    )


def check_config(cfg: Config) -> List[str]:
    problems = []
    if not cfg.admin_hash:
        problems.append("SCHNAPSEN_ADMIN_HASH ist nicht gesetzt (Admin-Passwort fehlt).")
    if not cfg.dashboard_hash:
        problems.append("SCHNAPSEN_DASHBOARD_HASH ist nicht gesetzt (Dashboard-Passwort fehlt).")
    return problems


def write_env_value(path: str, key: str, value: str) -> None:
    """Set KEY=value in the env file (created if missing)."""
    lines: List[str] = []
    existed = os.path.exists(path)
    if existed:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s*=")
    out, done = [], False
    for ln in lines:
        if pat.match(ln):
            if not done:
                out.append(f"{key}={value}")
                done = True
        else:
            out.append(ln)
    if not done:
        out.append(f"{key}={value}")
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")
    if existed:
        try:
            st = os.stat(path)
            os.chmod(tmp, st.st_mode & 0o777)
            os.chown(tmp, st.st_uid, st.st_gid)
        except (PermissionError, OSError):
            pass
    else:
        os.chmod(tmp, 0o640)
    os.replace(tmp, path)
