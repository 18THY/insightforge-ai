"""Storage and file validation engine for dataset uploads.

Handles file type validation, MIME type inspection, size checking,
filename sanitization, safe filesystem persistence, and file deletion.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from pathlib import Path
from uuid import UUID

from app.core.config import get_settings

# Allowed extensions and MIME types
ALLOWED_EXTENSIONS = {".csv", ".xlsx"}

CSV_MIME_TYPES = {
    "text/csv",
    "application/csv",
    "text/plain",
    "application/vnd.ms-excel",
    "application/octet-stream",
}

XLSX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",
    "application/zip",
    "application/octet-stream",
}

# Dangerous filename pattern
_UNSAFE_FILENAME_CHARS = re.compile(r"[^a-zA-Z0-9_.\- ]")


def sanitize_filename(filename: str) -> str:
    """Sanitize uploaded filename to prevent directory traversal and injection.

    - Removes directory separators and path components.
    - Removes null bytes and control characters.
    - Restricts characters to alphanumeric, underscore, dot, hyphen, space.
    - Limits length to 255 characters.
    """
    if not filename:
        return "unnamed_file"

    # Strip null bytes
    cleaned = filename.replace("\x00", "")

    # Strip any directory path components (both POSIX and Windows)
    cleaned = os.path.basename(cleaned)
    if "\\" in cleaned:
        cleaned = cleaned.split("\\")[-1]
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1]

    # Clean characters
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", cleaned).strip()

    # Prevent hidden files or relative paths
    cleaned = cleaned.lstrip(".")

    if not cleaned:
        cleaned = "unnamed_file"

    return cleaned[:255]


def get_file_extension(filename: str) -> str:
    """Extract lowercase file extension with dot (e.g. '.csv')."""
    return Path(filename).suffix.lower()


def validate_file_content(
    content: bytes,
    filename: str,
    content_type: str | None = None,
) -> tuple[str, int, int | None]:
    """Validate uploaded file content against size, type, and format rules.

    Args:
        content: Raw file bytes.
        filename: Original client filename.
        content_type: MIME type reported by the client (optional).

    Returns:
        tuple of (file_type, file_size, row_count) where file_type is 'csv' or 'xlsx'.

    Raises:
        ValueError: If validation fails for type, size, or content integrity.
    """
    settings = get_settings()

    # 1. Size check
    file_size = len(content)
    if file_size == 0:
        raise ValueError("Uploaded file is empty.")

    if file_size > settings.max_upload_size_bytes:
        max_mb = settings.max_upload_size_bytes / (1024 * 1024)
        raise ValueError(f"File size exceeds maximum allowed limit of {max_mb:.0f} MB.")

    # 2. Extension check
    ext = get_file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file format '{ext}'. Only CSV and XLSX files are supported."
        )

    file_type = ext.lstrip(".")
    row_count: int | None = None

    # 3. Content inspection by file type
    if file_type == "csv":
        if content_type and content_type.lower() not in CSV_MIME_TYPES:
            raise ValueError(f"Invalid MIME type '{content_type}' for CSV file.")

        # Check for null bytes (binary file disguised as CSV)
        if b"\x00" in content:
            raise ValueError("CSV file contains invalid binary characters or null bytes.")

        # Try decoding as UTF-8 or latin-1
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as e:
                raise ValueError(f"Unable to decode CSV file: {e}") from e

        # Count non-empty lines
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            raise ValueError("CSV file contains no readable data rows.")
        # Row count excluding header (minimum 0)
        row_count = max(0, len(lines) - 1)

    elif file_type == "xlsx":
        if content_type and content_type.lower() not in XLSX_MIME_TYPES:
            raise ValueError(f"Invalid MIME type '{content_type}' for XLSX file.")

        # XLSX must start with ZIP magic bytes 'PK\x03\x04'
        if not content.startswith(b"PK\x03\x04"):
            raise ValueError("Invalid XLSX file format: missing ZIP archive header.")

        # Verify it's a valid zip file containing Excel workbook parts
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                namelist = zf.namelist()
                if "[Content_Types].xml" not in namelist:
                    raise ValueError("Invalid XLSX file: missing [Content_Types].xml.")
                if not any(name.startswith("xl/") for name in namelist):
                    raise ValueError("Invalid XLSX file: missing Excel workbook components.")
        except zipfile.BadZipFile as e:
            raise ValueError("Corrupted or malformed XLSX file.") from e

        # Optional row counting using openpyxl in read-only mode
        try:
            import openpyxl

            wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            sheet = wb.active
            if sheet is not None:
                # Count rows with at least one non-None cell
                counted = 0
                for row in sheet.iter_rows(values_only=True):
                    if any(cell is not None for cell in row):
                        counted += 1
                row_count = max(0, counted - 1)
            wb.close()
        except Exception:
            # If counting fails, row_count remains None
            row_count = None

    return file_type, file_size, row_count


def get_upload_path(org_id: UUID, dataset_id: UUID, file_type: str) -> Path:
    """Generate the secure storage path for an uploaded dataset."""
    settings = get_settings()
    base_dir = Path(settings.upload_dir).resolve()
    org_dir = base_dir / str(org_id)
    return org_dir / f"{dataset_id}.{file_type}"


def save_upload_file(
    content: bytes,
    org_id: UUID,
    dataset_id: UUID,
    file_type: str,
) -> str:
    """Save upload content to the dedicated storage location.

    Returns:
        The normalized path string where the file is stored.
    """
    target_path = get_upload_path(org_id, dataset_id, file_type)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as f:
        f.write(content)

    return str(target_path)


def get_processed_path(org_id: UUID, dataset_id: UUID, file_type: str = "csv") -> Path:
    """Generate the secure storage path for a cleaned/processed dataset."""
    settings = get_settings()
    base_dir = Path(settings.processed_dir).resolve()
    org_dir = base_dir / str(org_id)
    return org_dir / f"{dataset_id}.{file_type}"


def save_processed_file(
    content: bytes,
    org_id: UUID,
    dataset_id: UUID,
    file_type: str = "csv",
) -> str:
    """Save cleaned dataset to the dedicated processed storage location.

    Returns:
        The normalized path string where the processed file is stored.
    """
    target_path = get_processed_path(org_id, dataset_id, file_type)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    with open(target_path, "wb") as f:
        f.write(content)

    return str(target_path)


def delete_stored_file(storage_path: str | None) -> bool:
    """Delete a stored file from disk if it exists.

    Returns True if file was deleted, False if file did not exist.
    """
    if not storage_path:
        return False

    try:
        p = Path(storage_path)
        if p.exists() and p.is_file():
            p.unlink()
            return True
    except Exception:
        pass
    return False


def validate_path_containment(path: Path | str, expected_parent_dir: Path | str) -> Path:
    """Validate that path resolves strictly inside expected_parent_dir.

    Raises:
        ValueError: If the path traverses outside the expected parent directory.
    """
    resolved_path = Path(path).resolve()
    resolved_parent = Path(expected_parent_dir).resolve()
    try:
        resolved_path.relative_to(resolved_parent)
    except ValueError:
        raise ValueError(
            f"Path traversal or unsafe path detected: '{path}' is not within '{expected_parent_dir}'"
        )
    return resolved_path

