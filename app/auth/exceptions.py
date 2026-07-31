"""Custom exceptions for the auth module."""


class UserAlreadyExistsError(Exception):
    """Raised when a user tries to create an account with an email that already exists."""


class InvalidCredentialsError(Exception):
    """Raised when a user tries to login with invalid credentials."""


class InvalidTokenError(Exception):
    """Raised when a token is invalid."""


class ExpiredTokenError(InvalidTokenError):
    """Raised when a token is expired."""


class InvalidSubjectError(InvalidTokenError):
    """Raised when a token has an invalid subject."""


class ForbiddenError(Exception):
    """Raised when a user is not authorized to access a resource."""
