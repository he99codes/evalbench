"""Service layer. Routes call exactly one service function; services own all DB and LLM work.

Service errors are framework-agnostic; app.main maps them to HTTP responses.
"""


class ServiceError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class InvalidRequestError(ServiceError):
    """Semantically invalid input that passed schema validation (e.g. foreign criteria)."""

    status_code = 422
