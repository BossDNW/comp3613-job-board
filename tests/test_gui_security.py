from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.main import app
from app.models.admin import Admin
from app.models.employer import Employer
from app.models.graduate import Graduate
from app.models.listing import Listing
from app.models.notification import Notification
from app.models.subscription import Subscription
from app.seed import seed
from app.utilities.security import create_access_token

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_database(isolated_test_database):
    seed(reset=True)


@pytest.fixture
def ids():
    with Session(engine) as db:
        return {
            "admin": db.exec(select(Admin)).one().id,
            "graduate": db.exec(select(Graduate).where(Graduate.programme == "DCIT")).one().id,
            "other": db.exec(select(Graduate).where(Graduate.programme == "OTHER")).one().id,
            "employer": db.exec(select(Employer).where(Employer.username == "employer")).one().id,
            "employer2": db.exec(select(Employer).where(Employer.username == "employer2")).one().id,
        }


def auth(user_id):
    return {"Cookie": f"access_token={create_access_token({'sub': str(user_id)})}"}


def listing_payload(**changes):
    payload = {
        "title": "Test Graduate Engineer",
        "company": "Test Company",
        "description": "Develop APIs",
        "deadline": (date.today() + timedelta(days=10)).isoformat(),
        "apply_mode": "collect",
    }
    payload.update(changes)
    return payload


@pytest.mark.parametrize("method,path", [
    ("get", "/api/ui/me"),
    ("get", "/api/ui/jobs"),
    ("get", "/api/ui/notifications"),
    ("post", "/api/ui/subscribe"),
    ("get", "/api/ui/employer/listings"),
    ("post", "/api/ui/employer/listings"),
    ("get", "/api/ui/admin/pending"),
    ("post", "/api/ui/admin/listings/1/publish"),
    ("post", "/api/ui/admin/listings/1/reject"),
])
def test_gui_api_requires_login(method, path):
    response = getattr(client, method)(path)
    assert response.status_code == 401


@pytest.mark.parametrize("role,path", [
    ("graduate", "/api/ui/employer/listings"),
    ("graduate", "/api/ui/admin/pending"),
    ("employer", "/api/ui/jobs"),
    ("employer", "/api/ui/notifications"),
    ("employer", "/api/ui/admin/pending"),
    ("admin", "/api/ui/jobs"),
    ("admin", "/api/ui/employer/listings"),
])
def test_role_boundaries(ids, role, path):
    assert client.get(path, headers=auth(ids[role])).status_code == 403


def test_user_profile_is_derived_from_cookie(ids):
    response = client.get("/api/ui/me", headers=auth(ids["employer"]))
    assert response.status_code == 200
    assert response.json()["id"] == ids["employer"]
    assert response.json()["role"] == "employer"


def test_non_dcit_cannot_subscribe(ids):
    response = client.post("/api/ui/subscribe", headers=auth(ids["other"]))
    assert response.status_code == 403
    with Session(engine) as db:
        assert db.exec(select(Subscription).where(Subscription.graduate_id == ids["other"])).first() is None


def test_duplicate_subscription_is_idempotent(ids):
    first = client.post("/api/ui/subscribe", headers=auth(ids["graduate"]))
    second = client.post("/api/ui/subscribe", headers=auth(ids["graduate"]))
    assert first.status_code == second.status_code == 200
    assert first.json()["already_subscribed"] is True
    assert second.json()["already_subscribed"] is True
    with Session(engine) as db:
        assert len(db.exec(select(Subscription).where(Subscription.graduate_id == ids["graduate"])).all()) == 1


def test_employer_listing_is_pending_and_owned(ids):
    response = client.post("/api/ui/employer/listings", json=listing_payload(), headers=auth(ids["employer"]))
    assert response.status_code == 201
    item = response.json()["listing"]
    assert item["status"] == "pending"
    assert item["employer_id"] == ids["employer"]
    own = client.get("/api/ui/employer/listings", headers=auth(ids["employer"]))
    others = client.get("/api/ui/employer/listings", headers=auth(ids["employer2"]))
    assert item["id"] in {row["id"] for row in own.json()["listings"]}
    assert item["id"] not in {row["id"] for row in others.json()["listings"]}


@pytest.mark.parametrize("changes", [
    {"title": " "},
    {"apply_mode": "invalid"},
    {"apply_mode": "external", "external_url": "javascript:alert(1)"},
    {"deadline": "2020-01-01"},
])
def test_listing_validation(ids, changes):
    response = client.post("/api/ui/employer/listings", json=listing_payload(**changes), headers=auth(ids["employer"]))
    assert response.status_code == 422


def test_publish_creates_one_notification_and_republish_conflicts(ids):
    created = client.post("/api/ui/employer/listings", json=listing_payload(), headers=auth(ids["employer"]))
    listing_id = created.json()["listing"]["id"]
    url = f"/api/ui/admin/listings/{listing_id}/publish"
    assert client.post(url, headers=auth(ids["employer"])).status_code == 403
    response = client.post(url, headers=auth(ids["admin"]))
    assert response.status_code == 200
    assert response.json()["notifications"] == 1
    assert client.post(url, headers=auth(ids["admin"])).status_code == 409
    notices = client.get("/api/ui/notifications", headers=auth(ids["graduate"]))
    assert notices.status_code == 200
    assert len(notices.json()["notifications"]) == 1
    assert "Test Graduate Engineer" in notices.json()["notifications"][0]["message"]
    assert client.get("/api/ui/jobs", headers=auth(ids["graduate"])).status_code == 200
    with Session(engine) as db:
        assert db.get(Listing, listing_id).status == "published"
        assert len(db.exec(select(Notification).where(Notification.user_id == ids["graduate"])).all()) == 1


def test_rejection_does_not_notify(ids):
    created = client.post("/api/ui/employer/listings", json=listing_payload(), headers=auth(ids["employer"]))
    listing_id = created.json()["listing"]["id"]
    assert client.post(f"/api/ui/admin/listings/{listing_id}/reject", headers=auth(ids["admin"])).status_code == 200
    assert client.post(f"/api/ui/admin/listings/{listing_id}/publish", headers=auth(ids["admin"])).status_code == 409
    with Session(engine) as db:
        assert db.get(Listing, listing_id).status == "rejected"
        assert db.exec(select(Notification)).all() == []


def test_registration_persists_programme_and_graduate_role():
    response = client.post("/register", data={
        "username": "newtestgraduate",
        "email": "newtestgraduate@example.com",
        "password": "SecureDemoPass2026!",
        "programme": "DCIT",
    }, follow_redirects=False)
    assert response.status_code == 303
    with Session(engine) as db:
        graduate = db.exec(select(Graduate).where(Graduate.username == "newtestgraduate")).one()
        assert graduate.programme == "DCIT"
        assert db.get(Admin, graduate.id) is None
        assert db.get(Employer, graduate.id) is None
    assert client.post("/api/ui/subscribe", headers=auth(graduate.id)).status_code == 200


def test_invalid_programme_does_not_create_graduate():
    response = client.post("/register", data={
        "username": "invalidgraduate",
        "email": "invalidgraduate@example.com",
        "password": "SecureDemoPass2026!",
        "programme": "ADMIN",
    }, follow_redirects=False)
    assert response.status_code == 303
    with Session(engine) as db:
        assert db.exec(select(Graduate).where(Graduate.username == "invalidgraduate")).first() is None


@pytest.mark.parametrize("method,path,data", [
    ("post", "/api/graduates/subscribe", {"actor_id": 1}),
    ("get", "/api/admin/listings/pending?actor_id=1", None),
    ("post", "/api/employer/listings", {"actor_id": 1}),
    ("post", "/api/admin/listings/1/publish", {"actor_id": 1}),
    ("post", "/api/admin/listings/1/notify", {"actor_id": 1}),
])
def test_legacy_actor_routes_require_login(method, path, data):
    response = getattr(client, method)(path, **({"json": data} if data is not None else {}))
    assert response.status_code == 401


def test_legacy_actor_id_cannot_impersonate_admin_or_employer(ids):
    assert client.get(
        f"/api/admin/listings/pending?actor_id={ids['admin']}",
        headers=auth(ids["graduate"]),
    ).status_code == 403
    assert client.post(
        "/api/employer/listings",
        json={**listing_payload(), "actor_id": ids["employer"]},
        headers=auth(ids["graduate"]),
    ).status_code == 403
    assert client.post(
        "/api/employer/listings",
        json={**listing_payload(), "actor_id": ids["employer2"]},
        headers=auth(ids["employer"]),
    ).status_code == 403
    assert client.post(
        "/api/admin/listings/2/publish",
        json={"actor_id": ids["admin"]},
        headers=auth(ids["employer"]),
    ).status_code == 403
    assert client.post(
        "/api/graduates/subscribe",
        json={"actor_id": ids["graduate"]},
        headers=auth(ids["other"]),
    ).status_code == 403
