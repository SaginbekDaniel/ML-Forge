"""Static content validation (no Docker)."""

import shutil

import pytest
import yaml
from mlforge_api.config import REPO_ROOT
from mlforge_api.content.loader import ContentError, find_cycle, load_curriculum
from mlforge_api.content.schema import ExerciseSpec, TestSpec

CONTENT = REPO_ROOT / "content" / "curriculum"


def test_real_curriculum_loads_and_meets_m1_minimums():
    cur = load_curriculum(CONTENT)
    active = [s for s in cur.index.skills if s.status == "active"]
    assert len(cur.lessons) >= 4
    practice_or_assess = [e for e in cur.exercises.values() if e.role in ("practice", "assessment")]
    assert len(practice_or_assess) >= 12
    for s in active:
        exs = cur.exercises_for(s.id)
        assert sum(e.role == "assessment" for e in exs) >= 1
        assert sum(e.role == "practice" for e in exs) >= 2
    for e in cur.exercises.values():
        assert e.review_status == "reviewed"
        assert e.wrong_solutions and len(e.hints) == 3


def test_prerequisite_graph_is_acyclic_and_cycles_are_detected():
    cur = load_curriculum(CONTENT)
    assert find_cycle({s.id: s.prerequisites for s in cur.index.skills}) is None
    assert find_cycle({"a": ["b"], "b": ["c"], "c": ["a"]}) is not None


def test_cycle_in_content_is_rejected(tmp_path):
    root = tmp_path / "c"
    shutil.copytree(CONTENT, root)
    data = yaml.safe_load((root / "skills.yaml").read_text())
    data["skills"][0]["prerequisites"] = [data["skills"][-1]["id"]]
    (root / "skills.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    with pytest.raises(ContentError) as exc:
        load_curriculum(root)
    assert any("cycle" in e for e in exc.value.errors)


def test_test_spec_requires_literal_expected():
    with pytest.raises(ValueError):
        TestSpec(id="t", kind="call", call="f()", expected="not a literal ((")


def test_exercise_requires_hidden_and_edge_tests():
    cur = load_curriculum(CONTENT)
    raw = cur.exercises["cond.sign"].model_dump()
    raw["tests"] = [t for t in raw["tests"] if t["visibility"] == "public"]
    with pytest.raises(ValueError):
        ExerciseSpec.model_validate(raw)


def test_lessons_hide_nothing_they_should_not():
    cur = load_curriculum(CONTENT)
    for lesson in cur.lessons.values():
        assert 2 <= len(lesson.check_questions) <= 4
        assert len(lesson.examples) >= 2
        assert lesson.common_mistake.fix_md


def test_changed_content_without_version_bump_is_rejected(tmp_path):
    from mlforge_api.config import Settings
    from mlforge_api.content.seed import seed_content
    from mlforge_api.db import init_engine, session_scope
    from mlforge_api.runtime import migrate

    settings = Settings(
        data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'g.db'}", content_dir=CONTENT, anthropic_api_key=None
    )
    init_engine(settings.resolved_database_url)
    migrate(settings)
    with session_scope() as db:
        rep = seed_content(db, load_curriculum(CONTENT), sandbox=None)
    assert rep.pending  # no sandbox -> nothing activated, honestly reported

    root = tmp_path / "c"
    shutil.copytree(CONTENT, root)
    path = root / "exercises" / "cond.sign.yaml"
    path.write_text(path.read_text(encoding="utf-8").replace("Знак числа", "Знак числа (изменено)"), encoding="utf-8")
    with session_scope() as db, pytest.raises(ContentError) as exc:
        seed_content(db, load_curriculum(root), sandbox=None)
    assert any("without a version bump" in e for e in exc.value.errors)
