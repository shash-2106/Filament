"""Database declarative base and metadata for SQLAlchemy models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy declarative models in Filament."""

    pass


# Register all domain models with Base.metadata upon import
import filament_api.models  # noqa: F401, E402
