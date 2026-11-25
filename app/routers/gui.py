from datetime import date
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app.dependencies.auth import AuthDep
from app.dependencies.session import SessionDep
from app.models.admin import Admin
from app.models.employer import Employer
from app.models.graduate import Graduate
from app.models.listing import Listing
from app.models.notification import Notification
from app.models.subscription import Subscription

router = APIRouter(prefix="/ui", tags=["Graphical Job Board"])


class ListingInput(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    company: str = Field(min_length=1, max_length=150)
    description: str = Field(min_length=1)
    deadline: date
    apply_mode: str
    external_url: str | None = None


def get_role(user: AuthDep, db: SessionDep) -> str:
    matches = [
        name
        for name, model in (
            ("graduate", Graduate),
            ("employer", Employer),
            ("admin", Admin),
        )
        if db.get(model, user.id) is not None
    ]

    if len(matches) != 1:
        raise HTTPException(status_code=403, detail="Invalid account role")

    return matches[0]


def require_role(user: AuthDep, db: SessionDep, role: str) -> None:
    if get_role(user, db) != role:
        raise HTTPException(
            status_code=403,
            detail=f"{role.title()} access required",
        )


def valid_deadline(value: str) -> bool:
    try:
        return date.fromisoformat(value) >= date.today()
    except (TypeError, ValueError):
        return False


@router.get("/me")
def current_account(user: AuthDep, db: SessionDep):
    return {
        "id": user.id,
        "username": user.username,
        "role": get_role(user, db),
    }


@router.get("/jobs")
def published_jobs(user: AuthDep, db: SessionDep):
    require_role(user, db, "graduate")

    listings = db.exec(
        select(Listing)
        .where(Listing.status == "published")
        .order_by(Listing.id.desc())
    ).all()

    return {
        "jobs": [
            listing.model_dump()
            for listing in listings
            if valid_deadline(listing.deadline)
        ]
    }


@router.post("/subscribe")
def subscribe(user: AuthDep, db: SessionDep):
    require_role(user, db, "graduate")

    graduate = db.get(Graduate, user.id)

    if graduate.programme != "DCIT":
        raise HTTPException(
            status_code=403,
            detail="Only DCIT graduates may subscribe",
        )

    existing = db.exec(
        select(Subscription).where(
            Subscription.graduate_id == graduate.id
        )
    ).first()

    if existing is not None:
        return {"ok": True, "already_subscribed": True}

    db.add(Subscription(graduate_id=graduate.id))
    db.commit()

    return {"ok": True, "already_subscribed": False}


@router.get("/notifications")
def notifications(user: AuthDep, db: SessionDep):
    require_role(user, db, "graduate")

    rows = db.exec(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.id.desc())
    ).all()

    return {"notifications": [row.model_dump() for row in rows]}


@router.get("/employer/listings")
def employer_listings(user: AuthDep, db: SessionDep):
    require_role(user, db, "employer")

    rows = db.exec(
        select(Listing)
        .where(Listing.employer_id == user.id)
        .order_by(Listing.id.desc())
    ).all()

    return {"listings": [row.model_dump() for row in rows]}


@router.post("/employer/listings", status_code=201)
def create_listing(
    body: ListingInput,
    user: AuthDep,
    db: SessionDep,
):
    require_role(user, db, "employer")

    title = body.title.strip()
    company = body.company.strip()
    description = body.description.strip()

    if not all((title, company, description)):
        raise HTTPException(
            status_code=422,
            detail="All listing details are required",
        )

    if body.apply_mode not in {"collect", "external"}:
        raise HTTPException(
            status_code=422,
            detail="Invalid application mode",
        )

    if body.deadline < date.today():
        raise HTTPException(
            status_code=422,
            detail="Deadline cannot be in the past",
        )

    external_url = None

    if body.apply_mode == "external":
        external_url = (body.external_url or "").strip()
        parsed = urlparse(external_url)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise HTTPException(
                status_code=422,
                detail="A valid external URL is required",
            )

    listing = Listing(
        employer_id=user.id,
        title=title,
        company=company,
        description=description,
        apply_mode=body.apply_mode,
        external_url=external_url,
        deadline=body.deadline.isoformat(),
        status="pending",
    )

    db.add(listing)
    db.commit()
    db.refresh(listing)

    return {"ok": True, "listing": listing.model_dump()}


@router.get("/admin/pending")
def pending_listings(user: AuthDep, db: SessionDep):
    require_role(user, db, "admin")

    rows = db.exec(
        select(Listing)
        .where(Listing.status == "pending")
        .order_by(Listing.id.desc())
    ).all()

    return {"listings": [row.model_dump() for row in rows]}


@router.post("/admin/listings/{listing_id}/publish")
def publish_listing(
    listing_id: int,
    user: AuthDep,
    db: SessionDep,
):
    require_role(user, db, "admin")

    listing = db.get(Listing, listing_id)

    if listing is None:
        raise HTTPException(404, "Listing not found")

    if listing.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending listings can be published",
        )

    if not valid_deadline(listing.deadline):
        raise HTTPException(
            status_code=409,
            detail="Listing deadline has passed or is invalid",
        )

    listing.status = "published"
    db.add(listing)

    subscriptions = db.exec(select(Subscription)).all()

    for subscription in subscriptions:
        db.add(
            Notification(
                user_id=subscription.graduate_id,
                message=(
                    f"New job published: "
                    f"{listing.title} at {listing.company}"
                ),
            )
        )

    db.commit()

    return {
        "ok": True,
        "status": "published",
        "notifications": len(subscriptions),
    }


@router.post("/admin/listings/{listing_id}/reject")
def reject_listing(
    listing_id: int,
    user: AuthDep,
    db: SessionDep,
):
    require_role(user, db, "admin")

    listing = db.get(Listing, listing_id)

    if listing is None:
        raise HTTPException(404, "Listing not found")

    if listing.status != "pending":
        raise HTTPException(
            status_code=409,
            detail="Only pending listings can be rejected",
        )

    listing.status = "rejected"
    db.add(listing)
    db.commit()

    return {"ok": True, "status": "rejected"}
