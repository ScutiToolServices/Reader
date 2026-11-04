"""Stable, coded failures. Messages are safe to show a user: no paths, no secrets."""


class OCRError(Exception):
    code = "ocr_error"


class DocumentRejected(OCRError):
    code = "document_rejected"


class FileNotFound(OCRError):
    code = "file_not_found"


class QuotaExceeded(OCRError):
    code = "quota_exceeded"


class EngineFailed(OCRError):
    code = "engine_failed"


class IdentityRequired(OCRError):
    code = "identity_required"
