"""Load and statically validate curriculum content from ``content/curriculum``."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import ValidationError

from .schema import CurriculumIndex, DiagnosticSpec, ExerciseSpec, LessonSpec


class ContentError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass
class Curriculum:
    index: CurriculumIndex
    lessons: dict[str, LessonSpec] = field(default_factory=dict)
    exercises: dict[str, ExerciseSpec] = field(default_factory=dict)
    diagnostic: DiagnosticSpec | None = None

    def exercises_for(self, skill_id: str) -> list[ExerciseSpec]:
        return sorted((e for e in self.exercises.values() if e.skill == skill_id), key=lambda e: e.position)


def content_hash(model) -> str:
    payload = json.dumps(model.model_dump(mode="json"), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def find_cycle(edges: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle in a prerequisite graph (node -> prerequisites), or None."""
    white, grey, black = 0, 1, 2
    color = {n: white for n in edges}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        color[node] = grey
        stack.append(node)
        for nxt in edges.get(node, []):
            if color.get(nxt, white) == grey:
                return stack[stack.index(nxt) :] + [nxt]
            if color.get(nxt, white) == white and nxt in edges:
                found = visit(nxt)
                if found:
                    return found
        stack.pop()
        color[node] = black
        return None

    for n in list(edges):
        if color[n] == white:
            found = visit(n)
            if found:
                return found
    return None


def load_curriculum(root: Path) -> Curriculum:
    errors: list[str] = []
    try:
        index = CurriculumIndex.model_validate(_read_yaml(root / "skills.yaml"))
    except (ValidationError, FileNotFoundError) as exc:
        raise ContentError([f"skills.yaml: {exc}"]) from exc

    cur = Curriculum(index=index)
    skill_ids = {s.id for s in index.skills}
    track_ids = {t.id for t in index.tracks}
    if len(skill_ids) != len(index.skills):
        errors.append("skills.yaml: duplicate skill ids")
    for s in index.skills:
        if s.track not in track_ids:
            errors.append(f"skill {s.id}: unknown track {s.track}")
        for p in s.prerequisites:
            if p not in skill_ids:
                errors.append(f"skill {s.id}: unknown prerequisite {p}")
    cycle = find_cycle({s.id: list(s.prerequisites) for s in index.skills})
    if cycle:
        errors.append("prerequisite cycle: " + " -> ".join(cycle))

    for path in sorted((root / "lessons").glob("*.yaml")):
        try:
            lesson = LessonSpec.model_validate(_read_yaml(path))
        except ValidationError as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if lesson.id in cur.lessons:
            errors.append(f"{path.name}: duplicate lesson id {lesson.id}")
        if lesson.skill not in skill_ids:
            errors.append(f"{path.name}: unknown skill {lesson.skill}")
        cur.lessons[lesson.id] = lesson

    for path in sorted((root / "exercises").glob("*.yaml")):
        try:
            ex = ExerciseSpec.model_validate(_read_yaml(path))
        except ValidationError as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        if ex.id in cur.exercises:
            errors.append(f"{path.name}: duplicate exercise id {ex.id}")
        for sid in [ex.skill, *ex.extra_skills]:
            if sid not in skill_ids:
                errors.append(f"{path.name}: unknown skill {sid}")
        cur.exercises[ex.id] = ex

    diag_path = root / "diagnostic.yaml"
    if diag_path.exists():
        try:
            cur.diagnostic = DiagnosticSpec.model_validate(_read_yaml(diag_path))
        except ValidationError as exc:
            errors.append(f"diagnostic.yaml: {exc}")
        else:
            if cur.diagnostic.practical_exercise not in cur.exercises:
                errors.append("diagnostic.yaml: practical_exercise not found")
            for q in cur.diagnostic.questions:
                if q.skill not in skill_ids:
                    errors.append(f"diagnostic {q.id}: unknown skill {q.skill}")

    for s in index.skills:
        if s.status != "active":
            continue
        if not any(lesson.skill == s.id for lesson in cur.lessons.values()):
            errors.append(f"active skill {s.id} has no lesson")
        exs = cur.exercises_for(s.id)
        if sum(e.role == "practice" for e in exs) < index.mastery_policy.min_distinct_exercises:
            errors.append(f"active skill {s.id} has fewer practice exercises than the mastery policy needs")
        if index.mastery_policy.require_independent_assessment and not any(e.role == "assessment" for e in exs):
            errors.append(f"active skill {s.id} has no independent-assessment exercise")

    if errors:
        raise ContentError(errors)
    return cur
