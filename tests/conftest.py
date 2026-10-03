import os
import tempfile

_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def admin_client(client):
    r = client.post("/login", data={"username": "admin", "password": "admin123"}, follow_redirects=False)
    assert r.status_code == 303
    return client
