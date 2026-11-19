import asyncio
import datetime
import hashlib
import json
import logging
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from fastapi.templating import Jinja2Templates
import tempfile
import zipfile
from starlette.background import BackgroundTask

from app.config import settings
from app.i18n import detect_locale, get_translations, SUPPORTED_LOCALES
from app.security import (
    create_session_token,
    generate_pin,
    hash_pin,
    verify_pin,
    verify_session_token,
)
from app.storage import (
    cleanup_expired_uploads,
    format_size,
    get_upload_dir,
    is_expired,
    is_locked,
    load_metadata,
    record_failed_attempt,
    reset_failed_attempts,
    save_metadata,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("file_server")

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Background TTL cleanup loop
async def background_cleanup_loop():
    while True:
        try:
            removed = cleanup_expired_uploads()
            if removed > 0:
                logger.info(f"Background cleanup removed {removed} expired upload(s)")
        except Exception as e:
            logger.error(f"Error in background cleanup: {e}")
        await asyncio.sleep(settings.CLEANUP_INTERVAL_MINUTES * 60)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure data dirs exist
    (Path(settings.DATA_DIR) / "uploads").mkdir(parents=True, exist_ok=True)
    cleanup_task = asyncio.create_task(background_cleanup_loop())
    logger.info("File server initialized and background cleaner started")
    yield
    cleanup_task.cancel()

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
@app.get(f"{settings.URL_PREFIX}/health")
def health_check():
    return {"status": "healthy", "service": "file-server"}

# -----------------------------------------------------------------------------
# Upload Endpoint (API for Bulwark / Web Upload)
# -----------------------------------------------------------------------------
@app.post("/api/upload")
@app.post(f"{settings.URL_PREFIX}/api/upload")
async def api_upload(
    request: Request,
    files: list[UploadFile] = File(...),
    pin: Annotated[str | None, Form()] = None,
    ttl_days: Annotated[int | None, Form()] = None,
):
    # Verify API Key if configured (protects server from unauthorized abuse)
    if settings.API_KEY:
        auth_header = (
            request.headers.get("X-API-Key")
            or request.headers.get("Authorization")
            or ""
        )
        token = auth_header.strip()
        if token.lower().startswith("bearer "):
            token = token[7:].strip()
        if not token or not secrets.compare_digest(token, settings.API_KEY.strip()):
            client_ip = request.client.host if request.client else "unknown"
            logger.warning(f"Unauthorized upload attempt from {client_ip}")
            raise HTTPException(
                status_code=401,
                detail="Access denied. Invalid or missing API key.",
            )

    if not files:
        raise HTTPException(status_code=400, detail="No files selected for upload.")

    if len(files) > settings.MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=400,
            detail=f"Exceeded maximum number of files ({settings.MAX_UPLOAD_FILES}).",
        )

    # Resolve TTL
    if ttl_days is None or ttl_days <= 0 or ttl_days > settings.MAX_TTL_DAYS:
        ttl_days = settings.DEFAULT_TTL_DAYS

    # Generate 32-character hex Upload ID
    upload_id = secrets.token_hex(16)
    upload_dir = get_upload_dir(upload_id)
    files_dir = upload_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    # Resolve PIN (if not provided, generate 6-digit random PIN)
    pin_clean = (pin or "").strip()
    if not pin_clean:
        pin_clean = generate_pin()

    pin_hash_val, pin_salt_val = hash_pin(pin_clean)

    saved_files = []
    total_size = 0

    for idx, file in enumerate(files):
        # Sanitize filename
        safe_name = Path(file.filename or f"file_{idx + 1}").name
        file_id = f"f_{idx + 1}"
        file_path = files_dir / file_id

        hasher = hashlib.sha256()
        file_size = 0

        # Save chunk by chunk
        with open(file_path, "wb") as out_f:
            while chunk := await file.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                if file_size > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                    # Clean up
                    delete_upload(upload_id)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File {safe_name} exceeds the maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB.",
                    )
                hasher.update(chunk)
                out_f.write(chunk)

        total_size += file_size
        saved_files.append(
            {
                "id": file_id,
                "name": safe_name,
                "size": file_size,
                "formatted_size": format_size(file_size),
                "sha256": hasher.hexdigest(),
                "content_type": file.content_type or "application/octet-stream",
            }
        )

    now = int(time.time())
    expires_at = now + (ttl_days * 86400)

    meta = {
        "upload_id": upload_id,
        "created_at": now,
        "expires_at": expires_at,
        "ttl_days": ttl_days,
        "pin_hash": pin_hash_val,
        "pin_salt": pin_salt_val,
        "failed_attempts": 0,
        "locked_until": 0,
        "total_size": total_size,
        "files": saved_files,
    }

    await save_metadata(upload_id, meta)

    # Build public URL
    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    if not base_url:
        # Use host header from request
        proto = request.headers.get("x-forwarded-proto", request.url.scheme)
        host = request.headers.get("x-forwarded-host", request.headers.get("host", "localhost"))
        base_url = f"{proto}://{host}"

    public_url = f"{base_url}{settings.URL_PREFIX}/{upload_id}"
    expires_dt = datetime.datetime.fromtimestamp(expires_at, tz=datetime.timezone.utc)

    logger.info(
        f"Uploaded bundle {upload_id}: {len(saved_files)} files, "
        f"{format_size(total_size)}, PIN={pin_clean}, TTL={ttl_days}d"
    )

    return {
        "success": True,
        "upload_id": upload_id,
        "url": public_url,
        "pin": pin_clean,
        "created_at": datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc).isoformat(),
        "expires_at": expires_dt.isoformat(),
        "ttl_days": ttl_days,
        "total_size": total_size,
        "formatted_size": format_size(total_size),
        "files_count": len(saved_files),
        "files": saved_files,
    }

# -----------------------------------------------------------------------------
# Web UI & Download Routes
# -----------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get(f"{settings.URL_PREFIX}/", response_class=HTMLResponse)
@app.get(f"{settings.URL_PREFIX}", response_class=HTMLResponse)
def index_info_page(request: Request):
    t = get_translations(request)
    locale = detect_locale(request)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "prefix": settings.URL_PREFIX,
            "app_name": settings.APP_NAME,
            "t": t,
            "locale": locale,
        },
    )

@app.get(f"{settings.URL_PREFIX}/{{upload_id}}", response_class=HTMLResponse)
async def view_download_page(request: Request, upload_id: str):
    t = get_translations(request)
    locale = detect_locale(request)
    meta = await load_metadata(upload_id)
    if not meta or is_expired(meta):
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "prefix": settings.URL_PREFIX,
                "t": t,
                "locale": locale,
                "title": t["error_not_found_title"],
                "message": t["error_not_found_desc"],
            },
            status_code=404,
        )

    # Check lock
    if is_locked(meta):
        rem_min = max(1, int((meta["locked_until"] - time.time()) / 60))
        return templates.TemplateResponse(
            request=request,
            name="download.html",
            context={
                "upload_id": upload_id,
                "prefix": settings.URL_PREFIX,
                "t": t,
                "locale": locale,
                "is_authenticated": False,
                "error": t("error_locked", minutes=rem_min),
            },
        )

    # Check session cookie
    token = request.cookies.get(f"{settings.SESSION_COOKIE_NAME}_{upload_id}")
    is_authed = False
    if token and verify_session_token(token, upload_id):
        is_authed = True

    expires_dt = datetime.datetime.fromtimestamp(meta["expires_at"])
    expires_str = expires_dt.strftime("%d.%m.%Y, %H:%M UTC")

    return templates.TemplateResponse(
        request=request,
        name="download.html",
        context={
            "upload_id": upload_id,
            "prefix": settings.URL_PREFIX,
            "t": t,
            "locale": locale,
            "is_authenticated": is_authed,
            "files": meta.get("files", []),
            "total_size_formatted": format_size(meta.get("total_size", 0)),
            "expires_date_str": expires_str,
            "error": None,
        },
    )

@app.post(f"{settings.URL_PREFIX}/{{upload_id}}/auth")
async def verify_download_pin(
    request: Request,
    response: Response,
    upload_id: str,
    pin: Annotated[str, Form()],
):
    t = get_translations(request)
    locale = detect_locale(request)
    meta = await load_metadata(upload_id)
    if not meta or is_expired(meta):
        raise HTTPException(status_code=404, detail=t["error_not_found_title"])

    if is_locked(meta):
        rem_min = max(1, int((meta["locked_until"] - time.time()) / 60))
        return templates.TemplateResponse(
            request=request,
            name="download.html",
            context={
                "upload_id": upload_id,
                "prefix": settings.URL_PREFIX,
                "t": t,
                "locale": locale,
                "is_authenticated": False,
                "error": t("error_locked", minutes=rem_min),
            },
            status_code=403,
        )

    pin_clean = pin.strip()
    if verify_pin(pin_clean, meta["pin_hash"], meta["pin_salt"]):
        await reset_failed_attempts(upload_id, meta)
        # Create session token
        token = create_session_token(upload_id)
        # Preserve lang query param if present
        target_url = f"{settings.URL_PREFIX}/{upload_id}"
        if request.query_params.get("lang"):
            target_url += f"?lang={request.query_params.get('lang')}"
        redirect_res = RedirectResponse(
            url=target_url,
            status_code=status.HTTP_303_SEE_OTHER,
        )
        redirect_res.set_cookie(
            key=f"{settings.SESSION_COOKIE_NAME}_{upload_id}",
            value=token,
            max_age=settings.SESSION_MAX_AGE_HOURS * 3600,
            httponly=True,
            samesite="lax",
        )
        return redirect_res
    else:
        attempts = await record_failed_attempt(upload_id, meta)
        rem_attempts = max(0, settings.RATE_LIMIT_ATTEMPTS - attempts)
        if rem_attempts == 0:
            error_msg = t("error_locked", minutes=settings.RATE_LIMIT_LOCKOUT_MINUTES)
        else:
            error_msg = t["error_invalid_pin"]

        return templates.TemplateResponse(
            request=request,
            name="download.html",
            context={
                "upload_id": upload_id,
                "prefix": settings.URL_PREFIX,
                "t": t,
                "locale": locale,
                "is_authenticated": False,
                "error": error_msg,
            },
            status_code=401,
        )

# -----------------------------------------------------------------------------
# File Download Endpoints
# -----------------------------------------------------------------------------
@app.get(f"{settings.URL_PREFIX}/{{upload_id}}/download/{{file_id}}")
async def download_file(request: Request, upload_id: str, file_id: str):
    meta = await load_metadata(upload_id)
    if not meta or is_expired(meta):
        raise HTTPException(status_code=404, detail="Файл не найден")

    # Verify session
    token = request.cookies.get(f"{settings.SESSION_COOKIE_NAME}_{upload_id}")
    if not token or not verify_session_token(token, upload_id):
        return RedirectResponse(url=f"{settings.URL_PREFIX}/{upload_id}")

    target_file = None
    for f in meta.get("files", []):
        if f["id"] == file_id:
            target_file = f
            break

    if not target_file:
        raise HTTPException(status_code=404, detail="File not found in bundle.")

    file_path = get_upload_dir(upload_id) / "files" / file_id
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on storage.")

    return FileResponse(
        path=file_path,
        filename=target_file["name"],
        media_type=target_file.get("content_type", "application/octet-stream"),
    )

@app.get(f"{settings.URL_PREFIX}/{{upload_id}}/download-all")
async def download_all_zip(request: Request, upload_id: str):
    meta = await load_metadata(upload_id)
    if not meta or is_expired(meta):
        raise HTTPException(status_code=404, detail="Файлы не найдены")

    # Verify session
    token = request.cookies.get(f"{settings.SESSION_COOKIE_NAME}_{upload_id}")
    if not token or not verify_session_token(token, upload_id):
        return RedirectResponse(url=f"{settings.URL_PREFIX}/{upload_id}")

    files = meta.get("files", [])
    if not files:
        raise HTTPException(status_code=404, detail="No files in bundle.")

    files_dir = get_upload_dir(upload_id) / "files"

    tmp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    tmp_zip.close()

    try:
        with zipfile.ZipFile(tmp_zip.name, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in files:
                path = files_dir / f["id"]
                if path.exists():
                    zf.write(path, arcname=f["name"])
    except Exception as e:
        if os.path.exists(tmp_zip.name):
            os.unlink(tmp_zip.name)
        logger.error(f"Failed to create ZIP for {upload_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to create archive.")

    zip_filename = f"files_{upload_id[:8]}.zip"
    return FileResponse(
        path=tmp_zip.name,
        filename=zip_filename,
        media_type="application/zip",
        background=BackgroundTask(lambda: os.unlink(tmp_zip.name) if os.path.exists(tmp_zip.name) else None),
    )
