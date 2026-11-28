import os
from typing import Self

import pytest

from tests.fixtures import enrichment_demo


def test_demo_cleans_container_and_restores_environment_on_startup_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[bool] = []

    class Container:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            closed.append(True)

        def get_connection_url(self) -> str:
            return "postgresql+asyncpg://test:test@127.0.0.1:1234/test"

    class Listener:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            pass

        def setsockopt(self, *_args: object) -> None:
            pass

        def bind(self, _address: object) -> None:
            pass

        def listen(self, _backlog: int) -> None:
            pass

    monkeypatch.setenv("PFA_DATABASE_URL", "original")

    def listener_factory(*_args: object, **_kwargs: object) -> Listener:
        return Listener()

    monkeypatch.setattr(enrichment_demo.socket, "socket", listener_factory)

    def container_factory(*_args: object, **_kwargs: object) -> Container:
        return Container()

    monkeypatch.setattr(enrichment_demo, "PostgresContainer", container_factory)

    def fail(_config: object, _revision: str) -> None:
        assert os.environ["PFA_DATABASE_URL"].endswith("/test")
        raise RuntimeError("synthetic startup failure")

    monkeypatch.setattr(enrichment_demo.command, "upgrade", fail)
    with pytest.raises(RuntimeError, match="synthetic startup failure"):
        enrichment_demo.main()
    assert closed == [True]
    assert os.environ["PFA_DATABASE_URL"] == "original"
