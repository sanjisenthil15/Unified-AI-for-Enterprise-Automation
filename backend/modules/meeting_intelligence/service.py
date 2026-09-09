"""
modules/meeting_intelligence/service.py

Persistence + retrieval logic for Meeting Intelligence.

Phase 3 implements meeting creation (video upload -> disk + DB row) and
deletion. Transcription / diarization / AI analysis and their orchestration
are added in later phases via pipeline.py; nothing here starts processing.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from models.meeting import Meeting
from models.meeting_action_item import MeetingActionItem
from models.meeting_analysis import MeetingAnalysis
from models.meeting_speaker import MeetingSpeaker
from models.meeting_transcript import MeetingTranscript
from models.meeting_transcript_segment import MeetingTranscriptSegment
from modules.meeting_intelligence.config import meeting_settings
from modules.meeting_intelligence.processing.analysis import (
    AnalysisError,
    AnalysisProvider,
    AnalysisResult,
    get_analysis_provider,
)
from modules.meeting_intelligence.processing.audio import AudioExtractionError, extract_audio
from modules.meeting_intelligence.processing.diarization import (
    Diarizer,
    DiarizationError,
    SingleSpeakerDiarizer,
    get_diarizer,
)
from modules.meeting_intelligence.processing.merge import label_for_span
from modules.meeting_intelligence.processing.transcription import (
    TranscriptionError,
    TranscriptionResult,
    transcribe_audio,
)
from modules.meeting_intelligence.storage import (
    EmptyUploadError,
    FileTooLargeError,
    MeetingVideoStorage,
    StorageError,
    UnsupportedMediaError,
    get_storage,
)

# A transcriber takes an audio path and returns a TranscriptionResult.
Transcriber = Callable[[str], TranscriptionResult]


def create_meeting(
    db: Session,
    *,
    created_by: int,
    upload_file: UploadFile,
    title: str,
    description: str | None = None,
    meeting_date: datetime | None = None,
    storage: MeetingVideoStorage | None = None,
) -> Meeting:
    """
    Create a meeting from an uploaded video.

    Flow: insert the row (to get an id) -> stream the file to storage ->
    record the path reference -> commit. The video bytes never touch the DB.
    On any storage failure nothing is committed and no partial file remains.
    """
    storage = storage or get_storage()

    if not title or not title.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "A meeting title is required.")

    meeting = Meeting(
        created_by=created_by,
        title=title.strip(),
        description=description,
        meeting_date=meeting_date,
        status="pending",
    )
    db.add(meeting)
    db.flush()  # assigns meeting.id, no commit yet
    meeting_id = meeting.id

    try:
        stored = storage.save_video(
            meeting_id,
            fileobj=upload_file.file,
            original_filename=upload_file.filename or "",
            content_type=upload_file.content_type,
        )
    except UnsupportedMediaError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc))
    except FileTooLargeError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc))
    except (EmptyUploadError, StorageError) as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))

    meeting.source_video_path     = stored.relative_path
    meeting.source_video_filename = stored.original_filename
    meeting.source_media_type     = stored.content_type
    meeting.file_size_bytes       = stored.size_bytes

    try:
        db.commit()
    except Exception:
        db.rollback()
        storage.delete_meeting_files(meeting_id)
        raise
    db.refresh(meeting)
    return meeting


def get_meeting(db: Session, meeting_id: int) -> Meeting:
    """Fetch a meeting or raise 404."""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if meeting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Meeting id={meeting_id} not found.")
    return meeting


def transcribe_meeting(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
    transcriber: Transcriber | None = None,
) -> MeetingTranscript:
    """
    Run offline speech-to-text on a meeting's extracted audio and persist the
    result: the full transcript in `meeting_transcripts` and each timestamped
    segment (ms) in `meeting_transcript_segments`.

    Speaker attribution is NOT done here — every segment is stored with
    speaker_id / speaker_label = NULL (diarization is Phase 6).

    Re-running replaces any previous transcript + segments for the meeting.
    Raises HTTP 422 if there is no extracted audio, the audio file is missing,
    or transcription fails.
    """
    storage = storage or get_storage()
    run = transcriber or transcribe_audio
    meeting = get_meeting(db, meeting_id)

    if not meeting.audio_path:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no extracted audio. Run audio extraction first.")
    try:
        audio = storage.resolve(meeting.audio_path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not audio.is_file():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Audio file is missing from storage.")

    try:
        result: TranscriptionResult = run(str(audio))
    except TranscriptionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Transcription failed: {exc}")

    # Reprocess-safe: drop any existing transcript + segments first.
    db.query(MeetingTranscriptSegment).filter(
        MeetingTranscriptSegment.meeting_id == meeting_id
    ).delete(synchronize_session=False)
    old = db.query(MeetingTranscript).filter(
        MeetingTranscript.meeting_id == meeting_id
    ).first()
    if old is not None:
        db.delete(old)
        db.flush()

    transcript = MeetingTranscript(
        meeting_id=meeting_id,
        full_text=result.text,
        language=result.language,
        whisper_model=result.model,
        word_count=len(result.text.split()),
        segment_count=len(result.segments),
    )
    db.add(transcript)
    for seg in result.segments:
        db.add(MeetingTranscriptSegment(
            meeting_id=meeting_id,
            speaker_id=None,        # diarization is Phase 6
            speaker_label=None,
            seq=seg.seq,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            text=seg.text,
        ))

    if result.language:
        meeting.language = result.language
    if not meeting.whisper_model:
        meeting.whisper_model = result.model

    db.commit()
    db.refresh(transcript)
    return transcript


def diarize_meeting(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
    diarizer: Diarizer | None = None,
) -> list[MeetingSpeaker]:
    """
    Run speaker diarization on the meeting's audio, persist the detected
    speakers in `meeting_speakers`, and attach speaker_id / speaker_label to
    each transcript segment by time overlap.

    Speaker labels are generic ("Speaker 1", ...). The rows keep
    display_name / mapped_user_id / mapped_employee_id NULL so a real
    identity can be attached later via the API — no schema change needed.

    Graceful degradation (req 8): if the diarization backend fails or its
    optional dependencies are missing, this falls back to a single
    "Speaker 1" rather than raising. A genuinely missing/invalid audio file
    still raises HTTP 422.

    Re-running replaces the previous speakers and re-maps the segments.
    Pipeline status transitions are not done here.
    """
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)

    if not meeting.audio_path:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no extracted audio. Run audio extraction first.")
    try:
        audio = storage.resolve(meeting.audio_path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not audio.is_file():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Audio file is missing from storage.")

    engine = diarizer or get_diarizer()
    try:
        result = engine.diarize(str(audio))
    except DiarizationError:
        try:
            result = SingleSpeakerDiarizer().diarize(str(audio))
        except DiarizationError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                                f"Diarization failed: {exc}")

    if not result.speaker_labels:
        result = SingleSpeakerDiarizer().diarize(str(audio))

    # Reprocess-safe: clear previous mapping + speakers.
    db.query(MeetingTranscriptSegment).filter(
        MeetingTranscriptSegment.meeting_id == meeting_id
    ).update({"speaker_id": None, "speaker_label": None}, synchronize_session=False)
    db.query(MeetingSpeaker).filter(
        MeetingSpeaker.meeting_id == meeting_id
    ).delete(synchronize_session=False)
    db.flush()

    speakers: dict[str, MeetingSpeaker] = {}
    for label in result.speaker_labels:
        row = MeetingSpeaker(meeting_id=meeting_id, label=label)
        db.add(row)
        speakers[label] = row
    db.flush()

    segments = (
        db.query(MeetingTranscriptSegment)
        .filter(MeetingTranscriptSegment.meeting_id == meeting_id)
        .order_by(MeetingTranscriptSegment.seq)
        .all()
    )
    default_label = result.speaker_labels[0]
    seg_counts: dict[str, int] = {}
    speaking_ms: dict[str, int] = {}
    for seg in segments:
        label = label_for_span(seg.start_ms, seg.end_ms, result.turns, default=default_label)
        if label not in speakers:
            label = default_label
        seg.speaker_id = speakers[label].id
        seg.speaker_label = label
        seg_counts[label] = seg_counts.get(label, 0) + 1
        speaking_ms[label] = speaking_ms.get(label, 0) + max(seg.end_ms - seg.start_ms, 0)

    for label, row in speakers.items():
        row.segment_count = seg_counts.get(label, 0)
        secs = round(speaking_ms.get(label, 0) / 1000)
        row.total_speaking_sec = secs or None

    meeting.diarization_backend = result.backend
    db.commit()
    for row in speakers.values():
        db.refresh(row)
    return list(speakers.values())


def _transcript_text_for_analysis(db: Session, meeting_id: int, transcript: MeetingTranscript) -> str:
    """Diarized transcript ("Speaker N: ...") when segments exist, else the full text."""
    segments = (
        db.query(MeetingTranscriptSegment)
        .filter(MeetingTranscriptSegment.meeting_id == meeting_id)
        .order_by(MeetingTranscriptSegment.seq)
        .all()
    )
    if segments:
        text = "\n".join(
            f"{seg.speaker_label or 'Speaker'}: {seg.text}".strip()
            for seg in segments
            if (seg.text or "").strip()
        )
    else:
        text = transcript.full_text or ""
    limit = meeting_settings.analysis_max_transcript_chars
    return text[:limit]


def analyze_meeting(
    db: Session,
    meeting_id: int,
    *,
    provider: AnalysisProvider | None = None,
) -> MeetingAnalysis:
    """
    Run AI analysis on a meeting's transcript and persist structured output:
    summary + key points + decisions in `meeting_analyses`, and each extracted
    task as a `meeting_action_items` row.

    Action items are created UNASSIGNED (assignment_method='unassigned',
    assigned_to_* NULL). The assignee the AI heard is kept as free text in
    `assignee_name_raw` — a human assigns the real person later. No automatic
    assignment.

    Re-running replaces the analysis and any AI action items a human has not
    touched; manually assigned / edited items are kept.

    HTTP 422 if there is no transcript, 503 if the provider is not configured,
    502 on a provider/parse error. Nothing is persisted on failure.
    """
    engine = provider or get_analysis_provider()
    meeting = get_meeting(db, meeting_id)

    transcript = (
        db.query(MeetingTranscript)
        .filter(MeetingTranscript.meeting_id == meeting_id)
        .first()
    )
    if transcript is None or not (transcript.full_text or "").strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no transcript. Run transcription first.")

    text = _transcript_text_for_analysis(db, meeting_id, transcript)
    try:
        result: AnalysisResult = engine.analyze(text)
    except AnalysisError as exc:
        code = (
            status.HTTP_503_SERVICE_UNAVAILABLE if exc.kind == "config"
            else status.HTTP_502_BAD_GATEWAY
        )
        raise HTTPException(code, f"Meeting analysis failed: {exc}")

    # Reprocess-safe: drop untouched AI action items + the old analysis.
    db.query(MeetingActionItem).filter(
        MeetingActionItem.meeting_id == meeting_id,
        MeetingActionItem.source == "ai",
        MeetingActionItem.assignment_method == "unassigned",
        MeetingActionItem.status == "pending",
    ).delete(synchronize_session=False)
    old = db.query(MeetingAnalysis).filter(
        MeetingAnalysis.meeting_id == meeting_id
    ).first()
    if old is not None:
        db.delete(old)
        db.flush()

    analysis = MeetingAnalysis(
        meeting_id=meeting_id,
        summary=result.summary,
        key_points=result.key_points or None,
        decisions=result.decisions or None,
        sentiment=result.sentiment,
        model_provider=result.model_provider,
        model_name=result.model_name or None,
        raw_response=result.raw_response,
    )
    db.add(analysis)
    db.flush()

    for item in result.action_items:
        db.add(MeetingActionItem(
            meeting_id=meeting_id,
            analysis_id=analysis.id,
            description=item.description,
            assignee_name_raw=item.assignee_name_raw,   # NOT resolved to a person
            assignment_method="unassigned",
            priority=item.priority,
            status="pending",
            source="ai",
            ai_confidence=item.confidence,
        ))

    db.commit()
    db.refresh(analysis)
    return analysis


def extract_meeting_audio(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
) -> Meeting:
    """
    Extract audio from a meeting's stored video and record `audio_path`
    (relative reference only — no bytes in the DB). The source video is
    preserved. Pipeline status transitions are handled by pipeline.py
    (Phase 8), not here.

    Raises HTTP 422 if the meeting has no source video, the video file is
    missing from storage, or FFmpeg fails. No partial audio file is left on
    failure.
    """
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)

    if not meeting.source_video_path:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Meeting has no source video to extract audio from.")

    try:
        source = storage.resolve(meeting.source_video_path)
    except StorageError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    if not source.is_file():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "Source video file is missing from storage.")

    target = storage.derived_target(meeting_id, meeting_settings.audio_filename)
    try:
        info = extract_audio(
            source, target,
            sample_rate=meeting_settings.audio_sample_rate,
            channels=meeting_settings.audio_channels,
        )
    except AudioExtractionError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            f"Audio extraction failed: {exc}")

    meeting.audio_path = storage.to_relative(info.path)
    if info.duration_sec:
        meeting.duration_sec = info.duration_sec
    db.commit()
    db.refresh(meeting)
    return meeting


def delete_meeting(
    db: Session,
    meeting_id: int,
    *,
    storage: MeetingVideoStorage | None = None,
) -> None:
    """Delete a meeting row (children cascade) and its stored files."""
    storage = storage or get_storage()
    meeting = get_meeting(db, meeting_id)
    db.delete(meeting)
    db.commit()
    storage.delete_meeting_files(meeting_id)
