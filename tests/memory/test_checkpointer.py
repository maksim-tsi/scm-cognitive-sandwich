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
