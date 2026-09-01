import re

import pytest

from tests._dbtest import _worker_suffix


@pytest.mark.parametrize("worker", [None, "gw0"])
def test_database_suffix_is_unique_for_each_suite_process(monkeypatch, worker: str | None) -> None:
    """Dos suites simultáneas no comparten la misma base efímera aunque compartan PID interno."""
    if worker is None:
        monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
        prefix = r"p\d+"
    else:
        monkeypatch.setenv("PYTEST_XDIST_WORKER", worker)
        prefix = re.escape(worker)

    first = _worker_suffix()
    second = _worker_suffix()

    assert first != second
    assert re.fullmatch(rf"{prefix}_[0-9a-f]{{8}}", first)
    assert re.fullmatch(rf"{prefix}_[0-9a-f]{{8}}", second)
