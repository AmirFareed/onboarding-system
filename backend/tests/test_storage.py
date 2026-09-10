"""Unit tests for the filesystem storage backend."""

from pathlib import Path

import pytest

from app.database.models.enums import DocumentType
from app.upload.exceptions import StorageException
from app.upload.storage import StorageService

PDF_BYTES = b"%PDF-1.4\n%%EOF\n"


def test_save_writes_file_under_type_slug(tmp_path: Path):
    service = StorageService(tmp_path)
    relative = service.save(1, DocumentType.TRIPARTITE_AGREEMENT, PDF_BYTES, ".pdf")

    assert relative == f"applications/APP-000001/tripartite/{Path(relative).name}"
    target = tmp_path / "applications" / "APP-000001" / "tripartite"
    files = list(target.iterdir())
    assert len(files) == 1
    assert files[0].suffix == ".pdf"
    assert files[0].read_bytes() == PDF_BYTES


def test_save_uses_random_uuid_names(tmp_path: Path):
    service = StorageService(tmp_path)
    first = service.save(1, DocumentType.BILATERAL_AGREEMENT, b"a", ".pdf")
    second = service.save(1, DocumentType.BILATERAL_AGREEMENT, b"b", ".pdf")

    assert first != second


def test_save_creates_storage_root(tmp_path: Path):
    root = tmp_path / "nested" / "storage"
    service = StorageService(root)
    assert root.is_dir()


def test_resolve_round_trip(tmp_path: Path):
    service = StorageService(tmp_path)
    relative = service.save(1, DocumentType.TRIPARTITE_AGREEMENT, PDF_BYTES, ".pdf")
    resolved = service.resolve(relative)

    assert resolved == (tmp_path / relative).resolve()
    assert resolved.read_bytes() == PDF_BYTES


def test_resolve_rejects_absolute_path(tmp_path: Path):
    service = StorageService(tmp_path)
    with pytest.raises(StorageException):
        service.resolve(str(tmp_path / "anything"))


def test_resolve_rejects_empty_path(tmp_path: Path):
    service = StorageService(tmp_path)
    with pytest.raises(StorageException):
        service.resolve("")


def test_resolve_rejects_path_traversal(tmp_path: Path):
    service = StorageService(tmp_path)
    for traversal in ("../outside", "a/../../outside", "applications/../../../etc/passwd"):
        with pytest.raises(StorageException):
            service.resolve(traversal)


def test_delete_removes_file(tmp_path: Path):
    service = StorageService(tmp_path)
    relative = service.save(1, DocumentType.TRIPARTITE_AGREEMENT, PDF_BYTES, ".pdf")

    service.delete(relative)
    assert not (tmp_path / relative).exists()


def test_delete_missing_file_is_noop(tmp_path: Path):
    service = StorageService(tmp_path)
    service.delete("applications/APP-000001/tripartite/nope.pdf")


def test_delete_rejects_traversal(tmp_path: Path):
    service = StorageService(tmp_path)
    with pytest.raises(StorageException):
        service.delete("../../etc/passwd")
