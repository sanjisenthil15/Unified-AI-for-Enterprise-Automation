"""
modules/customer_support/chunking.py

Deterministic text chunking and keyword extraction service for KnowledgeDocuments.

Design:
  - Preserves sentence and paragraph boundaries (no mid-word chopping).
  - Configurable maximum chunk character length and context overlap.
  - Generates searchable keyword tags for hybrid lexical retrieval.
  - Deterministic: Identical text content always produces identical chunks.
"""

import re
from typing import Dict, List, Set

# Default chunking parameters
DEFAULT_MAX_CHUNK_CHARS: int = 600
DEFAULT_OVERLAP_CHARS: int = 100
DEFAULT_MIN_CHUNK_CHARS: int = 40

# Standard English stopwords to filter during keyword extraction
STOPWORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "can't", "cannot", "could",
    "couldn't", "did", "didn't", "do", "does", "doesn't", "doing", "don't", "down",
    "during", "each", "few", "for", "from", "further", "had", "hadn't", "has",
    "hasn't", "have", "haven't", "having", "he", "he'd", "he'll", "he's", "her",
    "here", "here's", "hers", "herself", "him", "himself", "his", "how", "how's",
    "i", "i'd", "i'll", "i'm", "i've", "if", "in", "into", "is", "isn't", "it",
    "it's", "its", "itself", "let's", "me", "more", "most", "mustn't", "my",
    "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or", "other",
    "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "shan't",
    "she", "she'd", "she'll", "she's", "should", "shouldn't", "so", "some", "such",
    "than", "that", "that's", "the", "their", "theirs", "them", "themselves",
    "then", "there", "there's", "these", "they", "they'd", "they'll", "they're",
    "they've", "this", "those", "through", "to", "too", "under", "until", "up",
    "very", "was", "wasn't", "we", "we'd", "we'll", "we're", "we've", "were",
    "weren't", "what", "what's", "when", "when's", "where", "where's", "which",
    "while", "who", "who's", "whom", "why", "why's", "with", "won't", "would",
    "wouldn't", "you", "you'd", "you'll", "you're", "you've", "your", "yours",
    "yourself", "yourselves", "will", "shall", "may", "might", "must", "also",
    "please", "thank", "thanks", "hello", "hi", "etc", "e.g.", "i.e.",
}


def normalize_text(text: str) -> str:
    """
    Normalizes text by unifying newlines, replacing tabs, and stripping excess whitespace.
    """
    if not text:
        return ""
    # Unify line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace multiple empty lines with a double newline
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_keywords(text: str, max_keywords: int = 8) -> str:
    """
    Extracts top informative keywords from chunk text for lexical search boosting.
    Preserves technical terms, error codes (e.g., '500', '2fa'), and domain terms.
    """
    if not text:
        return ""

    # Tokenize words, technical identifiers, and numbers
    raw_tokens = re.findall(r"[A-Za-z0-9_\-\.]{2,}", text.lower())
    
    # Filter stopwords and short punctuation-only tokens
    meaningful_tokens: List[str] = []
    frequency: Dict[str, int] = {}

    for t in raw_tokens:
        clean = t.strip(".-_")
        if not clean or clean in STOPWORDS:
            continue
        if len(clean) < 2:
            continue
        # Check if it's alphanumeric
        if re.search(r"[A-Za-z0-9]", clean):
            frequency[clean] = frequency.get(clean, 0) + 1
            if clean not in meaningful_tokens:
                meaningful_tokens.append(clean)

    # Sort tokens by frequency descending, then by original appearance
    sorted_keywords = sorted(
        meaningful_tokens,
        key=lambda k: (-frequency[k], -len(k)),
    )

    return ", ".join(sorted_keywords[:max_keywords])


def split_text_into_chunks(
    content: str,
    max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
    min_chunk_chars: int = DEFAULT_MIN_CHUNK_CHARS,
) -> List[Dict[str, object]]:
    """
    Splits a document text into ordered, overlapping, sentence-aware chunks.

    Args:
        content: Raw text content of the knowledge document.
        max_chunk_chars: Maximum character length per chunk.
        overlap_chars: Number of trailing characters from previous chunk to prepend as context.
        min_chunk_chars: Minimum character length for the final trailing chunk.

    Returns:
        List of dicts:
          [
            {
              "chunk_index": int,
              "chunk_text": str,
              "keywords": str
            },
            ...
          ]
    """
    normalized = normalize_text(content)
    if not normalized:
        return []

    # If content fits in a single chunk, return immediately
    if len(normalized) <= max_chunk_chars:
        return [
            {
                "chunk_index": 0,
                "chunk_text": normalized,
                "keywords": extract_keywords(normalized),
            }
        ]

    # Split into paragraphs first
    paragraphs = [p.strip() for p in normalized.split("\n\n") if p.strip()]

    # Further break down large paragraphs into sentences
    units: List[str] = []
    for p in paragraphs:
        if len(p) <= max_chunk_chars:
            units.append(p)
        else:
            # Sentence splitter: look for ., !, or ? followed by whitespace or line breaks
            sentences = re.split(r"(?<=[.!?])\s+", p)
            for s in sentences:
                s_clean = s.strip()
                if s_clean:
                    units.append(s_clean)

    chunks: List[str] = []
    current_chunk: List[str] = []
    current_length = 0

    for unit in units:
        unit_len = len(unit)
        # If adding unit exceeds max_chunk_chars and we already have content, seal current chunk
        if current_length + unit_len + 1 > max_chunk_chars and current_chunk:
            chunk_text = "\n\n".join(current_chunk).strip()
            chunks.append(chunk_text)

            # Start new chunk with overlap from the tail of current chunk
            overlap_prefix = ""
            if overlap_chars > 0 and len(chunk_text) > overlap_chars:
                # Find a clean sentence or word boundary within the overlap window
                tail = chunk_text[-overlap_chars:]
                boundary_idx = tail.find(" ")
                if boundary_idx != -1 and boundary_idx < len(tail) - 10:
                    overlap_prefix = tail[boundary_idx + 1:].strip()
                else:
                    overlap_prefix = tail.strip()

            current_chunk = [overlap_prefix, unit] if overlap_prefix else [unit]
            current_length = sum(len(x) + 1 for x in current_chunk)
        else:
            current_chunk.append(unit)
            current_length += unit_len + 1

    # Append remaining trailing chunk
    if current_chunk:
        final_chunk = "\n\n".join(current_chunk).strip()
        if len(final_chunk) >= min_chunk_chars or not chunks:
            chunks.append(final_chunk)
        elif chunks:
            # Append trailing short fragment to the previous chunk if it won't blow up size excessively
            chunks[-1] = (chunks[-1] + "\n\n" + final_chunk).strip()

    # Build final structured chunk records
    result: List[Dict[str, object]] = []
    for idx, text_block in enumerate(chunks):
        cleaned_text = text_block.strip()
        if cleaned_text:
            result.append(
                {
                    "chunk_index": idx,
                    "chunk_text": cleaned_text,
                    "keywords": extract_keywords(cleaned_text),
                }
            )

    return result
