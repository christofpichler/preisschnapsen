"""HTTP Basic Auth with scrypt password hashes (standard library only)."""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import os
import threading
import time
from typing import Dict, Optional, Tuple

from .config import Config

SCRYPT_N = 2 ** 14
SCRYPT_R = 8
SCRYPT_P = 1
CACHE_SECONDS = 300


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def hash_password(password: str, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> str:
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=32, maxmem=128 * 1024 * 1024)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, want = stored.split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n), int(r), int(p)
        if n > 2 ** 20 or n < 2:
            return False
        dk = hashlib.scrypt(password.encode("utf-8"), salt=_unb64(salt), n=n, r=r, p=p,
                            dklen=len(_unb64(want)), maxmem=256 * 1024 * 1024)
        return hmac.compare_digest(dk, _unb64(want))
    except (ValueError, binascii.Error):
        return False


class Authenticator:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self._cache: Dict[str, Tuple[float, str]] = {}
        self._lock = threading.Lock()
        self._dummy = hash_password("dummy", n=_first_n(cfg))

    def check(self, header: Optional[str]) -> Optional[str]:
        """Return 'admin', 'user' or None."""
        if not header or not header.lower().startswith("basic "):
            return None
        key = hashlib.sha256(header.encode("utf-8", "replace")).hexdigest()
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                return hit[1]
        try:
            raw = base64.b64decode(header[6:].strip(), validate=False).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError):
            return None
        user, sep, pw = raw.partition(":")
        if not sep:
            return None
        role = self._verify(user, pw)
        if role:
            with self._lock:
                if len(self._cache) > 200:
                    self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
                self._cache[key] = (now + CACHE_SECONDS, role)
        return role

    def _verify(self, user: str, pw: str) -> Optional[str]:
        cfg = self.cfg
        ub = user.encode("utf-8")
        cands = []
        if cfg.admin_hash and hmac.compare_digest(ub, cfg.admin_user.encode("utf-8")):
            cands.append(("admin", cfg.admin_hash))
        if cfg.dashboard_hash and hmac.compare_digest(ub, cfg.dashboard_user.encode("utf-8")):
            cands.append(("user", cfg.dashboard_hash))
        if not cands:
            verify_password(pw, self._dummy)  # keep timing similar
            return None
        for role, h in cands:
            if verify_password(pw, h):
                return role
        return None


def _first_n(cfg: Config) -> int:
    for h in (cfg.admin_hash, cfg.dashboard_hash):
        try:
            return int(h.split("$")[1])
        except (IndexError, ValueError):
            continue
    return SCRYPT_N
