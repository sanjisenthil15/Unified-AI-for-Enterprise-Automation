"""
modules/files/cleanup.py

Finds (and optionally deletes) stored files nothing in the database points
at any more — e.g. a process died between uploading the bytes and
committing the row, or a manual delete half-failed.

Safety rules:
  - Only objects older than `grace_hours` are considered, so an upload
    whose database commit is still in progress is never touched.
  - Resumes: an object is orphaned when no Resume row references it.
  - Meetings: keys look like "<meeting_id>/<file>". An object is orphaned
    when its meeting no longer exists, or when it is a *source* recording
    ("source_*") the meeting no longer references. Derived files of live
    meetings (extracted audio) are never flagged.
  - Legacy local resume paths (pre-object-storage) are not inspected.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from config.settings import settings
from core.object_storage import ObjectStorage
from models.meeting import Meeting
from models.resume import Resume
from modules.recruitment.service import resume_object_ref


def find_orphans(db: Session, storage: ObjectStorage, grace_hours: float = 24) -> dict[str, list[str]]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=grace_hours)
    orphans: dict[str, list[str]] = {}

    bucket = settings.STORAGE_BUCKET_RESUMES
    referenced = {
        ref[1] for (path,) in db.query(Resume.file_path).all()
        if (ref := resume_object_ref(path)) is not None and ref[0] == bucket
    }
    orphans[bucket] = sorted(
        o["key"] for o in storage.list(bucket)
        if o["updated_at"] <= cutoff and o["key"] not in referenced and o["key"].startswith("job_")
    )

    bucket = settings.STORAGE_BUCKET_MEETINGS
    sources = dict(db.query(Meeting.id, Meeting.source_video_path).all())
    flagged = []
    for o in storage.list(bucket):
        if o["updated_at"] > cutoff:
            continue
        head, _, name = o["key"].partition("/")
        if not head.isdigit() or not name:
            continue
        meeting_id = int(head)
        if meeting_id not in sources:
            flagged.append(o["key"])
        elif name.startswith("source_") and sources[meeting_id] != o["key"]:
            flagged.append(o["key"])
    orphans[bucket] = sorted(flagged)
    return orphans


def delete_orphans(storage: ObjectStorage, orphans: dict[str, list[str]]) -> int:
    count = 0
    for bucket, keys in orphans.items():
        for start in range(0, len(keys), 100):
            batch = keys[start:start + 100]
            storage.delete(bucket, batch)
            count += len(batch)
    return count
