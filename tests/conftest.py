import base64

import pytest
from fastapi.testclient import TestClient

from app.auth import hash_password
from app.config import Config
from app.main import create_app
from app.service import Service

FAST = 2 ** 10


def basic(user, pw):
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()}


@pytest.fixture
def cfg(tmp_path):
    return Config(db=str(tmp_path / "t.db"), backup_dir=str(tmp_path / "backups"),
                  admin_user="admin", admin_hash=hash_password("adminpw", n=FAST),
                  dashboard_user="user", dashboard_hash=hash_password("userpw", n=FAST))


@pytest.fixture
def svc(cfg):
    return Service(cfg)


@pytest.fixture
def app(cfg):
    return create_app(cfg)


@pytest.fixture
def client(app):
    return TestClient(app)


ADMIN = basic("admin", "adminpw")
DASH = basic("user", "userpw")
WRITE = {**ADMIN, "X-Schnapsen": "1", "Content-Type": "application/json"}
