"""Policy loading, metadata parsing, chunking, and TF-IDF retrieval.

Version-aware: chunks carry (doc_id, version, effective_date, status). The
retriever filters by case date and labels superseded documents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer

from . import constants as C

_META_RE = {
    "doc_id": re.compile(r"^Document ID:\s*(.+)$", re.MULTILINE),
    "version": re.compile(r"^Version:\s*(.+)$", re.MULTILINE),
    "effective": re.compile(r"^Effective date:\s*(.+)$", re.MULTILINE),
    "status": re.compile(r"^Status:\s*(.+)$", re.MULTILINE),
}

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass(frozen=True)
class PolicyChunk:
    doc_id: str
    version: str
    effective_date: date
    status: str
    section: str
    text: str

    @property
    def superseded(self) -> bool:
        return "SUPERSEDED" in self.status.upper()

    @property
    def label(self) -> str:
        return f"{self.doc_id} {self.version}"


def _parse_date(raw: str) -> date:
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3,})\s+(\d{4})", raw.strip())
    if not m:
        raise ValueError(f"Unparseable effective date: {raw!r}")
    day, mon, year = int(m.group(1)), m.group(2)[:3].lower(), int(m.group(3))
    return date(year, _MONTHS[mon], day)


def load_policies(policies_dir: Path) -> list[PolicyChunk]:
    """Load every KB-*.md file and split it into '## ' sections."""
    chunks: list[PolicyChunk] = []
    for path in sorted(policies_dir.glob("KB-*.md")):
        text = path.read_text(encoding="utf-8")
        doc_id = _META_RE["doc_id"].search(text)
        version = _META_RE["version"].search(text)
        effective = _META_RE["effective"].search(text)
        status = _META_RE["status"].search(text)
        if not all((doc_id, version, effective, status)):
            continue
        eff_date = _parse_date(effective.group(1))
        status_str = status.group(1).strip()
        # Split by level-2 headings; keep the preamble attached to a section.
        parts = re.split(r"(?m)^##\s+", text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            first_line, _, rest = part.partition("\n")
            section = first_line.strip()
            body = rest.strip()
            if not body:
                continue
            # Keep the archive notice attached to every KB-05 chunk.
            if "SUPERSEDED" in status_str.upper():
                body = "ARCHIVE NOTICE: " + body
            chunks.append(
                PolicyChunk(
                    doc_id=doc_id.group(1).strip(),
                    version=version.group(1).strip(),
                    effective_date=eff_date,
                    status=status_str,
                    section=section,
                    text=body,
                )
            )
    return chunks


class PolicyIndex:
    """TF-IDF index over policy chunks with version-aware filtering."""

    def __init__(self, chunks: list[PolicyChunk]) -> None:
        self.chunks = chunks
        self._vectorizer = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2)
        )
        corpus = [f"{c.doc_id} {c.version} {c.section}\n{c.text}" for c in chunks]
        self._matrix = self._vectorizer.fit_transform(corpus) if corpus else None

    def relevant(
        self,
        query: str,
        assessed_on: date,
        include_superseded: bool = False,
        top_k: int = 6,
    ) -> list[PolicyChunk]:
        """Return chunks relevant to the query, filtered by case date."""
        eligible = [
            c
            for c in self.chunks
            if c.effective_date <= assessed_on
            and (include_superseded or not c.superseded)
        ]
        if not eligible or self._matrix is None:
            return eligible[:top_k]

        # Re-rank the eligible subset by cosine similarity to the query.
        sub_corpus = [
            f"{c.doc_id} {c.version} {c.section}\n{c.text}" for c in eligible
        ]
        sub_vec = TfidfVectorizer(
            lowercase=True, stop_words="english", ngram_range=(1, 2)
        ).fit_transform(sub_corpus + [query])
        scores = (sub_vec[:-1] @ sub_vec[-1].T).toarray().ravel()
        ranked = sorted(zip(eligible, scores), key=lambda x: x[1], reverse=True)
        return [c for c, s in ranked[:top_k] if s > 0] or eligible[:top_k]


def mandatory_sources(query: str, notes: str) -> list[str]:
    """Rule-driven mandatory source IDs based on query keywords (KB-01..04)."""
    haystack = f"{query} {notes}".lower()
    wanted: list[str] = []
    if any(k in haystack for k in ("attend", "session", "medical", "makeup", "certif")):
        wanted.append(C.KB_ATTENDANCE)
    if any(k in haystack for k in ("capstone", "extension", "deadline", "due", "score", "pass")):
        wanted.append(C.KB_CAPSTONE)
    if any(k in haystack for k in ("submit", "submission", "zip", "repo", "readme", "secret", "key")):
        wanted.append(C.KB_SUBMISSION)
    if any(k in haystack for k in ("status", "workflow", "next", "case")):
        wanted.append(C.KB_WORKFLOW)
    return wanted


def refers_to_old_policy(query: str, notes: str) -> bool:
    """Detect questions that mention the superseded 60-point or old deadline."""
    haystack = f"{query} {notes}".lower()
    return any(
        k in haystack
        for k in ("60", "old policy", "older policy", "superseded", "18:00", "colleague")
    )