from app.models.application_state import ApplicationState

class AppliedState(ApplicationState):
    def review(self, application):
        application.state = "reviewed"

class ReviewedState(ApplicationState):
    def shortlist(self, application):
        application.state = "shortlisted"

class ShortlistedState(ApplicationState):
    def interview(self, application):
        application.state = "interview"

class InterviewState(ApplicationState):
    def offer(self, application):
        application.state = "offered"

class OfferedState(ApplicationState):
    def accept_offer(self, application):
        application.state = "hired"

    def reject_offer(self, application):
        application.state = "rejected"
        # application.state = "withdrawn"

class HiredState(ApplicationState):
    pass

class RejectedState(ApplicationState):
    pass

class WithdrawnState(ApplicationState):
    pass