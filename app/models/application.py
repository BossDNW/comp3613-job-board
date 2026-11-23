from typing import Optional
from sqlmodel import Field, SQLModel

class Application(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    graduate_id: int = Field(foreign_key="graduate.id", index=True)
    cover_letter: str
    resume_text: str
    state: str = "applied"

    # def __init__(self):
    #     self.state = AppliedState()

    def review(self):
        self.state.review(self)

    def shortlist(self):
        self.state.shortlist(self)

    def interview(self):
        self.state.interview(self)

    def offer(self):
        self.state.offer(self)

    def accept_offer(self):
        self.state.accept_offer(self)

    def reject_offer(self):
        self.state.reject_offer(self)

    def reject(self):
        self.state.reject(self)

    def withdraw(self):
        self.state.withdraw(self)