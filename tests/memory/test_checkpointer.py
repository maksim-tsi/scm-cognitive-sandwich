from contextlib import asynccontextmanager

from langgraph.checkpoint.memory import MemorySaver

from memory.checkpointer import DEFAULT_CHECKPOINT_PREFIX, create_checkpointer


def test_create_checkpointer_without_redis_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)

    checkpointer = create_checkpointer()

    assert isinstance(checkpointer, MemorySaver)


def test_create_checkpointer_with_redis_url_but_missing_package(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/1")
    monkeypatch.setattr("memory.checkpointer._load_redis_saver_class", lambda: None)

    checkpointer = create_checkpointer()

    assert isinstance(checkpointer, MemorySaver)


def test_create_checkpointer_uses_prefix_for_redis_builder(monkeypatch):
    calls: dict[str, str] = {}

    class FakeRedisSaver:
        key_prefix: str | None = None

        @classmethod
        def from_conn_string(cls, redis_url: str, key_prefix: str):
            calls["redis_url"] = redis_url
            calls["key_prefix"] = key_prefix
            instance = cls()
            instance.key_prefix = key_prefix
            return instance

    monkeypatch.setattr("memory.checkpointer._load_redis_saver_class", lambda: FakeRedisSaver)

    checkpointer = create_checkpointer(redis_url="redis://localhost:6379/1")

    assert not isinstance(checkpointer, MemorySaver)
    assert calls["redis_url"] == "redis://localhost:6379/1"
    assert calls["key_prefix"] == DEFAULT_CHECKPOINT_PREFIX


def test_create_checkpointer_falls_back_when_redis_init_fails(monkeypatch):
    class FailingRedisSaver:
        @classmethod
        def from_conn_string(cls, redis_url: str, key_prefix: str):  # noqa: ARG003
            raise RuntimeError("boom")

    monkeypatch.setattr("memory.checkpointer._load_redis_saver_class", lambda: FailingRedisSaver)

    checkpointer = create_checkpointer(redis_url="redis://localhost:6379/1")

    assert isinstance(checkpointer, MemorySaver)


def test_create_checkpointer_supports_awaitable_builder(monkeypatch):
    calls: dict[str, str] = {}

    class FakeAsyncRedisSaver:
        key_prefix: str | None = None

        @classmethod
        async def from_conn_string(cls, redis_url: str, key_prefix: str):
            calls["redis_url"] = redis_url
            calls["key_prefix"] = key_prefix
            instance = cls()
            instance.key_prefix = key_prefix
            return instance

    monkeypatch.setattr("memory.checkpointer._load_redis_saver_class", lambda: FakeAsyncRedisSaver)

    checkpointer = create_checkpointer(redis_url="redis://localhost:6379/1")

    assert not isinstance(checkpointer, MemorySaver)
    assert calls["redis_url"] == "redis://localhost:6379/1"
    assert calls["key_prefix"] == DEFAULT_CHECKPOINT_PREFIX


def test_create_checkpointer_calls_saver_setup(monkeypatch):
    calls: dict[str, int] = {"setup": 0}

    class FakeRedisSaver:
        key_prefix: str | None = None

        @classmethod
        def from_conn_string(cls, redis_url: str, key_prefix: str):  # noqa: ARG003
            instance = cls()
            instance.key_prefix = key_prefix
            return instance

        def setup(self):
            calls["setup"] += 1

    monkeypatch.setattr("memory.checkpointer._load_redis_saver_class", lambda: FakeRedisSaver)

    checkpointer = create_checkpointer(redis_url="redis://localhost:6379/1")

    assert isinstance(checkpointer, FakeRedisSaver)
    assert calls["setup"] == 1


def test_create_checkpointer_resolves_awaitable_saver_setup(monkeypatch):
    calls: dict[str, bool] = {"setup_completed": False}

    class FakeRedisSaver:
        key_prefix: str | None = None

        @classmethod
        def from_conn_string(cls, redis_url: str, key_prefix: str):  # noqa: ARG003
            instance = cls()
            instance.key_prefix = key_prefix
            return instance

        def setup(self):
            async def _setup():
                calls["setup_completed"] = True

            return _setup()

    monkeypatch.setattr("memory.checkpointer._load_redis_saver_class", lambda: FakeRedisSaver)

    checkpointer = create_checkpointer(redis_url="redis://localhost:6379/1")

    assert isinstance(checkpointer, FakeRedisSaver)
    assert calls["setup_completed"] is True


def test_create_checkpointer_skips_async_context_manager_builder(monkeypatch):
    class FakeRedisSaver:
        def __init__(self, redis_url: str, key_prefix: str | None = None):
            self.redis_url = redis_url
            self.key_prefix = key_prefix

        @classmethod
        def from_conn_string(cls, redis_url: str, key_prefix: str):
            @asynccontextmanager
            async def _manager():
                yield cls(redis_url=redis_url, key_prefix=key_prefix)

            return _manager()

    monkeypatch.setattr("memory.checkpointer._load_redis_saver_class", lambda: FakeRedisSaver)

    checkpointer = create_checkpointer(redis_url="redis://localhost:6379/1")

    assert isinstance(checkpointer, FakeRedisSaver)
    assert checkpointer.redis_url == "redis://localhost:6379/1"
    assert checkpointer.key_prefix == DEFAULT_CHECKPOINT_PREFIX
