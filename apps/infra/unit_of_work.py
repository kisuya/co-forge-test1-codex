from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Generic, TypeVar

TSession = TypeVar("TSession")
TModel = TypeVar("TModel")


class UnitOfWorkStateError(RuntimeError):
    """Raised when transaction lifecycle methods are called in invalid order."""


class _TransactionState(Enum):
    IDLE = "idle"
    ACTIVE = "active"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


@dataclass
class RepositoryBase(Generic[TModel, TSession]):
    session: TSession


class UnitOfWork(Generic[TSession]):
    def __init__(self, session_factory: Callable[[], TSession]) -> None:
        self._session_factory = session_factory
        self._session: TSession | None = None
        self._state = _TransactionState.IDLE

    @property
    def session(self) -> TSession:
        if self._session is None:
            raise UnitOfWorkStateError("transaction is not active")
        return self._session

    def __enter__(self) -> "UnitOfWork[TSession]":
        if self._state == _TransactionState.ACTIVE:
            raise UnitOfWorkStateError("nested transactions are not allowed")
        if self._state in {_TransactionState.COMMITTED, _TransactionState.ROLLED_BACK}:
            raise UnitOfWorkStateError("unit of work instances cannot be reused")

        self._session = self._session_factory()
        self._state = _TransactionState.ACTIVE
        return self

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> bool:
        if self._state != _TransactionState.ACTIVE:
            return False

        if exc is not None:
            self.rollback()
            return False

        self.commit()
        return False

    def commit(self) -> None:
        if self._state == _TransactionState.COMMITTED:
            raise UnitOfWorkStateError("duplicate commit is not allowed")
        if self._state != _TransactionState.ACTIVE:
            raise UnitOfWorkStateError("transaction is not active")

        session = self.session
        try:
            _invoke(session, "commit")
        except Exception:  # noqa: BLE001 - transactional safety requires rollback on any commit failure.
            _invoke(session, "rollback")
            _invoke(session, "close")
            self._state = _TransactionState.ROLLED_BACK
            raise

        _invoke(session, "close")
        self._state = _TransactionState.COMMITTED

    def rollback(self) -> None:
        if self._state != _TransactionState.ACTIVE:
            raise UnitOfWorkStateError("transaction is not active")

        session = self.session
        _invoke(session, "rollback")
        _invoke(session, "close")
        self._state = _TransactionState.ROLLED_BACK


def _invoke(session: Any, method_name: str) -> None:
    method = getattr(session, method_name, None)
    if method is None:
        raise UnitOfWorkStateError(f"session does not support '{method_name}'")
    method()
