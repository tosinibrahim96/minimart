"""Custom exceptions for the auth module."""


class UserAlreadyExistsError(Exception):
    """Raised when a user tries to create an account with an email that already exists."""
