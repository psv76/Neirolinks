"""Atomic unit-of-work boundary for multi-entity commands."""

from __future__ import annotations

from sqlalchemy import Engine
from sqlalchemy.orm import Session


class UnitOfWork:
    """One explicit SQLAlchemy session and transaction per application command."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._session: Session | None = None
        self._committed = False

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._session

    def __enter__(self) -> UnitOfWork:
        if self._session is not None:
            raise RuntimeError("UnitOfWork cannot be entered twice")
        self._session = Session(bind=self._engine, autoflush=False, expire_on_commit=False)
        return self

    def execute(self, statement, parameters=None):
        if parameters is None:
            return self.session.execute(statement)
        return self.session.execute(statement, parameters)

    def commit(self) -> None:
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        self.session.rollback()
        self._committed = False

    def __exit__(self, exc_type, _exc, _traceback) -> None:
        if self._session is None:
            return
        try:
            if exc_type is not None or not self._committed:
                self._session.rollback()
        finally:
            self._session.close()
            self._session = None
