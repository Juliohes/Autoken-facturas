"""Comportamiento de la caché local de existencia de buckets MinIO."""

from concurrent.futures import ThreadPoolExecutor
from time import sleep
from types import SimpleNamespace

from invoice_intake import storage


class _BucketClient:
    def __init__(self, exists: bool = True) -> None:
        self.exists = exists
        self.bucket_exists_calls = 0
        self.make_bucket_calls = 0

    def bucket_exists(self, _bucket: str) -> bool:
        self.bucket_exists_calls += 1
        return self.exists

    def make_bucket(self, _bucket: str) -> None:
        self.make_bucket_calls += 1


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        minio_endpoint="minio:9000",
        minio_access_key="access-key",
        minio_secure=False,
    )


def test_bucket_existence_is_reused_until_invalidated(monkeypatch) -> None:
    client = _BucketClient()
    bucket = "tenant-cache-test"
    monkeypatch.setattr(storage, "get_settings", _settings)
    storage._known_buckets.clear()

    storage._ensure_bucket(client, bucket)
    storage._ensure_bucket(client, bucket)

    assert client.bucket_exists_calls == 1
    assert client.make_bucket_calls == 0

    storage._forget_bucket(bucket)
    storage._ensure_bucket(client, bucket)

    assert client.bucket_exists_calls == 2


def test_missing_bucket_is_created_and_cached(monkeypatch) -> None:
    client = _BucketClient(exists=False)
    bucket = "tenant-cache-create-test"
    monkeypatch.setattr(storage, "get_settings", _settings)
    storage._known_buckets.clear()

    storage._ensure_bucket(client, bucket)
    storage._ensure_bucket(client, bucket)

    assert client.bucket_exists_calls == 1
    assert client.make_bucket_calls == 1


def test_bucket_creation_is_single_flight_under_concurrent_uploads(monkeypatch) -> None:
    client = _BucketClient(exists=False)
    bucket = "tenant-concurrent-create-test"
    monkeypatch.setattr(storage, "get_settings", _settings)
    storage._known_buckets.clear()

    original_bucket_exists = client.bucket_exists

    def slow_bucket_exists(name: str) -> bool:
        sleep(0.01)
        return original_bucket_exists(name)

    monkeypatch.setattr(client, "bucket_exists", slow_bucket_exists)
    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(lambda _: storage._ensure_bucket(client, bucket), range(32)))

    assert client.bucket_exists_calls == 1
    assert client.make_bucket_calls == 1
