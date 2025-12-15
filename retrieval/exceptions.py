"""Custom exception hierarchy for the retrieval engine."""


class RetrievalError(Exception):
    """Base exception for retrieval engine errors."""


class ConfigError(RetrievalError):
    """Raised when configuration is invalid or incomplete."""


class DatabaseError(RetrievalError):
    """Raised when database operations fail."""


class AcquisitionError(RetrievalError):
    """Raised when acquiring or downloading resources fails."""


class ParseError(RetrievalError):
    """Raised when parsing or extraction fails."""


class IndexError(RetrievalError):
    """Raised when indexing or search operations fail."""
