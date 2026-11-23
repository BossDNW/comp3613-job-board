"""Shallow scenario smoke tests — intentionally weak."""

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.main import app
from app.seed import seed
from app.database import engine
from app.models.admin import Admin
from app.models.employer import Employer
from app.models.graduate import Graduate


def setup_module() -> None:
    seed(reset=True)


client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["scenario"] == "job-board"


def test_api_login_seed_admin():
    r = client.post(
        "/api/auth/login",
        json={"email": "admin@example.com", "password": "admin-dev"},
    )
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"


def test_seed_creates_child_class_records():
    with Session(engine) as session:
        assert session.exec(select(Admin)).first() is not None
        assert session.exec(select(Employer)).first() is not None
        assert session.exec(select(Graduate)).first() is not None


def test_jobs_endpoint_returns_list():
    r = client.get("/api/jobs")
    assert r.status_code == 200
    assert isinstance(r.json()["jobs"], list)
    assert len(r.json()["jobs"]) >= 1
