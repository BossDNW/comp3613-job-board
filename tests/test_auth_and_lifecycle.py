import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.dependencies.auth import get_current_user, is_admin, is_admin_dep
from app.models.admin import Admin
from app.models.application import Application
from app.models.employer import Employer
from app.models.graduate import Graduate
from app.models.listing import Listing
from app.models.user import User, UserBase
from app.repositories.user import UserRepository
from app.services import applications, board_auth
from app.services.auth_service import AuthService
from app.utilities.security import create_access_token, encrypt_password


def create_user(session, user_model, username):
    return UserRepository(session).create(
        UserBase(
            username=username,
            email=f"{username}@example.com",
            password=encrypt_password("secret"),
        ),
        user_model=user_model,
    )


def test_registration_creates_graduate_subtype_and_authenticates(test_session):
    repository = UserRepository(test_session)

    user = AuthService(repository).register_user(
        "newgraduate",
        "newgraduate@example.com",
        "secret",
    )

    assert test_session.get(User, user.id) is not None
    assert test_session.get(Graduate, user.id) is not None
    assert test_session.get(Employer, user.id) is None

    assert AuthService(repository).authenticate_user(
        "newgraduate",
        "secret",
    )

    assert AuthService(repository).authenticate_user(
        "newgraduate",
        "wrong",
    ) is None


@pytest.mark.parametrize(
    "user_model",
    [Admin, Graduate, Employer],
)
def test_board_login_authenticates_users_from_subtype(
    test_session,
    monkeypatch,
    user_model,
):
    monkeypatch.setattr(
        board_auth,
        "engine",
        test_session.get_bind(),
    )

    user = create_user(
        test_session,
        user_model,
        user_model.__name__.lower(),
    )

    result = board_auth.login(
        f"{user.username}@example.com",
        "secret",
    )

    assert result is not None
    assert result["id"] == user.id
    assert result["username"] == user.username
    assert "password" not in result


def test_current_user_authenticates_parent_user_from_token(test_session):
    user = create_user(
        test_session,
        Graduate,
        "tokenuser",
    )

    token = create_access_token(
        {"sub": str(user.id)}
    )

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [
                (
                    b"cookie",
                    f"access_token={token}".encode(),
                )
            ],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )

    authenticated = asyncio.run(
        get_current_user(request, test_session)
    )

    assert authenticated.id == user.id
    assert isinstance(authenticated, User)


def test_admin_authorization_accepts_admin_and_rejects_graduate(
    test_session,
):
    admin = create_user(
        test_session,
        Admin,
        "authorizedadmin",
    )

    graduate = create_user(
        test_session,
        Graduate,
        "nonadmin",
    )

    assert asyncio.run(
        is_admin(admin, test_session)
    )

    assert not asyncio.run(
        is_admin(graduate, test_session)
    )

    assert asyncio.run(
        is_admin_dep(admin, test_session)
    ).id == admin.id

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            is_admin_dep(graduate, test_session)
        )

    assert exc_info.value.status_code == 403


@pytest.fixture
def application_data(test_session, monkeypatch):
    monkeypatch.setattr(
        applications,
        "engine",
        test_session.get_bind(),
    )

    graduate = create_user(
        test_session,
        Graduate,
        "applicant",
    )

    other_graduate = create_user(
        test_session,
        Graduate,
        "otherapplicant",
    )

    employer = create_user(
        test_session,
        Employer,
        "listingowner",
    )

    other_employer = create_user(
        test_session,
        Employer,
        "otheremployer",
    )

    admin = create_user(
        test_session,
        Admin,
        "lifecycleadmin",
    )

    listing = Listing(
        employer_id=employer.id,
        title="Engineer",
        company="Example Co",
        description="Build things",
        apply_mode="collect",
        deadline="2099-12-31",
        status="published",
    )

    test_session.add(listing)
    test_session.commit()
    test_session.refresh(listing)

    application = Application(
        listing_id=listing.id,
        graduate_id=graduate.id,
        cover_letter="Interested",
        resume_text="Experience",
        state="submitted",
    )

    test_session.add(application)
    test_session.commit()
    test_session.refresh(application)

    return {
        "admin": admin,
        "application": application,
        "employer": employer,
        "graduate": graduate,
        "listing": listing,
        "other_employer": other_employer,
        "other_graduate": other_graduate,
        "session": test_session,
    }


def current_state(data):
    data["session"].expire_all()

    application = data["session"].get(
        Application,
        data["application"].id,
    )

    return application.state


def test_application_follows_review_and_shortlist_transitions(
    application_data,
):
    data = application_data

    transitions = [
        (
            data["employer"],
            "review",
            "reviewed",
        ),
        (
            data["employer"],
            "shortlist",
            "shortlisted",
        ),
    ]

    for actor, action, expected_state in transitions:
        result = applications.transition_application(
            actor.id,
            data["application"].id,
            action,
        )

        assert result["ok"] is True
        assert result["application"]["state"] == expected_state
        assert current_state(data) == expected_state


@pytest.mark.parametrize(
    (
        "action",
        "expected_state",
    ),
    [
        (
            "reject",
            "rejected",
        ),
        (
            "hire",
            "hired",
        ),
    ],
)
def test_shortlisted_application_can_be_rejected_or_hired(
    application_data,
    action,
    expected_state,
):
    data = application_data

    data["application"].state = "shortlisted"
    data["session"].add(data["application"])
    data["session"].commit()

    result = applications.transition_application(
        data["employer"].id,
        data["application"].id,
        action,
    )

    assert result["ok"] is True
    assert result["application"]["state"] == expected_state
    assert current_state(data) == expected_state


@pytest.mark.parametrize(
    (
        "starting_state",
        "actor_key",
        "action",
    ),
    [
        (
            "submitted",
            "employer",
            "shortlist",
        ),
        (
            "submitted",
            "employer",
            "reject",
        ),
        (
            "submitted",
            "employer",
            "hire",
        ),
        (
            "reviewed",
            "employer",
            "review",
        ),
        (
            "shortlisted",
            "employer",
            "shortlist",
        ),
        (
            "hired",
            "employer",
            "review",
        ),
        (
            "rejected",
            "employer",
            "hire",
        ),
    ],
)
def test_invalid_application_transition_leaves_state_unchanged(
    application_data,
    starting_state,
    actor_key,
    action,
):
    data = application_data

    data["application"].state = starting_state
    data["session"].add(data["application"])
    data["session"].commit()

    result = applications.transition_application(
        data[actor_key].id,
        data["application"].id,
        action,
    )

    assert result["ok"] is False
    assert result["error"] == "invalid application state transition"
    assert current_state(data) == starting_state


@pytest.mark.parametrize(
    (
        "actor_key",
        "action",
        "expected_error",
    ),
    [
        (
            "graduate",
            "review",
            "forbidden",
        ),
        (
            "employer",
            "unsupported",
            "forbidden",
        ),
        (
            "other_employer",
            "review",
            "forbidden",
        ),
    ],
)
def test_only_permitted_actor_subtypes_can_transition(
    application_data,
    actor_key,
    action,
    expected_error,
):
    data = application_data

    result = applications.transition_application(
        data[actor_key].id,
        data["application"].id,
        action,
    )

    assert result == {
        "ok": False,
        "error": expected_error,
    }

    assert current_state(data) == "submitted"


@pytest.mark.parametrize(
    "action",
    ["review", "reject"],
)
def test_admin_cannot_transition_application(
    application_data,
    action,
):
    data = application_data

    result = applications.transition_application(
        data["admin"].id,
        data["application"].id,
        action,
    )

    assert result == {
        "ok": False,
        "error": "forbidden",
    }

    assert current_state(data) == "submitted"


def test_application_transitions_are_limited_to_owning_actors(
    application_data,
):
    data = application_data

    graduate_result = applications.transition_application(
        data["other_graduate"].id,
        data["application"].id,
        "review",
    )

    employer_result = applications.transition_application(
        data["other_employer"].id,
        data["application"].id,
        "review",
    )

    assert graduate_result == {
        "ok": False,
        "error": "forbidden",
    }

    assert employer_result == {
        "ok": False,
        "error": "forbidden",
    }

    assert current_state(data) == "submitted"


def test_applicant_listing_is_limited_to_listing_owner(
    application_data,
):
    data = application_data

    owner_result = applications.listing_applicants(
        data["employer"].id,
        data["listing"].id,
    )

    other_employer_result = applications.listing_applicants(
        data["other_employer"].id,
        data["listing"].id,
    )

    assert owner_result["ok"] is True
    assert len(owner_result["applicants"]) == 1

    assert other_employer_result == {
        "ok": False,
        "error": "forbidden",
    }