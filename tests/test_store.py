import pytest

from src.errors import QuotaExceeded
from src.store import DocumentStore


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def make(tmp_path, ttl=100, quota=1000):
    clock = Clock()
    return DocumentStore(tmp_path, ttl, quota, clock), clock


def test_id_is_stable_and_owner_specific():
    assert DocumentStore.file_id("ann", b"x") == DocumentStore.file_id("ann", b"x")
    assert DocumentStore.file_id("ann", b"x") != DocumentStore.file_id("bob", b"x")
    assert len(DocumentStore.file_id("ann", b"x")) == 32


def test_put_then_get(tmp_path):
    store, _ = make(tmp_path)
    fid = DocumentStore.file_id("ann", b"abc")
    stored = store.put("ann", fid, b"abc", "a.pdf", 3)
    got = store.get("ann", fid)
    assert got == stored and got.page_count == 3 and got.filename == "a.pdf" and got.path.read_bytes() == b"abc"


def test_a_document_is_private_to_its_owner_and_a_bad_id_finds_nothing(tmp_path):
    store, _ = make(tmp_path)
    fid = DocumentStore.file_id("ann", b"abc")
    store.put("ann", fid, b"abc", "a.pdf", 1)
    assert store.get("bob", fid) is None
    assert store.get("ann", "../../etc/passwd") is None


def test_expiry_removes_the_document_and_its_result(tmp_path):
    store, clock = make(tmp_path, ttl=100)
    fid = DocumentStore.file_id("ann", b"abc")
    store.put("ann", fid, b"abc", "a.pdf", 1)
    store.put_result("ann", fid, "sig", {"text": "t"})
    clock.now += 101
    assert store.get("ann", fid) is None
    assert not list(tmp_path.rglob("*.bin")) and not list(tmp_path.rglob("*.json"))


def test_quota_is_per_owner(tmp_path):
    store, _ = make(tmp_path, quota=10)
    store.put("ann", DocumentStore.file_id("ann", b"12345678"), b"12345678", "a.pdf", 1)
    with pytest.raises(QuotaExceeded):
        store.put("ann", DocumentStore.file_id("ann", b"123"), b"123", "b.pdf", 1)
    store.put("bob", DocumentStore.file_id("bob", b"12345678"), b"12345678", "a.pdf", 1)


def test_a_result_is_kept_only_for_the_same_signature(tmp_path):
    store, _ = make(tmp_path)
    fid = DocumentStore.file_id("ann", b"abc")
    store.put("ann", fid, b"abc", "a.pdf", 1)
    store.put_result("ann", fid, "model|300", {"text": "t", "pages": ["t"], "page_count": 1})
    assert store.get_result("ann", fid, "model|300")["text"] == "t"
    assert store.get_result("ann", fid, "model|150") is None
    assert store.get_result("ann", "not-an-id", "model|300") is None
