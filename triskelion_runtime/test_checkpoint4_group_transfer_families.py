from triskelion_runtime.checkpoint4_group_transfer_families import (
    Fingerprint,
    fingerprint,
    similarity,
)


def _row(project, bug_id, command, output):
    return {
        "project": project,
        "bug_id": bug_id,
        "classification": "qualified",
        "buggy": {
            "test": {
                "steps": [
                    {"command": command, "output": output, "returncode": 1}
                ]
            }
        },
        # These must have no effect on grouping fingerprints.
        "fixed": {"test": {"steps": [{"output": "SECRET_FIXED_ONLY_TOKEN"}]}},
        "fixed_commit": "abcdef0123456789abcdef0123456789abcdef01",
    }


def test_fingerprint_uses_buggy_visible_material_only():
    row = _row(
        "alpha",
        "42",
        "pytest tests/test_parser.py::test_escape",
        "ValueError: malformed escape sequence in parser input",
    )
    fp = fingerprint(row)
    joined = set(fp.test_tokens) | set(fp.class_tokens) | set(fp.message_tokens)
    assert "secret_fixed_only_token" not in joined
    assert "valueerror" in fp.class_tokens


def test_identity_and_long_numbers_are_scrubbed():
    row = _row(
        "alpha",
        "42",
        "pytest alpha/tests/test_42.py",
        "AssertionError alpha bug 42 at /tmp/alpha/file.py token 12345678",
    )
    fp = fingerprint(row)
    joined = set(fp.test_tokens) | set(fp.message_tokens)
    assert "alpha" not in joined
    assert "12345678" not in joined


def test_similarity_requires_guard_and_threshold():
    a = Fingerprint(
        frozenset({"parser", "escape", "case"}),
        frozenset({"valueerror"}),
        frozenset({"malformed", "escape", "sequence"}),
    )
    b = Fingerprint(
        frozenset({"parser", "escape", "case"}),
        frozenset({"valueerror"}),
        frozenset({"malformed", "escape", "sequence"}),
    )
    result = similarity(a, b)
    assert result["edge"] is True
    assert result["score"] == 1.0


def test_unrelated_failures_do_not_form_edge():
    a = Fingerprint(
        frozenset({"parser", "escape"}),
        frozenset({"valueerror"}),
        frozenset({"malformed", "escape"}),
    )
    b = Fingerprint(
        frozenset({"database", "transaction"}),
        frozenset({"keyerror"}),
        frozenset({"missing", "record"}),
    )
    result = similarity(a, b)
    assert result["edge"] is False


def test_same_exception_alone_is_not_enough():
    a = Fingerprint(frozenset({"parser"}), frozenset({"valueerror"}), frozenset({"escape"}))
    b = Fingerprint(frozenset({"loader"}), frozenset({"valueerror"}), frozenset({"shape"}))
    result = similarity(a, b)
    assert result["class_exact"] is True
    assert result["score"] < 0.60
    assert result["edge"] is False
