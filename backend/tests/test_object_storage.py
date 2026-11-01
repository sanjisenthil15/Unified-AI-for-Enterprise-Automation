"""Permanent file storage: resumes and meeting recordings in object storage,
signed downloads with RBAC, failure handling, orphan cleanup, and the
Supabase Storage REST client (against a mocked HTTP transport — no real
credentials or buckets are used)."""
import io
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

from config.database import SessionLocal
from config.settings import settings
from core import object_storage as obj
from models.meeting import Meeting
from models.resume import Resume
from modules.files.cleanup import delete_orphans, find_orphans
from modules.meeting_intelligence import storage as meeting_storage
from modules.meeting_intelligence.storage import ObjectBackedMeetingVideoStorage, StorageUnavailableError
from modules.recruitment import service as recruitment_service

PDF = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF"
FAKE_MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 2048


class FakeObjectStorage(obj.ObjectStorage):
    """In-memory stand-in for Supabase Storage."""
    backend_name = "fake"

    def __init__(self, fail_uploads=False):
        self.objects: dict[tuple[str, str], tuple[bytes, datetime]] = {}
        self.fail_uploads = fail_uploads

    def upload_file(self, bucket, key, source, content_type=None):
        if self.fail_uploads:
            raise obj.ObjectStorageError("File storage is unreachable (upload failed).")
        self.objects[(bucket, key)] = (Path(source).read_bytes(), datetime.now(timezone.utc))

    def download_to(self, bucket, key, dest):
        if (bucket, key) not in self.objects:
            raise obj.ObjectNotFoundError(key)
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(self.objects[(bucket, key)][0])

    def delete(self, bucket, keys):
        for k in keys:
            self.objects.pop((bucket, k), None)

    def list(self, bucket, prefix=""):
        return [{"key": k, "updated_at": t} for (b, k), (_, t) in self.objects.items() if b == bucket and k.startswith(prefix)]

    def signed_url(self, bucket, key, ttl_seconds):
        if (bucket, key) not in self.objects:
            raise obj.ObjectNotFoundError(key)
        return f"https://storage.example/signed/{bucket}/{key}?ttl={ttl_seconds}"

    def keys(self, bucket):
        return sorted(k for (b, k) in self.objects if b == bucket)


@pytest.fixture
def fake_storage():
    fake = FakeObjectStorage()
    obj.set_object_storage(fake)
    yield fake
    obj.set_object_storage(None)


def _job(client, headers):
    r = client.post("/api/v1/recruitment/jobs", headers=headers, json={
        "title": "Storage Test Role", "description": "Object storage regression.", "required_skills": "python",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _upload_resume(client, headers, job_id, data=PDF, name="cv.pdf"):
    return client.post(f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=headers,
                       data={"candidate_name": "Storage Candidate"},
                       files={"resume_file": (name, io.BytesIO(data), "application/pdf")})


def _resume_row(resume_id):
    db = SessionLocal()
    try:
        return db.get(Resume, resume_id)
    finally:
        db.close()


# ------------------------------------------------------------------ resumes

def test_resume_upload_stores_bytes_in_bucket_and_only_reference_in_db(client, new_user, fake_storage):
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    r = _upload_resume(client, recruiter["headers"], job_id, name="../../Jane CV.pdf")
    assert r.status_code in (200, 201), r.text
    row = _resume_row(r.json()["id"])
    bucket, key = recruitment_service.resume_object_ref(row.file_path)
    assert bucket == settings.STORAGE_BUCKET_RESUMES
    assert key.startswith(f"job_{job_id}/") and ".." not in key and key.endswith("_Jane_CV.pdf")
    assert fake_storage.objects[(bucket, key)][0] == PDF
    assert row.extracted_text is not None  # text is still extracted into the DB


def test_resume_download_url_is_signed_and_restricted(client, new_user, fake_storage):
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    resume_id = _upload_resume(client, recruiter["headers"], job_id).json()["id"]
    url = f"/api/v1/recruitment/resumes/{resume_id}/download-url"

    for role in ("recruiter", "hr_manager", "admin"):
        who = recruiter if role == "recruiter" else new_user(f"R {role}", role=role)
        r = client.get(url, headers=who["headers"])
        assert r.status_code == 200, (role, r.text)
        assert r.json()["url"].startswith("https://storage.example/signed/recruitment-resumes/")
        assert r.json()["expires_in"] == settings.SIGNED_URL_TTL_SECONDS
    for role in ("employee", "viewer", "manager", "support_agent"):
        assert client.get(url, headers=new_user(f"R {role}", role=role)["headers"]).status_code == 403, role


def test_invalid_and_oversized_resumes_store_nothing(client, new_user, fake_storage):
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    assert _upload_resume(client, recruiter["headers"], job_id, data=b"not a pdf").status_code == 422
    big = PDF + b"0" * (recruitment_service.MAX_RESUME_BYTES + 1)
    assert _upload_resume(client, recruiter["headers"], job_id, data=big).status_code == 422
    assert _upload_resume(client, recruiter["headers"], job_id, name="cv.exe").status_code == 422
    assert fake_storage.keys(settings.STORAGE_BUCKET_RESUMES) == []


def test_storage_outage_creates_no_resume_record(client, new_user):
    obj.set_object_storage(FakeObjectStorage(fail_uploads=True))
    try:
        recruiter = new_user("Storage Recruiter", role="recruiter")
        job_id = _job(client, recruiter["headers"])
        r = _upload_resume(client, recruiter["headers"], job_id)
        assert r.status_code == 503 and "unreachable" in r.text
        listed = client.get(f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=recruiter["headers"]).json()
        assert listed == []
        bulk = client.post(f"/api/v1/recruitment/jobs/{job_id}/resumes/bulk", headers=recruiter["headers"],
                           files=[("files", ("a.pdf", io.BytesIO(PDF), "application/pdf"))]).json()
        assert bulk["files"][0]["status"] == "error"
        assert client.get(f"/api/v1/recruitment/jobs/{job_id}/resumes", headers=recruiter["headers"]).json() == []
    finally:
        obj.set_object_storage(None)


def test_database_failure_after_upload_removes_the_object(client, new_user, fake_storage, monkeypatch):
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    real_resume = recruitment_service.Resume

    def broken_row(**kwargs):
        kwargs["job_posting_id"] = 2_000_000_000  # FK violation at commit
        return real_resume(**kwargs)

    monkeypatch.setattr(recruitment_service, "Resume", broken_row)
    with pytest.raises(Exception):
        _upload_resume(client, recruiter["headers"], job_id)
    monkeypatch.undo()
    assert fake_storage.keys(settings.STORAGE_BUCKET_RESUMES) == []


def test_deleting_a_resume_deletes_its_object(client, new_user, fake_storage):
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    resume_id = _upload_resume(client, recruiter["headers"], job_id).json()["id"]
    assert len(fake_storage.keys(settings.STORAGE_BUCKET_RESUMES)) == 1
    assert client.delete(f"/api/v1/recruitment/resumes/{resume_id}", headers=recruiter["headers"]).status_code in (200, 204)
    assert fake_storage.keys(settings.STORAGE_BUCKET_RESUMES) == []


def test_local_signed_links_serve_the_file_and_reject_tampering(client, new_user):
    obj.set_object_storage(None)  # the real local backend
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    resume_id = _upload_resume(client, recruiter["headers"], job_id).json()["id"]
    link = client.get(f"/api/v1/recruitment/resumes/{resume_id}/download-url", headers=recruiter["headers"]).json()["url"]
    assert link.startswith("/api/v1/files/local/recruitment-resumes/")

    r = client.get(link)  # the signature is the credential — no JWT needed
    assert r.status_code == 200 and r.content == PDF
    tampered = link[:-1] + ("0" if link[-1] != "0" else "1")
    assert client.get(tampered).status_code == 403
    path, _, query = link.partition("?")
    params = dict(p.split("=", 1) for p in query.split("&"))
    expired = f"{path}?expires={int(time.time()) - 10}&signature={params['signature']}"
    assert client.get(expired).status_code == 403
    other_key = link.replace("job_", "job_9", 1)
    assert client.get(other_key).status_code == 403
    client.delete(f"/api/v1/recruitment/resumes/{resume_id}", headers=recruiter["headers"])


def test_legacy_local_resume_rows_are_not_broken(client, new_user, fake_storage):
    """Rows from before object storage keep their disk path; with cloud
    storage on they report a clear 404 instead of crashing."""
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    db = SessionLocal()
    try:
        row = Resume(job_posting_id=job_id, candidate_name="Legacy", file_name="old.pdf",
                     file_path="C:/old-server/uploads/resumes/abc_old.pdf", extracted_text="text", status="extracted")
        db.add(row)
        db.commit()
        rid = row.id
    finally:
        db.close()
    r = client.get(f"/api/v1/recruitment/resumes/{rid}/download-url", headers=recruiter["headers"])
    assert r.status_code == 404 and "no longer available" in r.json()["detail"]
    assert client.get(f"/api/v1/recruitment/resumes/{rid}", headers=recruiter["headers"]).status_code == 200


# ------------------------------------------------------------------ meetings

def _video_upload(name="meeting.mp4"):
    return UploadFile(file=io.BytesIO(FAKE_MP4), filename=name, headers=Headers({"content-type": "video/mp4"}))


@pytest.fixture
def cloud_meeting_storage(tmp_path):
    fake = FakeObjectStorage()
    store = ObjectBackedMeetingVideoStorage(
        tmp_path / "meetings", allowed_extensions={".mp4", ".webm"}, max_bytes=5 * 1024 * 1024,
        object_storage=fake, bucket=settings.STORAGE_BUCKET_MEETINGS,
    )
    return store, fake


def test_meeting_recording_is_kept_permanently_and_restored_after_restart(cloud_meeting_storage):
    store, fake = cloud_meeting_storage
    stored = store.save_video(77, fileobj=io.BytesIO(FAKE_MP4), original_filename="sync.mp4", content_type="video/mp4")
    key = stored.relative_path
    assert fake.keys(settings.STORAGE_BUCKET_MEETINGS) == [key]          # one permanent copy, same key as the DB path
    Path(stored.absolute_path).unlink()                                   # Render restart wipes the disk
    restored = store.resolve(key)
    assert restored.is_file() and restored.read_bytes() == FAKE_MP4      # pipeline gets a real file again
    assert store.resolve("77/audio.wav").name == "audio.wav"              # derived files: no error, regenerated later
    store.delete_meeting_files(77)
    assert fake.keys(settings.STORAGE_BUCKET_MEETINGS) == []


def test_meeting_storage_outage_keeps_nothing(cloud_meeting_storage, meeting_owner):
    store, fake = cloud_meeting_storage
    fake.fail_uploads = True
    with pytest.raises(StorageUnavailableError):
        store.save_video(78, fileobj=io.BytesIO(FAKE_MP4), original_filename="x.mp4")
    assert not list((store.base_dir / "78").glob("source_*"))

    from modules.meeting_intelligence import service as meeting_service
    db = SessionLocal()
    try:
        before = db.query(Meeting).filter(Meeting.created_by == meeting_owner).count()
        with pytest.raises(HTTPException) as exc:
            meeting_service.create_meeting(db, created_by=meeting_owner, upload_file=_video_upload(),
                                           title="Outage", storage=store)
        assert exc.value.status_code == 503
        assert db.query(Meeting).filter(Meeting.created_by == meeting_owner).count() == before
    finally:
        db.close()


def test_meeting_validation_still_applies_before_storage(cloud_meeting_storage):
    store, fake = cloud_meeting_storage
    from modules.meeting_intelligence.storage import FileTooLargeError, UnsupportedMediaError
    with pytest.raises(UnsupportedMediaError):
        store.save_video(79, fileobj=io.BytesIO(FAKE_MP4), original_filename="x.exe")
    with pytest.raises(FileTooLargeError):
        store.save_video(79, fileobj=io.BytesIO(b"x" * (6 * 1024 * 1024)), original_filename="x.mp4")
    assert fake.keys(settings.STORAGE_BUCKET_MEETINGS) == []


def test_recording_download_url_follows_meeting_visibility(client, new_user, fake_storage):
    owner = new_user("Meeting Owner", role="employee")
    outsider = new_user("Outsider", role="employee")
    key = f"{uuid.uuid4().int % 10**8}/source_test.mp4"
    db = SessionLocal()
    try:
        m = Meeting(created_by=owner["id"], title="Private sync", status="completed",
                    source_video_path=key, source_video_filename="sync.mp4")
        db.add(m)
        db.commit()
        mid = m.id
    finally:
        db.close()
    fake_storage.objects[(settings.STORAGE_BUCKET_MEETINGS, key)] = (FAKE_MP4, datetime.now(timezone.utc))
    url = f"/api/v1/meetings/{mid}/recording/download-url"
    r = client.get(url, headers=owner["headers"])
    assert r.status_code == 200 and r.json()["url"].startswith("https://storage.example/signed/meeting-recordings/")
    # Same answer as the meeting itself: unlinked meetings are invisible (404)
    # to non-owners, so the link can't even confirm the recording exists.
    detail = client.get(f"/api/v1/meetings/{mid}", headers=outsider["headers"]).status_code
    assert detail in (403, 404)
    assert client.get(url, headers=outsider["headers"]).status_code == detail
    fake_storage.objects.clear()
    assert client.get(url, headers=owner["headers"]).status_code == 404  # file gone -> clear 404


# ------------------------------------------------------------------ orphan cleanup

def test_orphan_cleanup_only_removes_unreferenced_old_files(client, new_user, fake_storage, meeting_owner):
    recruiter = new_user("Storage Recruiter", role="recruiter")
    job_id = _job(client, recruiter["headers"])
    kept_resume = recruitment_service.resume_object_ref(
        _resume_row(_upload_resume(client, recruiter["headers"], job_id).json()["id"]).file_path)[1]
    old = datetime.now(timezone.utc) - timedelta(days=3)
    rb, mb = settings.STORAGE_BUCKET_RESUMES, settings.STORAGE_BUCKET_MEETINGS
    fake_storage.objects[(rb, kept_resume)] = (PDF, old)
    fake_storage.objects[(rb, "job_1/dead_cv.pdf")] = (PDF, old)                  # orphan
    fake_storage.objects[(rb, "job_1/inflight_cv.pdf")] = (PDF, datetime.now(timezone.utc))  # too new
    db = SessionLocal()
    try:
        live = Meeting(created_by=meeting_owner, title="Live", status="completed")
        db.add(live)
        db.flush()
        live.source_video_path = f"{live.id}/source_live.mp4"
        db.commit()
        live_id = live.id
    finally:
        db.close()
    fake_storage.objects[(mb, f"{live_id}/source_live.mp4")] = (FAKE_MP4, old)
    fake_storage.objects[(mb, f"{live_id}/audio.wav")] = (b"a", old)              # derived: keep
    fake_storage.objects[(mb, f"{live_id}/source_replaced.mp4")] = (FAKE_MP4, old)  # orphan
    fake_storage.objects[(mb, "999999999/source_gone.mp4")] = (FAKE_MP4, old)      # orphan

    db = SessionLocal()
    try:
        orphans = find_orphans(db, fake_storage, grace_hours=24)
    finally:
        db.close()
    assert "job_1/dead_cv.pdf" in orphans[rb]
    assert kept_resume not in orphans[rb] and "job_1/inflight_cv.pdf" not in orphans[rb]
    assert set(orphans[mb]) >= {f"{live_id}/source_replaced.mp4", "999999999/source_gone.mp4"}
    assert f"{live_id}/source_live.mp4" not in orphans[mb] and f"{live_id}/audio.wav" not in orphans[mb]
    delete_orphans(fake_storage, orphans)
    assert (rb, kept_resume) in fake_storage.objects and (mb, f"{live_id}/source_live.mp4") in fake_storage.objects
    assert (rb, "job_1/dead_cv.pdf") not in fake_storage.objects


# ------------------------------------------------------------------ Supabase REST client

def _client_with(handler):
    calls = []

    def record(request):
        calls.append(request)
        return handler(request)

    return obj.SupabaseObjectStorage("https://proj.supabase.co", "service-key-test",
                                     client=httpx.Client(transport=httpx.MockTransport(record))), calls


def test_supabase_client_request_shapes(tmp_path):
    def handler(request):
        if request.url.path.startswith("/storage/v1/object/sign/"):
            return httpx.Response(200, json={"signedURL": "/object/sign/recruitment-resumes/job_1/a.pdf?token=t"})
        if request.url.path == "/storage/v1/object/list/recruitment-resumes":
            body = json.loads(request.content)
            if body["prefix"] == "":
                return httpx.Response(200, json=[{"name": "job_1", "id": None}])
            return httpx.Response(200, json=[{"name": "a.pdf", "id": "x", "updated_at": "2026-11-01T00:00:00Z"}])
        return httpx.Response(200, json={})

    store, calls = _client_with(handler)
    src = tmp_path / "a.pdf"
    src.write_bytes(PDF)
    store.upload_file("recruitment-resumes", "job_1/a.pdf", src, "application/pdf")
    up = calls[-1]
    assert up.method == "POST" and up.url.path == "/storage/v1/object/recruitment-resumes/job_1/a.pdf"
    assert up.headers["authorization"] == "Bearer service-key-test" and up.headers["x-upsert"] == "false"
    assert up.content == PDF

    url = store.signed_url("recruitment-resumes", "job_1/a.pdf", 120)
    assert url == "https://proj.supabase.co/storage/v1/object/sign/recruitment-resumes/job_1/a.pdf?token=t"
    assert json.loads(calls[-1].content) == {"expiresIn": 120}

    assert [o["key"] for o in store.list("recruitment-resumes")] == ["job_1/a.pdf"]  # recursed into the folder

    store.delete("recruitment-resumes", ["job_1/a.pdf"])
    assert calls[-1].method == "DELETE" and json.loads(calls[-1].content) == {"prefixes": ["job_1/a.pdf"]}


def test_supabase_client_errors_are_safe(tmp_path):
    src = tmp_path / "a.pdf"
    src.write_bytes(PDF)
    store, _ = _client_with(lambda r: httpx.Response(500, text="internal secret detail"))
    with pytest.raises(obj.ObjectStorageError) as exc:
        store.upload_file("b", "k.pdf", src)
    assert "secret" not in str(exc.value)
    store, _ = _client_with(lambda r: httpx.Response(404, json={"error": "not_found"}))
    with pytest.raises(obj.ObjectNotFoundError):
        store.signed_url("b", "missing.pdf", 60)

    def unreachable(request):
        raise httpx.ConnectError("down")

    store, _ = _client_with(unreachable)
    with pytest.raises(obj.ObjectStorageError):
        store.upload_file("b", "k.pdf", src)


def test_supabase_mode_requires_credentials(monkeypatch):
    from pydantic import ValidationError
    from config.settings import Settings
    monkeypatch.setenv("STORAGE_BACKEND", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    with pytest.raises(ValidationError, match="SUPABASE_URL"):
        Settings()
