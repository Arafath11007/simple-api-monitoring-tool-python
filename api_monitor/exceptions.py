"""Exceptions for the API Health Monitor package."""

class MonitorError(Exception):
    """Base exception for all API monitor errors."""
    pass

class ConfigError(MonitorError):
    """Raised when configuration file is missing, malformed, or invalid."""
    pass

class ValidationError(MonitorError):
    """Raised when payload or schema validation fails."""
    pass

class StorageError(MonitorError):
    """Raised when writing or reading reports/data fails."""
    pass

class NotificationError(MonitorError):
    """Raised when alert notification delivery fails."""
    pass
