class AdminServiceError(Exception):
    """Base error for administrative operations."""


class ResourceNotFoundError(AdminServiceError):
    """Raised when an administrative resource does not exist."""


class ResourceConflictError(AdminServiceError):
    """Raised when an operation violates a business uniqueness rule."""
