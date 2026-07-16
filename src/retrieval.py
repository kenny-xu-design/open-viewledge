from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


LATIN_WORD = re.compile(r"[a-zA-Z0-9_]+")
CHINESE_RUN = re.compile(r"[\u3400-\u9fff]+")
GENERIC_VIDEO_TERMS = {"视频", "内容", "主题", "总结", "主要", "讲了", "讲什么"}


class ContextRetriever:
    def __init__(self, groups: list[dict[str, Any]], *, limit: int = 6, character_budget: int = 12_000) -> None:
        self.groups = groups
        self.limit = limit
        self.character_budget = character_budget

    def retrieve(self, query: str) -> list[dict[str, Any]]:
        return retrieve_groups(query, self.groups, limit=self.limit, character_budget=self.character_budget)


def tokenize(value: str) -> list[str]:
    text = value.lower()
    tokens = LATIN_WORD.findall(text)
    for run in CHINESE_RUN.findall(text):
        tokens.extend(run if len(run) == 1 else (run[index : index + 2] for index in range(len(run) - 1)))
    return [token for token in tokens if token.strip()]


def retrieve_groups(
    query: str,
    groups: list[dict[str, Any]],
    *,
    limit: int = 6,
    character_budget: int = 12_000,
) -> list[dict[str, Any]]:
    if not groups or limit <= 0:
        return []
    documents = [tokenize(f"{item.get('title', '')} {item.get('text', '')}") for item in groups]
    query_terms = tokenize(query)
    scores = _bm25_scores(query_terms, documents)
    ranked = sorted(range(len(groups)), key=lambda index: (-scores[index], index))
    if not any(score > 0 for score in scores):
        if not any(term in query for term in GENERIC_VIDEO_TERMS):
            return []
        ranked = list(range(len(groups)))

    selected: list[int] = []
    for index in ranked:
        for candidate in (index, index - 1, index + 1):
            if 0 <= candidate < len(groups) and candidate not in selected:
                selected.append(candidate)
                if len(selected) >= limit:
                    break
        if len(selected) >= limit:
            break

    result: list[dict[str, Any]] = []
    remaining = max(0, character_budget)
    for index in sorted(selected, key=lambda item: float(groups[item].get("start") or 0)):
        item = dict(groups[index])
        text = str(item.get("text") or "")
        if remaining <= 0:
            break
        item["text"] = text[:remaining]
        remaining -= len(item["text"])
        result.append(item)
    return result


def _bm25_scores(query_terms: list[str], documents: list[list[str]]) -> list[float]:
    if not query_terms:
        return [0.0] * len(documents)
    count = len(documents)
    average_length = sum(len(document) for document in documents) / max(count, 1)
    frequencies = [Counter(document) for document in documents]
    document_frequency = Counter(term for term in set(query_terms) for document in documents if term in document)
    scores: list[float] = []
    for document, frequency in zip(documents, frequencies):
        score = 0.0
        length_factor = 1 - 0.75 + 0.75 * (len(document) / max(average_length, 1))
        for term in query_terms:
            occurrences = frequency.get(term, 0)
            if not occurrences:
                continue
            idf = math.log(1 + (count - document_frequency[term] + 0.5) / (document_frequency[term] + 0.5))
            score += idf * (occurrences * 2.5) / (occurrences + 1.5 * length_factor)
        scores.append(score)
    return scores
