"""محدودیت‌های یکسان آپلود فایل در API."""

# پیوست درخواست‌ها (پرداخت، تنخواه، …)
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024  # 25 MB

# تصویر پروفایل
AVATAR_MAX_BYTES = 10 * 1024 * 1024  # 10 MB

ATTACHMENT_ALLOWED_EXTENSIONS = frozenset(
    {
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".heic",
        ".heif",
        ".gif",
        ".bmp",
        ".tif",
        ".tiff",
        ".zip",
    }
)

AVATAR_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".heif"})
