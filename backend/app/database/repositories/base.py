"""Generic repository base.

Provides shared CRUD operations used by every concrete repository to avoid
duplicated query code. Repositories receive a SQLAlchemy session through their
constructor (dependency injection) and each public method is a self-contained
transaction: changes are flushed, committed and reloaded so server-generated
values (ids, timestamps, defaults) are available on the returned instance.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Self, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class _UnsetType:
    """Sentinel used to distinguish 'not provided' from an explicit ``None``.

    A module-level instance is available as :data:`UNSET`.
    """

    _instance: "_UnsetType | None" = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "UNSET"


#: Unique sentinel instance; see :class:`_UnsetType`.
UNSET: _UnsetType = _UnsetType()


class BaseRepository[ModelT: Base](ABC):
    """CRUD operations shared by all repositories.

    Args:
        db: SQLAlchemy session used for all database interaction.
    """

    def __init__(self, db: Session) -> None:
        self._db = db

    @property
    @abstractmethod
    def _model(self) -> type[ModelT]:
        """Return the ORM model managed by this repository."""

    def get_by_id(self, entity_id: int) -> ModelT | None:
        """Return the entity with the given primary key, or ``None``.

        Args:
            entity_id: Primary key of the entity.

        Returns:
            The matching entity or ``None`` when it does not exist.
        """
        return self._db.get(self._model, entity_id)

    def list(self, *, offset: int = 0, limit: int = 50) -> Sequence[ModelT]:
        """Return entities ordered by primary key with pagination.

        Args:
            offset: Number of rows to skip.
            limit: Maximum number of rows to return.

        Returns:
            A sequence of entities.
        """
        statement = (
            select(self._model)
            .order_by(self._model.id)
            .offset(offset)
            .limit(limit)
        )
        return self._db.scalars(statement).all()

    def delete(self, entity: ModelT) -> None:
        """Delete an entity and commit the transaction.

        Args:
            entity: Entity instance to delete.
        """
        self._db.delete(entity)
        self._db.commit()

    def _commit_and_refresh(self, entity: ModelT) -> ModelT:
        """Commit the session and reload server-generated values.

        Args:
            entity: Entity to persist and refresh.

        Returns:
            The refreshed entity.
        """
        self._db.commit()
        self._db.refresh(entity)
        return entity
