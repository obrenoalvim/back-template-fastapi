from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine


class QueryCounter:
    def __init__(self) -> None:
        self.count = 0

    def reset(self) -> None:
        self.count = 0


@contextmanager
def count_queries(engine: AsyncEngine) -> Iterator[QueryCounter]:
    """Counts SQL statements sent to Postgres while the context is open.

    Used to guard against N+1 regressions: a repository function that's
    supposed to eager-load a relationship must keep running the same number
    of queries no matter how many rows exist.
    """
    counter = QueryCounter()
    sync_engine = engine.sync_engine

    def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany) -> None:
        counter.count += 1

    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        yield counter
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)
