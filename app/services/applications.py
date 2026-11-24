"""Application create / read / state transitions."""

from __future__ import annotations
from typing import Any
from sqlmodel import Session, select
from app.database import engine

from app.models.application import Application
from app.models.listing import Listing
from app.models.graduate import Graduate
from app.models.employer import Employer
from app.models.states import AppliedState, ReviewedState, ShortlistedState, InterviewState, OfferedState, HiredState, RejectedState, WithdrawnState


STATE_CLASSES = {
    "applied": AppliedState,
    "reviewed": ReviewedState,
    "shortlisted": ShortlistedState,
    "interview": InterviewState,
    "offered": OfferedState,
    "hired": HiredState,
    "rejected": RejectedState,
    "withdrawn": WithdrawnState,
}

EMPLOYER_ACTIONS = {
    "review", "shortlist", "interview", "offer", "reject"
}

GRADUATE_ACTIONS = {
    "accept_offer", "reject_offer", "withdraw"
}


def get_state(application: Application):
    state_class = STATE_CLASSES.get(application.state)
    if state_class is None:
        return None
    return state_class()


def apply(
    graduate_id: int,
    listing_id: int,
    cover_letter: str,
    resume_text: str | None = None,
) -> dict[str, Any]:

    with Session(engine) as session:

        graduate = session.get(Graduate, graduate_id)
        if graduate is None:
            return {"ok": False, "error": "graduate not found"}

        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}

        resume = resume_text or graduate.resume_text or ""

        application = Application(
            listing_id=listing_id,
            graduate_id=graduate_id,
            cover_letter=cover_letter,
            resume_text=resume,
            state="applied",
        )

        session.add(application)
        session.commit()
        session.refresh(application)

        return {
            "ok": True,
            "application_id": application.id,
            "state": application.state,
        }


def my_applications(graduate_id: int) -> list[dict[str, Any]]:

    with Session(engine) as session:

        graduate = session.get(Graduate, graduate_id)
        if graduate is None:
            return []

        applications = session.exec(
            select(Application)
            .where(Application.graduate_id == graduate_id)
            .order_by(Application.id)
        ).all()

        return [application.model_dump() for application in applications]


def listing_applicants(employer_id: int, listing_id: int) -> dict[str, Any]:

    with Session(engine) as session:

        employer = session.get(Employer, employer_id)
        if employer is None:
            return {"ok": False, "error": "employer not found"}

        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}

        if listing.employer_id != employer_id:
            return {"ok": False, "error": "forbidden"}

        applications = session.exec(
            select(Application)
            .where(Application.listing_id == listing_id)
            .order_by(Application.id)
        ).all()

        return {"ok": True, "applicants": [application.model_dump() for application in applications]}


def export_applicants(
        employer_id: int,
        listing_id: int
) -> dict[str, Any]:

    result = listing_applicants(employer_id, listing_id)
    if not result.get("ok"):
        return result

    return {"ok": True, "format": "json", "package": result["applicants"]}

def export_applicants_admin(
    listing_id: int
) -> dict[str, Any]:

    with Session(engine) as session:

        listing = session.get(Listing, listing_id)

        if listing is None:
            return {
                "ok": False,
                "error": "listing not found"
            }

        applicants = session.exec(
            select(Application)
            .where(Application.listing_id == listing_id)
            .order_by(Application.id)
        ).all()

        return {
            "ok": True,
            "format": "json",
            "package": [
                applicant.model_dump()
                for applicant in applicants
            ]
        }

def transition_application(
    actor_id: int,
    application_id: int,
    action: str,
    actor_role: str
) -> dict[str, Any]:

    with Session(engine) as session:

        application = session.get(Application, application_id)

        if application is None:
            return {
                "ok": False,
                "error": "application not found"
            }

        # Identify the actor using their verified role.
        if actor_role == "graduate":

            graduate = session.get(Graduate, actor_id)

            if graduate is None:
                return {"ok": False, "error": "forbidden"}

            if application.graduate_id != graduate.id:
                return {"ok": False, "error": "forbidden"}

            allowed_actions = GRADUATE_ACTIONS

        elif actor_role == "employer":

            employer = session.get(Employer, actor_id)

            if employer is None:
                return {"ok": False, "error": "forbidden"}

            listing = session.get(
                Listing, application.listing_id
            )

            if listing is None:
                return {
                    "ok": False,
                    "error": "listing not found"
                }

            if listing.employer_id != employer.id:
                return {"ok": False, "error": "forbidden"}

            allowed_actions = EMPLOYER_ACTIONS

        else:
            return {"ok": False, "error": "forbidden"}

        # Check the action against the actor's role.
        if action not in allowed_actions:
            return {"ok": False, "error": "forbidden"}

        # Do not reopen terminal states.
        if application.state in {
            "hired", "rejected", "withdrawn"
        }:
            return {
                "ok": False,
                "error": "invalid application state transition"
            }

        # Find the current State Pattern object.
        state = get_state(application)

        if state is None:
            return {
                "ok": False,
                "error": "invalid application state"
            }

        # Restrict actions to valid source states.
        valid_sources = {
            "review": {"applied"},
            "shortlist": {"reviewed"},
            "interview": {"shortlisted"},
            "offer": {"interview"},
            "accept_offer": {"offered"},
            "reject_offer": {"offered"},
            "reject": {
                "applied", "reviewed", "shortlisted",
                "interview", "offered"
            },
            "withdraw": {
                "applied", "reviewed", "shortlisted",
                "interview", "offered"
            },
        }

        if application.state not in valid_sources.get(
            action, set()
        ):
            return {
                "ok": False,
                "error": "invalid application state transition"
            }

        # Delegate the transition to the State Pattern.
        method = getattr(state, action, None)

        if not callable(method):
            return {
                "ok": False,
                "error": "invalid application state transition"
            }

        previous_state = application.state

        method(application)

        if application.state == previous_state:
            return {
                "ok": False,
                "error": "invalid application state transition"
            }

        session.add(application)
        session.commit()
        session.refresh(application)

        return {
            "ok": True,
            "application": application.model_dump(),
            "changed": True
        }