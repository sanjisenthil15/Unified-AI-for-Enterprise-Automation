"""
modules/files/router.py

Serves files for signed links issued in STORAGE_BACKEND=local mode
(development). The link itself is the credential: an HMAC(SECRET_KEY)
over bucket, key and expiry, issued only by endpoints that already checked
the caller's permissions, and valid for SIGNED_URL_TTL_SECONDS. In
supabase mode this route is disabled — Supabase serves its own signed URLs.

    GET /files/local/{bucket}/{key}?expires=<unix>&signature=<hex>
"""

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from config.settings import settings
from core.object_storage import LocalObjectStorage, ObjectStorageError, get_object_storage, verify_local_signature

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("/local/{bucket}/{key:path}", summary="Download via a short-lived signed link (local storage mode)")
def download_local_file(
    bucket: str,
    key: str,
    expires: int = Query(...),
    signature: str = Query(..., min_length=64, max_length=64),
):
    storage = get_object_storage()
    if settings.STORAGE_BACKEND != "local" or not isinstance(storage, LocalObjectStorage):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    if not verify_local_signature(bucket, key, expires, signature):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This download link is invalid or has expired.")
    try:
        path = storage.path_for(bucket, key)
    except ObjectStorageError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found.")
    return FileResponse(path, filename=path.name.split("_", 1)[-1])
