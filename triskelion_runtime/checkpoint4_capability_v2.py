from __future__ import annotations

from typing import Iterable, Sequence

from triskelion_runtime.checkpoint3_capability import normalize_context


def _norm_many(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(normalize_context(value) for value in values)


def entailed_forbidden(positive: str, forbidden: str) -> bool:
    """Literal-substring routing: positive presence entails forbidden presence."""
    p = normalize_context(positive)
    f = normalize_context(forbidden)
    return bool(p and f and f in p)


def route_satisfiable(
    required_any: Sequence[str],
    required_all: Sequence[str],
    forbidden_any: Sequence[str],
) -> bool:
    """Conservative satisfiability test for CP4 literal-substring routing.

    A required_all signature that contains a forbidden signature makes every
    satisfying context impossible. When required_any is nonempty, at least one
    alternative must remain that does not itself entail a forbidden match.
    """
    req_any = _norm_many(required_any)
    req_all = _norm_many(required_all)
    forb = _norm_many(forbidden_any)

    for positive in req_all:
        if any(f and f in positive for f in forb):
            return False

    if req_any:
        viable = [
            positive
            for positive in req_any
            if not any(f and f in positive for f in forb)
        ]
        if not viable:
            return False

    return bool(req_any or req_all)


def fixed_patch_leak(
    emitted_texts: Iterable[str],
    added_patch_literals: Iterable[str],
    *,
    min_chars: int = 16,
) -> bool:
    """Reject long fixed-patch overlap in either substring direction."""
    emitted = [normalize_context(x) for x in emitted_texts]
    fixed = [normalize_context(x) for x in added_patch_literals]
    for text in emitted:
        if len(text) < min_chars:
            continue
        for literal in fixed:
            if len(literal) < min_chars:
                continue
            if text in literal or literal in text:
                return True
    return False


def acquisition_activation_sanity(
    required_any: Sequence[str],
    required_all: Sequence[str],
    forbidden_any: Sequence[str],
    buggy_visible_context: str,
) -> bool:
    """A prospective rule must at least route on its own buggy acquisition context."""
    if not route_satisfiable(required_any, required_all, forbidden_any):
        return False
    context = normalize_context(buggy_visible_context)
    forb = _norm_many(forbidden_any)
    req_all = _norm_many(required_all)
    req_any = _norm_many(required_any)
    if any(f in context for f in forb):
        return False
    if any(p not in context for p in req_all):
        return False
    if req_any and not any(p in context for p in req_any):
        return False
    return True
