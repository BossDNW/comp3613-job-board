import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.database import engine
from app.main import app
from app.models.application import Application
from app.models.employer import Employer
from app.models.graduate import Graduate
from app.models.listing import Listing
from app.models.states import get_state
from app.seed import seed
from app.utilities.security import create_access_token


client = TestClient(app)


@pytest.fixture(autouse=True)
def application_test_data(isolated_test_database):
    assert engine.url.database.endswith("application-tests.db")
    seed(reset=True)
    yield


def auth_cookie(user_id: int) -> dict[str, str]:
    token = create_access_token({"sub": str(user_id)})
    return {"Cookie": f"access_token={token}"}


def seed_ids() -> tuple[int, int, int, int]:
    with Session(engine) as session:
        graduate = session.exec(
            select(Graduate).where(Graduate.programme == "DCIT")
        ).one()
        employer = session.exec(
            select(Employer).where(Employer.email == "employer@example.com")
        ).one()
        listing = session.exec(
            select(Listing).where(
                Listing.employer_id == employer.id,
                Listing.apply_mode == "collect",
            )
        ).first()
        assert listing is not None
        return graduate.id, employer.id, listing.id


@pytest.mark.parametrize(
    ("initial_state", "action", "expected_state"),
    [
        ("submitted", "review", "reviewed"),
        ("reviewed", "shortlist", "shortlisted"),
        ("shortlisted", "reject", "rejected"),
        ("shortlisted", "hire", "hired"),
    ],
)
def test_state_objects_allow_only_the_next_approved_stage(
    initial_state,
    action,
    expected_state,
):
    application = Application(
        listing_id=1,
        graduate_id=1,
        cover_letter="Cover letter",
        resume_text="Resume",
        state=initial_state,
    )
    state = get_state(initial_state)

    assert state is not None
    assert state.transition(application, action) is True
    assert application.state == expected_state


@pytest.mark.parametrize(
    ("initial_state", "action"),
    [
        ("submitted", "shortlist"),
        ("submitted", "hire"),
        ("reviewed", "review"),
        ("shortlisted", "review"),
        ("rejected", "review"),
        ("hired", "reject"),
    ],
)
def test_skipped_repeated_and_terminal_actions_are_rejected(
    initial_state,
    action,
):
    application = Application(
        listing_id=1,
        graduate_id=1,
        cover_letter="Cover letter",
        resume_text="Resume",
        state=initial_state,
    )

    assert application.transition(action) is False
    assert application.state == initial_state


def test_application_context_delegates_to_the_resolved_state(monkeypatch):
    application = Application(
        listing_id=1,
        graduate_id=1,
        cover_letter="Cover letter",
        resume_text="Resume",
        state="submitted",
    )
    calls = []

    class DelegatingState:
        def transition(self, context, action):
            calls.append((context, action))
            context.state = "reviewed"
            return True

    monkeypatch.setattr(
        "app.models.states.get_state",
        lambda state: DelegatingState() if state == "submitted" else None,
    )

    assert application.transition("review") is True
    assert calls == [(application, "review")]
    assert application.state == "reviewed"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/graduates/applications"),
        ("get", "/api/listings/1/applicants"),
        ("get", "/api/admin/listings/1/export"),
        ("post", "/api/applications/1/transition"),
    ],
)
def test_protected_application_endpoints_require_authentication(method, path):
    if method == "post":
        response = client.post(path, json={"action": "review"})
    else:
        response = client.get(path)

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("listing_status", "deadline", "expected_detail"),
    [
        ("pending", "2099-12-31", "listing is not available"),
        ("published", "2020-01-01", "listing deadline has passed"),
    ],
)
def test_unpublished_and_expired_collect_listings_reject_applications(
    listing_status,
    deadline,
    expected_detail,
):
    graduate_id, employer_id, _ = seed_ids()
    with Session(engine) as session:
        listing = Listing(
            employer_id=employer_id,
            title="Unavailable role",
            company="Test Co",
            description="Not available for application.",
            apply_mode="collect",
            deadline=deadline,
            status=listing_status,
        )
        session.add(listing)
        session.commit()
        session.refresh(listing)
        listing_id = listing.id

    response = client.post(
        "/api/graduates/applications",
        headers=auth_cookie(graduate_id),
        json={
            "listing_id": listing_id,
            "cover_letter": "Cover letter",
            "resume_text": "Resume",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == expected_detail
    with Session(engine) as session:
        applications = session.exec(
            select(Application).where(Application.listing_id == listing_id)
        ).all()
        assert applications == []


@pytest.mark.parametrize(
    ("cover_letter", "resume_text"),
    [
        ("", "Resume"),
        ("   ", "Resume"),
        ("Cover letter", "   "),
    ],
)
def test_blank_application_payloads_create_no_record(cover_letter, resume_text):
    graduate_id, _, listing_id = seed_ids()
    with Session(engine) as session:
        before = len(session.exec(select(Application)).all())

    response = client.post(
        "/api/graduates/applications",
        headers=auth_cookie(graduate_id),
        json={
            "listing_id": listing_id,
            "cover_letter": cover_letter,
            "resume_text": resume_text,
        },
    )

    assert response.status_code == 422
    with Session(engine) as session:
        after = len(session.exec(select(Application)).all())
        assert after == before


@pytest.mark.parametrize(
    "resume_field",
    [
        pytest.param("omitted", id="omitted"),
        pytest.param("empty", id="explicit-empty"),
    ],
)
def test_saved_resume_is_used_when_request_resume_is_missing(resume_field):
    graduate_id, _, listing_id = seed_ids()
    payload = {
        "listing_id": listing_id,
        "cover_letter": "Cover letter",
    }
    if resume_field == "empty":
        payload["resume_text"] = ""

    response = client.post(
        "/api/graduates/applications",
        headers=auth_cookie(graduate_id),
        json=payload,
    )

    assert response.status_code == 200
    with Session(engine) as session:
        application = session.exec(
            select(Application).where(Application.listing_id == listing_id)
        ).one()
        graduate = session.get(Graduate, graduate_id)
        assert application.resume_text == graduate.resume_text


def test_resume_is_required_when_no_saved_resume_exists():
    graduate_id, _, listing_id = seed_ids()
    with Session(engine) as session:
        graduate = session.get(Graduate, graduate_id)
        graduate.resume_text = "   "
        session.add(graduate)
        session.commit()

    response = client.post(
        "/api/graduates/applications",
        headers=auth_cookie(graduate_id),
        json={
            "listing_id": listing_id,
            "cover_letter": "Cover letter",
            "resume_text": "",
        },
    )

    assert response.status_code == 422
    with Session(engine) as session:
        applications = session.exec(
            select(Application).where(Application.listing_id == listing_id)
        ).all()
        assert applications == []


def test_invalid_graduate_and_listing_ids_return_not_found():
    from app.services.applications import apply

    graduate_id, _, listing_id = seed_ids()

    assert apply(99999, listing_id, "Cover letter", "Resume") == {
        "ok": False,
        "error": "graduate not found",
    }
    assert apply(graduate_id, 99999, "Cover letter", "Resume") == {
        "ok": False,
        "error": "listing not found",
    }


def test_repeated_invalid_transition_never_mutates_persisted_status():
    from app.services.applications import apply, transition_application

    graduate_id, employer_id, listing_id = seed_ids()
    created = apply(graduate_id, listing_id, "Cover letter", "Resume")
    application_id = created["application_id"]

    for _ in range(3):
        result = transition_application(employer_id, application_id, "hire")
        assert result == {
            "ok": False,
            "error": "invalid application state transition",
        }

    with Session(engine) as session:
        application = session.get(Application, application_id)
        assert application.state == "submitted"
