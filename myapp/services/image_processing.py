"""Image preparation helpers for medicine uploads."""

from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile


MAX_IMAGE_SIZE = (1600, 1600)
JPEG_QUALITY = 82


def _compressed_name(original_name):
    stem = Path(original_name or "medicine").stem or "medicine"
    return f"{stem}.jpg"


def compress_uploaded_image(image):
    """Resize and compress a user-uploaded medicine image for storage.

    This prepares a consistent image file that can later be reused by Gemini OCR
    without calling any OCR or AI service now.
    """
    if not image:
        return image

    from PIL import Image, ImageOps

    image.seek(0)
    with Image.open(image) as opened:
        opened = ImageOps.exif_transpose(opened)
        opened.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)

        if opened.mode not in ("RGB", "L"):
            opened = opened.convert("RGB")

        output = BytesIO()
        opened.save(output, format="JPEG", quality=JPEG_QUALITY, optimize=True)

    compressed = ContentFile(output.getvalue())
    compressed.name = _compressed_name(getattr(image, "name", "medicine"))
    return compressed
