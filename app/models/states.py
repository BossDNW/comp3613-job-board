from app.models.application_state import ApplicationState

class AppliedState(ApplicationState):
    allowed_actions = frozenset({"review", "reject", "withdraw"})

    def review(self, application):
        application.state = "reviewed"


class ReviewedState(ApplicationState):
    allowed_actions = frozenset({"shortlist", "reject", "withdraw"})

    def shortlist(self, application):
        application.state = "shortlisted"


class ShortlistedState(ApplicationState):
    allowed_actions = frozenset({"interview", "reject", "withdraw"})

    def interview(self, application):
        application.state = "interview"


class InterviewState(ApplicationState):
    allowed_actions = frozenset({"offer", "reject", "withdraw"})

    def offer(self, application):
        application.state = "offered"


class OfferedState(ApplicationState):
    allowed_actions = frozenset({
        "accept_offer",
        "reject_offer",
        "reject",
        "withdraw",
    })

    def accept_offer(self, application):
        application.state = "hired"

    def reject_offer(self, application):
        application.state = "rejected"


class HiredState(ApplicationState):
    pass

class RejectedState(ApplicationState):
    pass

class WithdrawnState(ApplicationState):
    pass


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


def get_state(status: str):
    state_class = STATE_CLASSES.get(status)

    if state_class is None:
        return None

    return state_class()
