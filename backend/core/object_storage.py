"""
core/object_storage.py

Permanent file storage behind one small interface, so upload workflows
don't care where bytes live:

  STORAGE_BACKEND=local     files under per-bucket local directories
                            (development / tests; Render's disk is NOT
                            permanent — never use this when hosted)
  STORAGE_BACKEND=supabase  private Supabase Storage buckets via the
                            Storage REST API, called server-side only with
                            SUPABASE_SERVICE_ROLE_KEY (never sent to the
                            browser)

Only object keys / metadata go in Postgres; bytes go to storage. Downloads
are always short-lived signed URLs handed out by backend endpoints that
check permissions first:
  - supabase: Supabase's own signed URL (expires after SIGNED_URL_TTL_SECONDS)
  - local:    an HMAC(SECRET_KEY)-signed URL to GET /api/v1/files/local/...
"""

import hashlib
import hmac
import logging
import re
import shutil
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Optional
from urllib.parse import quote

import httpx

from config.settings import settings

logger = logging.getLogger(__name__)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class ObjectStorageError(Exception):
    """Storage is unreachable or refused the operation (safe to show)."""


class ObjectNotFoundError(ObjectStorageError):
    pass


def safe_segment(value: str, max_len: int = 100) -> str:
    """One path segment: final component only, safe characters only."""
    base = (value or "").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _SAFE.sub("_", base).strip("._") or "file"
    return cleaned[-max_len:]


def unique_key(*prefix: str, filename: str) -> str:
    """e.g. unique_key("job_4", filename="cv.pdf") -> 'job_4/3f2a…_cv.pdf'."""
    parts = [safe_segment(p) for p in prefix if p]
    parts.append(f"{uuid.uuid4().hex}_{safe_segment(filename)}")
    return "/".join(parts)


class ObjectStorage(ABC):
    backend_name = "abstract"

    @abstractmethod
    def upload_file(self, bucket: str, key: str, source: Path, content_type: Optional[str] = None) -> None: ...

    def upload_bytes(self, bucket: str, key: str, data: bytes, content_type: Optional[str] = None) -> None:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(data)
            tmp_path = Path(tmp.name)
        try:
            self.upload_file(bucket, key, tmp_path, content_type)
        finally:
            tmp_path.unlink(missing_ok=True)

    @abstractmethod
    def download_to(self, bucket: str, key: str, dest: Path) -> None: ...

    @abstractmethod
    def delete(self, bucket: str, keys: list[str]) -> None: ...

    @abstractmethod
    def list(self, bucket: str, prefix: str = "") -> list[dict]:
        """[{"key": str, "updated_at": datetime}] — recursive under prefix."""

    @abstractmethod
    def signed_url(self, bucket: str, key: str, ttl_seconds: int) -> str: ...


# --------------------------------------------------------------------------- #
# Local (development / tests)
# --------------------------------------------------------------------------- #

def _local_signature(bucket: str, key: str, expires: int) -> str:
    msg = f"{bucket}\n{key}\n{expires}".encode()
    return hmac.new(settings.SECRET_KEY.encode(), msg, hashlib.sha256).hexdigest()


def verify_local_signature(bucket: str, key: str, expires: int, signature: str) -> bool:
    if expires < int(time.time()):
        return False
    return hmac.compare_digest(_local_signature(bucket, key, expires), signature or "")


class LocalObjectStorage(ObjectStorage):
    backend_name = "local"

    def __init__(self, bucket_dirs: dict[str, Path]):
        self.bucket_dirs = {b: Path(d).resolve() for b, d in bucket_dirs.items()}

    def path_for(self, bucket: str, key: str) -> Path:
        root = self.bucket_dirs.get(bucket)
        if root is None:
            raise ObjectStorageError(f"Unknown bucket {bucket!r}")
        candidate = (root / key).resolve()
        if root not in candidate.parents:
            raise ObjectStorageError("Object key escapes its bucket")
        return candidate

    def upload_file(self, bucket, key, source, content_type=None):
        dest = self.path_for(bucket, key)
        if dest.resolve() == Path(source).resolve():
            return  # already in place (meeting working copy == stored object)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)

    def download_to(self, bucket, key, dest):
        src = self.path_for(bucket, key)
        if not src.is_file():
            raise ObjectNotFoundError(key)
        if Path(dest).resolve() != src:
            Path(dest).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)

    def delete(self, bucket, keys):
        for key in keys:
            self.path_for(bucket, key).unlink(missing_ok=True)

    def list(self, bucket, prefix=""):
        root = self.bucket_dirs.get(bucket)
        if root is None or not root.exists():
            return []
        out = []
        for p in root.rglob("*"):
            if p.is_file():
                key = p.relative_to(root).as_posix()
                if key.startswith(prefix):
                    out.append({"key": key, "updated_at": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc)})
        return out

    def signed_url(self, bucket, key, ttl_seconds):
        if not self.path_for(bucket, key).is_file():  # also validates the key
            raise ObjectNotFoundError(key)
        expires = int(time.time()) + int(ttl_seconds)
        sig = _local_signature(bucket, key, expires)
        return f"/api/v1/files/local/{quote(bucket)}/{quote(key)}?expires={expires}&signature={sig}"


# --------------------------------------------------------------------------- #
# Supabase Storage (REST API, server-side only)
# --------------------------------------------------------------------------- #

class SupabaseObjectStorage(ObjectStorage):
    backend_name = "supabase"

    def __init__(self, url: str, service_key: str, client: Optional[httpx.Client] = None):
        self.base = url.rstrip("/") + "/storage/v1"
        self.client = client or httpx.Client(timeout=httpx.Timeout(30.0, read=300.0, write=300.0))
        self.headers = {"Authorization": f"Bearer {service_key}", "apikey": service_key}

    def _check(self, response: httpx.Response, action: str) -> httpx.Response:
        if response.status_code == 404 or (response.status_code == 400 and "not_found" in response.text.lower()):
            raise ObjectNotFoundError(action)
        if response.status_code >= 400:
            # Never echo the response body: it can contain internal detail.
            logger.warning("Supabase Storage %s failed: HTTP %s", action, response.status_code)
            raise ObjectStorageError(f"File storage is unavailable ({action} failed).")
        return response

    def _object_url(self, bucket: str, key: str) -> str:
        return f"{self.base}/object/{quote(bucket)}/{quote(key)}"

    def upload_file(self, bucket, key, source, content_type=None):
        headers = {**self.headers, "Content-Type": content_type or "application/octet-stream", "x-upsert": "false"}
        try:
            with open(source, "rb") as fh:
                resp = self.client.post(self._object_url(bucket, key), headers=headers, content=fh)
        except httpx.HTTPError as exc:
            raise ObjectStorageError("File storage is unreachable (upload failed).") from exc
        self._check(resp, "upload")

    def download_to(self, bucket, key, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with self.client.stream("GET", self._object_url(bucket, key), headers=self.headers) as resp:
                self._check(resp, "download")
                with open(tmp, "wb") as out:
                    for chunk in resp.iter_bytes():
                        out.write(chunk)
            tmp.replace(dest)
        except httpx.HTTPError as exc:
            raise ObjectStorageError("File storage is unreachable (download failed).") from exc
        finally:
            tmp.unlink(missing_ok=True)

    def delete(self, bucket, keys):
        if not keys:
            return
        try:
            resp = self.client.request("DELETE", f"{self.base}/object/{quote(bucket)}",
                                       headers=self.headers, json={"prefixes": list(keys)})
        except httpx.HTTPError as exc:
            raise ObjectStorageError("File storage is unreachable (delete failed).") from exc
        self._check(resp, "delete")

    def list(self, bucket, prefix=""):
        out: list[dict] = []
        folder = prefix.rstrip("/")
        offset = 0
        while True:
            try:
                resp = self.client.post(f"{self.base}/object/list/{quote(bucket)}", headers=self.headers,
                                        json={"prefix": folder, "limit": 1000, "offset": offset})
            except httpx.HTTPError as exc:
                raise ObjectStorageError("File storage is unreachable (list failed).") from exc
            entries = self._check(resp, "list").json()
            for e in entries:
                key = f"{folder}/{e['name']}" if folder else e["name"]
                if e.get("id") is None:  # a "folder" — Supabase lists one level at a time
                    out.extend(self.list(bucket, key + "/"))
                else:
                    stamp = e.get("updated_at") or e.get("created_at")
                    updated = datetime.fromisoformat(stamp.replace("Z", "+00:00")) if stamp else datetime.now(timezone.utc)
                    out.append({"key": key, "updated_at": updated})
            if len(entries) < 1000:
                return out
            offset += 1000

    def signed_url(self, bucket, key, ttl_seconds):
        try:
            resp = self.client.post(f"{self.base}/object/sign/{quote(bucket)}/{quote(key)}",
                                    headers=self.headers, json={"expiresIn": int(ttl_seconds)})
        except httpx.HTTPError as exc:
            raise ObjectStorageError("File storage is unreachable (signing failed).") from exc
        signed = self._check(resp, "sign").json().get("signedURL") or ""
        return signed if signed.startswith("http") else f"{self.base}{signed}"


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

_instance: Optional[ObjectStorage] = None


def local_bucket_dirs() -> dict[str, Path]:
    from modules.meeting_intelligence.config import meeting_settings
    from modules.recruitment.service import UPLOAD_DIR

    return {
        settings.STORAGE_BUCKET_MEETINGS: Path(meeting_settings.storage_path),
        settings.STORAGE_BUCKET_RESUMES: Path(UPLOAD_DIR),
    }


def get_object_storage() -> ObjectStorage:
    global _instance
    if _instance is None:
        if settings.STORAGE_BACKEND == "supabase":
            _instance = SupabaseObjectStorage(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        else:
            _instance = LocalObjectStorage(local_bucket_dirs())
    return _instance


def set_object_storage(storage: Optional[ObjectStorage]) -> None:
    """Swap the backend (tests)."""
    global _instance
    _instance = storage
