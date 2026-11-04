"""Pydantic schemas for versioned curriculum content stored in Git (spec §4.2, §11)."""

from __future__ import annotations

import ast
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ID_RE = re.compile(r"^[a-z0-9_]+(\.[a-z0-9_]+)*$")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Track(Strict):
    id: str
    title: str
    title_en: str | None = None


class SkillSpec(Strict):
    id: str
    track: str
    title: str
    title_en: str | None = None
    description: str = ""
    prerequisites: list[str] = Field(default_factory=list)
    status: Literal["active", "planned"] = "active"
    version: int = 1

    @field_validator("id")
    @classmethod
    def _id(cls, v: str) -> str:
        if not ID_RE.match(v):
            raise ValueError(f"invalid skill id {v!r}")
        return v


class MasteryPolicy(Strict):
    pass_threshold: float = 0.85
    min_distinct_exercises: int = 2
    require_no_hint_solve: bool = True
    require_independent_assessment: bool = True
    review_intervals_days: list[int] = Field(default_factory=lambda: [1, 3, 7, 14, 30])


class CurriculumIndex(Strict):
    version: int
    tracks: list[Track]
    skills: list[SkillSpec]
    mastery_policy: MasteryPolicy = Field(default_factory=MasteryPolicy)


class Example(Strict):
    title: str
    code: str
    output: str = ""
    note_md: str = ""


class CommonMistake(Strict):
    code: str
    problem_md: str
    fix_md: str
    output: str | None = None


class CheckQuestion(Strict):
    """Predict-the-output question: the answer is checked by exact (normalised)
    match and the answer itself is verified by running ``code`` in the sandbox."""

    id: str
    prompt_md: str
    code: str
    answer: str
    explanation_md: str


class Term(Strict):
    en: str
    ru: str


class Resource(Strict):
    title: str
    url: str


class LessonSpec(Strict):
    id: str
    version: int
    skill: str
    title: str
    estimated_minutes: int = 20
    summary: str
    explanation_md: str
    analogy_md: str
    definition_md: str
    examples: list[Example] = Field(min_length=2)
    common_mistake: CommonMistake
    check_questions: list[CheckQuestion] = Field(min_length=2, max_length=4)
    recap_md: str
    terms: list[Term] = Field(default_factory=list)
    resources: list[Resource] = Field(default_factory=list)


class TestSpec(Strict):
    __test__ = False  # not a pytest test class

    id: str
    kind: Literal["call", "stdout"]
    visibility: Literal["public", "hidden"] = "public"
    description: str = ""
    call: str | None = None
    expected: str | None = None
    raises: str | None = None
    stdin: str | None = None
    expected_stdout: str | None = None
    compare: Literal["exact", "float", "unordered"] = "exact"
    abs_tol: float = 1e-9
    rel_tol: float = 1e-9
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _shape(self) -> TestSpec:
        if self.kind == "call":
            if not self.call:
                raise ValueError(f"test {self.id}: call tests need 'call'")
            if self.expected is None and self.raises is None:
                raise ValueError(f"test {self.id}: call tests need 'expected' or 'raises'")
            if self.expected is not None:
                try:
                    ast.literal_eval(self.expected)
                except (ValueError, SyntaxError) as exc:
                    raise ValueError(f"test {self.id}: expected must be a Python literal: {exc}") from exc
            try:
                ast.parse(self.call, mode="eval")
            except SyntaxError as exc:
                raise ValueError(f"test {self.id}: call is not an expression: {exc}") from exc
        else:
            if self.expected_stdout is None:
                raise ValueError(f"test {self.id}: stdout tests need 'expected_stdout'")
        return self


class WrongSolution(Strict):
    name: str
    code: str
    why: str


class PublicExample(Strict):
    input: str
    output: str


class ExerciseSpec(Strict):
    id: str
    version: int
    title: str
    skill: str
    extra_skills: list[str] = Field(default_factory=list)
    type: Literal["write_code", "debug", "refactor"]
    role: Literal["practice", "assessment", "diagnostic"] = "practice"
    difficulty: int = Field(ge=1, le=5)
    estimated_minutes: int = 10
    position: int = 0
    language: Literal["python"] = "python"
    execution_mode: Literal["function", "script"] = "function"
    prompt_md: str
    starter_code: str
    public_examples: list[PublicExample] = Field(default_factory=list)
    tests: list[TestSpec] = Field(min_length=3)
    hints: list[str] = Field(min_length=3, max_length=3)
    solution: str
    wrong_solutions: list[WrongSolution] = Field(min_length=1, max_length=3)
    explain_prompt: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str = "ML Forge original"
    license: str = "CC BY 4.0"
    review_status: Literal["draft", "reviewed"] = "draft"

    @model_validator(mode="after")
    def _tests(self) -> ExerciseSpec:
        ids = [t.id for t in self.tests]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{self.id}: duplicate test ids")
        if not any(t.visibility == "public" for t in self.tests):
            raise ValueError(f"{self.id}: needs at least one public test")
        if self.role != "diagnostic" and not any(t.visibility == "hidden" for t in self.tests):
            raise ValueError(f"{self.id}: needs at least one hidden test")
        if not any("edge_case" in t.tags for t in self.tests):
            raise ValueError(f"{self.id}: needs at least one edge_case test")
        return self


class DiagnosticQuestion(Strict):
    id: str
    type: Literal["self_assessment", "predict_output"]
    skill: str
    prompt_md: str
    code: str | None = None
    answer: str | None = None
    options: list[str] | None = None

    @model_validator(mode="after")
    def _shape(self) -> DiagnosticQuestion:
        if self.type == "predict_output" and (self.code is None or self.answer is None):
            raise ValueError(f"{self.id}: predict_output needs code and answer")
        return self


class DiagnosticSpec(Strict):
    version: int
    questions: list[DiagnosticQuestion]
    practical_exercise: str
