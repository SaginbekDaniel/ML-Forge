"""Unit tests for host-side grading (no Docker needed)."""

from mlforge_runner.grading import deep_equal, grade, grade_test, normalize_stdout


def call(id_="t", expected="3", visibility="public", **kw):
    return {"id": id_, "kind": "call", "call": "f()", "expected": expected, "visibility": visibility, **kw}


def test_deep_equal_is_type_strict():
    assert deep_equal(3, 3)
    assert not deep_equal(True, 1)
    assert not deep_equal(2.0, 2)
    assert not deep_equal([1, 2], (1, 2))
    assert deep_equal({"a": [1, (2, 3)]}, {"a": [1, (2, 3)]})


def test_float_and_unordered_modes():
    assert deep_equal(0.1 + 0.2, 0.3, "float")
    assert not deep_equal(0.1 + 0.2, 0.3, "exact")
    assert deep_equal([3, 1, 2], [1, 2, 3], "unordered")
    assert not deep_equal([1, 1, 2], [1, 2, 2], "unordered")


def test_normalize_stdout_ignores_trailing_whitespace_only():
    assert normalize_stdout("a  \r\nb\n\n") == "a\nb"
    assert normalize_stdout("  a") == "  a"


def test_passed_and_wrong_answer():
    ok = grade_test(call(), {"id": "t", "status": "ok", "repr": "3", "type": "int"})
    assert ok.passed and ok.status == "passed"
    bad = grade_test(call(), {"id": "t", "status": "ok", "repr": "'3'", "type": "str"})
    assert not bad.passed and bad.status == "wrong_answer" and "type mismatch" in bad.message


def test_hidden_test_never_exposes_inputs_outputs_or_messages():
    spec = call(visibility="hidden")
    out = grade_test(
        spec,
        {
            "id": "t",
            "status": "exception",
            "stdout": "secret-input 42",
            "exc": {"type": "ValueError", "message": "bad value 42", "phase": "call", "line": 3},
        },
    )
    d = out.to_dict()
    assert d["input"] is None and d["expected"] is None and d["actual"] is None
    assert d["stdout"] is None and d["message"] is None
    assert out.error_type == "ValueError" and out.line == 3


def test_expected_exception():
    spec = {"id": "t", "kind": "call", "call": "f(-1)", "raises": "ValueError", "visibility": "public"}
    assert grade_test(spec, {"id": "t", "status": "exception", "exc": {"type": "ValueError", "phase": "call"}}).passed
    assert not grade_test(spec, {"id": "t", "status": "ok", "repr": "1"}).passed
    # an exception during module import is not the expected raise
    assert not grade_test(
        spec, {"id": "t", "status": "exception", "exc": {"type": "ValueError", "phase": "module"}}
    ).passed


def test_non_literal_return_is_wrong_not_crash():
    out = grade_test(call(), {"id": "t", "status": "ok", "repr": "<object at 0x1>", "type": "object"})
    assert out.status == "wrong_answer"


def test_infrastructure_statuses_map():
    for raw, expected in [
        ("timeout", "timeout"),
        ("killed", "memory_limit"),
        ("output_limit", "output_limit"),
        ("not_run", "not_run"),
        ("crashed", "crashed"),
    ]:
        assert grade_test(call(), {"id": "t", "status": raw}).status == expected


def test_summary_counts_edge_cases_and_first_error():
    specs = [call("a"), call("b", tags=["edge_case"]), call("c", tags=["edge_case"])]
    obs = [
        {"id": "a", "status": "ok", "repr": "3"},
        {"id": "b", "status": "exception", "exc": {"type": "TypeError", "phase": "call"}},
        {"id": "c", "status": "ok", "repr": "3"},
    ]
    _, s = grade(specs, obs)
    assert (s.passed, s.total, s.edge_cases_passed, s.edge_cases_total) == (2, 3, 1, 2)
    assert s.error_type == "TypeError"
    assert abs(s.score - 2 / 3) < 1e-9


def test_stdout_test():
    spec = {"id": "s", "kind": "stdout", "stdin": "x", "expected_stdout": "Hello", "visibility": "public"}
    assert grade_test(spec, {"id": "s", "status": "ok", "stdout": "Hello\n"}).passed
    assert not grade_test(spec, {"id": "s", "status": "ok", "stdout": "Hello", "stdout_truncated": True}).passed
