"""
processing/analysis.py — Phase 7.

Turn a diarized transcript into structured JSON:
    {summary, key_points[], decisions[], action_items[]}

where each action_item is {description, assignee_name_raw, due_date_hint,
confidence}. Assignment is MANUAL in the MVP — the AI only extracts the
raw mention; it does NOT resolve it to an employee/user.

Provider abstraction (selected by MeetingSettings.ai_provider):

    class AnalysisProvider(Protocol):
        def analyze(self, transcript: str) -> dict: ...

    "gemini" — google-genai, same call/parse pattern as
               modules/recruitment/service.py (strip fences -> json.loads)  (default)
    "ollama" — local LLM, possible later

Stub only in Phase 1. No hard-coded AI responses.
"""
