from abc import ABC

class ApplicationState(ABC):
    def reject(self, application):
        application.state = "rejected"

    def withdraw(self, application):
        application.state = "withdrawn"