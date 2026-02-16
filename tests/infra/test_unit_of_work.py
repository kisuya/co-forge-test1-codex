from __future__ import annotations

import unittest

from apps.infra.unit_of_work import UnitOfWork, UnitOfWorkStateError


class _FakeSession:
    def __init__(self) -> None:
        self.commit_calls = 0
        self.rollback_calls = 0
        self.close_calls = 0

    def commit(self) -> None:
        self.commit_calls += 1

    def rollback(self) -> None:
        self.rollback_calls += 1

    def close(self) -> None:
        self.close_calls += 1


class _FakeSessionFactory:
    def __init__(self) -> None:
        self.created_sessions: list[_FakeSession] = []

    def __call__(self) -> _FakeSession:
        session = _FakeSession()
        self.created_sessions.append(session)
        return session

    @property
    def last(self) -> _FakeSession:
        return self.created_sessions[-1]


class UnitOfWorkTests(unittest.TestCase):
    def test_success_path_commits_atomically(self) -> None:
        factory = _FakeSessionFactory()
        with UnitOfWork(factory) as uow:
            self.assertIsNotNone(uow.session)

        session = factory.last
        self.assertEqual(session.commit_calls, 1)
        self.assertEqual(session.rollback_calls, 0)
        self.assertEqual(session.close_calls, 1)

    def test_exception_path_rolls_back_and_propagates(self) -> None:
        factory = _FakeSessionFactory()

        with self.assertRaises(ValueError):
            with UnitOfWork(factory):
                raise ValueError("boom")

        session = factory.last
        self.assertEqual(session.commit_calls, 0)
        self.assertEqual(session.rollback_calls, 1)
        self.assertEqual(session.close_calls, 1)

    def test_nested_transaction_is_rejected(self) -> None:
        factory = _FakeSessionFactory()
        uow = UnitOfWork(factory)

        with uow:
            with self.assertRaises(UnitOfWorkStateError) as nested_error:
                uow.__enter__()
        self.assertIn("nested transactions", str(nested_error.exception))

    def test_duplicate_commit_is_rejected(self) -> None:
        factory = _FakeSessionFactory()
        uow = UnitOfWork(factory)

        with uow:
            uow.commit()
            with self.assertRaises(UnitOfWorkStateError) as duplicate_error:
                uow.commit()
        self.assertIn("duplicate commit", str(duplicate_error.exception))


if __name__ == "__main__":
    unittest.main()
