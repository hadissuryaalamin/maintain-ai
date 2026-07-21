"""Deterministic lexical retrieval over pre-chunked synthetic manuals.

This intentionally retrieves only a few relevant chunks. It is easy to replace with a
PostgreSQL full-text or vector index later without changing the tool contract.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ManualChunk
from app.security.content import contains_likely_prompt_injection, delimit_untrusted_content
from app.security.context import AuthContext, log_security_event


def tokenize(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9][a-z0-9_-]+", value.lower()) if len(token) > 1}


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    chunk_id: str
    title: str
    section: str
    excerpt: str
    source_reference: str
    relevance_score: float


class RetrievalService:
    def __init__(self, session: Session, context: AuthContext, *, chunk_limit: int = 4) -> None:
        self.session = session
        self.context = context
        self.chunk_limit = chunk_limit

    def search_manual(self, query: str, machine_model: str | None) -> list[RetrievedChunk]:
        statement = select(ManualChunk).where(ManualChunk.tenant_id == self.context.tenant_id)
        if machine_model:
            statement = statement.where(ManualChunk.machine_model == machine_model)
        chunks = list(self.session.scalars(statement))
        query_terms = tokenize(query)
        scored: list[tuple[ManualChunk, float]] = []
        for chunk in chunks:
            title_terms = tokenize(f"{chunk.title} {chunk.section} {chunk.machine_model}")
            content_terms = tokenize(chunk.content)
            title_overlap = len(query_terms & title_terms)
            content_overlap = len(query_terms & content_terms)
            identifier_overlap = sum(
                1
                for term in query_terms & title_terms
                if "-" in term or any(character.isdigit() for character in term)
            )
            # A compact, deterministic ranking function suitable for the small fixture corpus.
            score = (2.0 * title_overlap + content_overlap + 8.0 * identifier_overlap) / math.sqrt(
                max(len(content_terms), 1)
            )
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda item: (item[1], item[0].id), reverse=True)

        results: list[RetrievedChunk] = []
        for chunk, score in scored[: self.chunk_limit]:
            if chunk.is_adversarial_fixture or contains_likely_prompt_injection(chunk.content):
                log_security_event(
                    self.session,
                    context=self.context,
                    event_type="prompt_injection_content_retrieved",
                    target_type="manual_chunk",
                    target_id=chunk.id,
                    detail="Potential prompt injection was contained as untrusted evidence.",
                )
            results.append(
                RetrievedChunk(
                    chunk_id=chunk.id,
                    title=chunk.title,
                    section=chunk.section,
                    excerpt=delimit_untrusted_content(chunk.content[:1600]),
                    source_reference=chunk.source_reference,
                    relevance_score=round(score, 4),
                )
            )
        return results
