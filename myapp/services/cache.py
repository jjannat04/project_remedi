"""Small cache wrappers for low-cost computed values."""

import hashlib

from django.core.cache import cache


OCR_CACHE_PREFIX = "ocr:image:"
OCR_CACHE_TIMEOUT_SECONDS = 60 * 60 * 24


def read_file_bytes(file_obj):
    position = None
    if hasattr(file_obj, "tell"):
        try:
            position = file_obj.tell()
        except (OSError, ValueError):
            position = None

    if hasattr(file_obj, "seek"):
        file_obj.seek(0)
    data = file_obj.read()
    if hasattr(file_obj, "seek") and position is not None:
        file_obj.seek(position)
    return data


def hash_uploaded_file(file_obj):
    return hashlib.sha256(read_file_bytes(file_obj)).hexdigest()


def get_cached_ocr_result(image_hash):
    result = cache.get(f"{OCR_CACHE_PREFIX}{image_hash}")
    return result.copy() if result else None


def set_cached_ocr_result(image_hash, result):
    cache.set(f"{OCR_CACHE_PREFIX}{image_hash}", result.copy(), OCR_CACHE_TIMEOUT_SECONDS)
