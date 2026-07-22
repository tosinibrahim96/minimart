"""Custom exceptions for the products module."""


class ProductNotFoundError(Exception):
    """Raised when a product lookup finds nothing."""


class DuplicateSKUError(Exception):
    """Raised when attempting to create a product with an existing SKU, when the current product with the SKU is not soft deleted."""
