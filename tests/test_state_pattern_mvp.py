
import pytest

from app.models.application import Application
from app.models.application_state import ApplicationState
from app.models.states import (
    AppliedState,
    ReviewedState,
    ShortlistedState,
    InterviewState,
    OfferedState,
    HiredState,
    RejectedState,
    WithdrawnState,
    get_state,
)


def make_application(state="submitted"):
    return Application(
        listing_id=1,
        graduate_id=1,
        cover_letter="Cover letter",
        resume_text="Resume",
        state=state,
    )


def test_new_application_defaults_to_submitted():
    application = Application(
        listing_id=1,
        graduate_id=1,
        cover_letter="Cover letter",
        resume_text="Resume",
    )

    assert application.state == "submitted"
    assert isinstance(get_state(application.state), AppliedState)


@pytest.mark.parametrize(
    ("start", "action", "expected"),
    [
        ("submitted", "review", "reviewed"),
        ("reviewed", "shortlist", "shortlisted"),
        ("shortlisted", "reject", "rejected"),
        ("shortlisted", "hire", "hired"),
    ],
)
def test_valid_transitions(start, action, expected):
    application = make_application(start)

    assert application.transition(action) is True
    assert application.state == expected


@pytest.mark.parametrize(
    ("start", "action"),
    [
        ("submitted", "hire"),
        ("submitted", "reject"),
        ("submitted", "withdraw"),
        ("reviewed", "reject"),
        ("reviewed", "interview"),
        ("shortlisted", "interview"),
        ("shortlisted", "withdraw"),
        ("hired", "review"),
        ("rejected", "hire"),
        ("withdrawn", "review"),
        ("interview", "offer"),
        ("offered", "accept_offer"),
        ("submitted", "__class__"),
    ],
)
def test_invalid_transitions(start, action):
    application = make_application(start)

    assert application.transition(action) is False
    assert application.state == start


def test_all_eight_states_exist():
    classes = (
        AppliedState,
        ReviewedState,
        ShortlistedState,
        InterviewState,
        OfferedState,
        HiredState,
        RejectedState,
        WithdrawnState,
    )

    assert len(classes) == 8

    for state_class in classes:
        assert issubclass(state_class, ApplicationState)


def test_complete_hiring_lifecycle():
    application = make_application()

    assert application.review() is True
    assert application.state == "reviewed"

    assert application.shortlist() is True
    assert application.state == "shortlisted"

    assert application.hire() is True
    assert application.state == "hired"

    assert application.review() is False
    assert application.state == "hired"


def test_complete_rejection_lifecycle():
    application = make_application()

    assert application.review() is True
    assert application.shortlist() is True
    assert application.reject() is True

    assert application.state == "rejected"
    assert application.hire() is False
    assert application.state == "rejected"


def test_offered_state_design_routes_refusal_to_withdrawn():
    application = make_application("offered")

    OfferedState().reject_offer(application)

    assert application.state == "withdrawn"
