import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Any
import aiofiles
from app.config import settings

logger = logging.getLogger("file_server.storage")

def get_upload_dir(upload_id: str) -> Path:
    return Path(settings.DATA_DIR) / "uploads" / upload_id

def format_size(size_bytes: int) -> str:
    """Format bytes into human-readable string (KB, MB, GB)."""
    if size_bytes < 1024:
        return f"{size_bytes} Б"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} КБ"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} МБ"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} ГБ"

async def save_metadata(upload_id: str, data: dict[str, Any]) -> None:
    upload_dir = get_upload_dir(upload_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    meta_path = upload_dir / "meta.json"
    temp_path = upload_dir / "meta.json.tmp"
    async with aiofiles.open(temp_path, "w", encoding="utf-8") as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    os.replace(temp_path, meta_path)

async def load_metadata(upload_id: str) -> dict[str, Any] | None:
    meta_path = get_upload_dir(upload_id) / "meta.json"
    if not meta_path.exists():
        return None
    try:
        async with aiofiles.open(meta_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return json.loads(content)
    except Exception as e:
        logger.error(f"Error reading metadata for {upload_id}: {e}")
        return None

def is_expired(meta: dict[str, Any]) -> bool:
    return time.time() > meta.get("expires_at", 0)

def is_locked(meta: dict[str, Any]) -> bool:
    return time.time() < meta.get("locked_until", 0)

async def record_failed_attempt(upload_id: str, meta: dict[str, Any]) -> int:
    """Record a failed PIN attempt and lock if threshold exceeded."""
    attempts = meta.get("failed_attempts", 0) + 1
    meta["failed_attempts"] = attempts
    if attempts >= settings.RATE_LIMIT_ATTEMPTS:
        meta["locked_until"] = int(time.time() + settings.RATE_LIMIT_LOCKOUT_MINUTES * 60)
        logger.warning(f"Upload {upload_id} locked due to {attempts} failed attempts")
    await save_metadata(upload_id, meta)
    return attempts

async def reset_failed_attempts(upload_id: str, meta: dict[str, Any]) -> None:
    if meta.get("failed_attempts", 0) > 0 or meta.get("locked_until", 0) > 0:
        meta["failed_attempts"] = 0
        meta["locked_until"] = 0
        await save_metadata(upload_id, meta)

def delete_upload(upload_id: str) -> None:
    upload_dir = get_upload_dir(upload_id)
    if upload_dir.exists():
        try:
            shutil.rmtree(upload_dir)
            logger.info(f"Deleted expired/removed upload: {upload_id}")
        except Exception as e:
            logger.error(f"Failed to delete upload {upload_id}: {e}")

def cleanup_expired_uploads() -> int:
    """Scan all uploads and remove those past their TTL."""
    base_dir = Path(settings.DATA_DIR) / "uploads"
    if not base_dir.exists():
        return 0
    
    removed = 0
    now = time.time()
    for item in base_dir.iterdir():
        if item.is_dir():
            meta_path = item / "meta.json"
            if meta_path.exists():
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    if now > meta.get("expires_at", 0):
                        shutil.rmtree(item)
                        removed += 1
                        logger.info(f"Cleaned up expired upload: {item.name}")
                except Exception as e:
                    logger.error(f"Error checking {item.name}: {e}")
            else:
                # Orphaned directory older than 24h
                if now - item.stat().st_mtime > 86400:
                    shutil.rmtree(item, ignore_errors=True)
                    removed += 1
    return removed
