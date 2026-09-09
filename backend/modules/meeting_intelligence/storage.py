"""
modules/meeting_intelligence/storage.py

Local filesystem storage for meeting media. Videos are NEVER stored in
PostgreSQL — only their on-disk path/reference is persisted.

Populated in Phase 3. Layout (under the git-ignored backend/uploads/):
    uploads/meetings/<meeting_id>/source<ext>      original upload
    uploads/meetings/<meeting_id>/audio.wav        extracted 16 kHz mono audio

Mirrors the storage approach already used by modules/recruitment/service.py
(UUID-prefixed filenames, path string saved to the DB row).
"""
