
from app.models.application_state import ApplicationState


class AppliedState(ApplicationState):
    allowed_actions = frozenset({"review"})

    def review(self, application):
        application.state = "reviewed"


class ReviewedState(ApplicationState):
    allowed_actions = frozenset({"shortlist"})

    def shortlist(self, application):
        application.state = "shortlisted"


class ShortlistedState(ApplicationState):
    allowed_actions = frozenset({"reject", "hire"})

    def hire(self, application):
        application.state = "hired"


class InterviewState(ApplicationState):
    allowed_actions = frozenset()

    def offer(self, application):
        application.state = "offered"


class OfferedState(ApplicationState):
    allowed_actions = frozenset()

    def accept_offer(self, application):
        application.state = "hired"

    def reject_offer(self, application):
        application.state = "withdrawn"


class HiredState(ApplicationState):
    allowed_actions = frozenset()


class RejectedState(ApplicationState):
    allowed_actions = frozenset()


class WithdrawnState(ApplicationState):
    allowed_actions = frozenset()


STATE_CLASSES = {
    "submitted": AppliedState,
    "reviewed": ReviewedState,
    "shortlisted": ShortlistedState,
    "rejected": RejectedState,
    "hired": HiredState,
}


def get_state(status: str):
    state_class = STATE_CLASSES.get(status)

    if state_class is None:
        return None

    return state_class()
