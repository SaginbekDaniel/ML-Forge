// Response shapes of the ML Forge API (mirrors services/api routes).

export type SkillStateName = "planned" | "locked" | "available" | "in_progress" | "mastered" | "needs_review";

export interface Criterion {
  id: "distinct_exercises" | "no_hint_solve" | "independent_assessment" | string;
  met: boolean;
  current: number;
  required: number;
  note: string;
}

export interface Profile {
  id: string;
  display_name: string;
  locale: "ru" | "en";
  daily_goal_minutes: number;
  days_per_week: number;
  timezone: string;
  onboarding_completed: boolean;
}

export interface SkillSummary {
  id: string;
  track: string;
  title: string;
  title_en: string | null;
  description: string;
  status: "active" | "planned";
  state: SkillStateName;
  mastery_score: number;
  criteria: Criterion[];
  mastered_at: string | null;
  next_review_at: string | null;
  prerequisites: string[];
  lesson_id: string | null;
  lesson_completed: boolean;
  exercises_total: number;
  exercises_solved: number;
}

export interface Roadmap {
  tracks: { id: string; skills: SkillSummary[] }[];
  policy: { pass_threshold: number; min_distinct_exercises: number; review_intervals_days: number[] };
}

export interface Evidence {
  id: number;
  source_type: string;
  verification: string;
  exercise_id: string | null;
  score: number;
  hint_level: number;
  created_at: string;
  counts: boolean;
}

export interface SkillDetail extends SkillSummary {
  hint_dependency: number | null;
  failure_tags: Record<string, number>;
  prerequisite_details: { id: string; title: string; state: SkillStateName }[];
  exercises: {
    id: string;
    title: string;
    type: string;
    difficulty: number;
    estimated_minutes: number;
    attempts: number;
    best_score: number | null;
    solved: boolean;
    solved_without_hints: boolean;
    hints_used: number;
  }[];
  assessment_variants: number;
  assessments: { id: string; status: string; exercise_id: string; variant_seen: boolean; started_at: string }[];
  evidence: Evidence[];
  reviews: { id: number; status: string; due_at: string; interval_days: number; last_outcome: string | null }[];
}

export interface PublicTest {
  id: string;
  kind: "call" | "stdout";
  description: string;
  tags: string[];
  call?: string;
  expected?: string;
  stdin?: string;
  expected_stdout?: string;
}

export interface Exercise {
  id: string;
  version: number;
  title: string;
  type: "write_code" | "debug" | "refactor";
  role: "practice" | "assessment" | "diagnostic";
  difficulty: number;
  estimated_minutes: number;
  skill_id: string;
  skill_title: string;
  skill_state: SkillStateName;
  lesson_id: string | null;
  active: boolean;
  lock: { reason: string } | null;
  execution_mode: "function" | "script";
  prompt_md: string;
  starter_code: string;
  public_examples: { input: string; output: string }[];
  public_tests: PublicTest[];
  hidden_tests_count: number;
  hints_total: number;
  hints_revealed: { level: number; text: string }[];
  hints_blocked: string | null;
  explain_prompt: string | null;
  draft: { code: string; updated_at: string } | null;
  progress: { attempts: number; best_score: number | null; solved: boolean; solved_without_hints: boolean };
  next_exercise_id: string | null;
}

export type JobStatus = "queued" | "running" | "completed" | "failed" | "timed_out" | "cancelled";

export interface TestResultView {
  test_id: string;
  visibility: "public" | "hidden";
  passed: boolean;
  status: string;
  error_type: string | null;
  duration_ms: number | null;
  description?: string;
  tags?: string[];
  input?: string | null;
  expected?: string | null;
  actual?: string | null;
  stdout?: string | null;
  stderr?: string | null;
  stdout_truncated?: boolean;
  message?: string | null;
  line?: number | null;
}

export interface Job {
  id: string;
  status: JobStatus;
  exit_reason: string | null;
  passed: number | null;
  total: number | null;
  score: number | null;
  error_type: string | null;
  edge_cases_passed: number | null;
  edge_cases_total: number | null;
  duration_ms: number | null;
  max_test_ms: number | null;
  submission_id: string;
  exercise_id: string;
  kind: "run" | "submit";
  mode: string;
  memory_limit_mb: number | null;
  time_budget_s: number;
  results: TestResultView[];
  run_output: TestResultView | null;
  skill?: { id: string; state: SkillStateName; criteria: Criterion[] } | null;
  counts_as_evidence?: boolean;
}

export interface SubmissionSummary {
  id: string;
  exercise_id: string;
  kind: "run" | "submit";
  mode: string;
  hint_level: number;
  submitted_at: string;
  job: Pick<Job, "id" | "status" | "exit_reason" | "passed" | "total" | "score" | "error_type" | "duration_ms"> | null;
}

export interface Rate {
  numerator: number;
  denominator: number;
  value: number | null;
  sufficient: boolean;
}

export interface Insights {
  independent_accuracy: Rate;
  hint_dependency: Rate;
  review_recall: Rate;
  top_errors: { error_type: string; count: number }[];
}

export type NextStep =
  | { type: "review"; review_id: number; skill_id: string }
  | { type: "lesson"; lesson_id: string; skill_id: string; title: string }
  | { type: "exercise" | "exercise_no_hints"; exercise_id: string; skill_id: string; title: string }
  | { type: "assessment"; skill_id: string; title: string };

export interface Dashboard {
  profile: { display_name: string; daily_goal_minutes: number; onboarding_completed: boolean };
  today: { active_minutes: number; goal_minutes: number; submissions: number; exercises_solved: number };
  current_skill: { id: string; title: string; state: SkillStateName; criteria: Criterion[] } | null;
  next_step: NextStep | null;
  reviews_due: number;
  skill_counts: Record<string, number>;
  recent_attempts: {
    submission_id: string;
    exercise_id: string;
    kind: string;
    mode: string;
    submitted_at: string;
    status: JobStatus | null;
    passed: number | null;
    total: number | null;
  }[];
  insights: Insights;
  runner: { available: boolean; reason: string };
}

export interface Lesson {
  id: string;
  version: number;
  skill_id: string;
  skill_title: string;
  skill_state: SkillStateName;
  title: string;
  estimated_minutes: number;
  examples_verified: boolean;
  completed: boolean;
  content: {
    summary: string;
    explanation_md: string;
    analogy_md: string;
    definition_md: string;
    examples: { title: string; code: string; output: string; note_md: string }[];
    common_mistake: { code: string; problem_md: string; fix_md: string; output: string | null };
    check_questions: { id: string; prompt_md: string; code: string }[];
    recap_md: string;
    terms: { en: string; ru: string }[];
    resources: { title: string; url: string }[];
  };
  exercises: { id: string; title: string; difficulty: number; type: string; solved: boolean }[];
}

export interface ReviewItem {
  id: number;
  skill_id: string;
  skill_title: string;
  due_at: string;
  interval_days: number;
  step: number;
  status: string;
  exercise_id: string | null;
  started_at: string | null;
  last_outcome: string | null;
}

export interface Assessment {
  id: string;
  skill_id: string;
  exercise_id: string;
  exercise_version: number;
  variant_seen: boolean;
  status: "active" | "passed" | "failed" | "abandoned";
}

export interface DiagnosticQuestion {
  id: string;
  type: "self_assessment" | "predict_output";
  skill_id: string;
  prompt_md: string;
  code?: string;
  options?: string[];
}

export interface Diagnostic {
  id: string;
  status: "in_progress" | "completed";
  questions: DiagnosticQuestion[];
  answers: Record<string, { answer: string; correct: boolean | null }>;
  practical_exercise_id: string | null;
  result: {
    skills: {
      skill_id: string;
      skill_title: string;
      recommendation: "try_assessment_early" | "start_with_lesson";
      self_report: string | null;
      checks_correct: number;
      checks_total: number;
    }[];
    recommended_start_skill: string | null;
    answer_key: Record<string, string>;
    practical?: { attempted: boolean; passed: number | null; total: number | null } | null;
  } | null;
}

export interface AIStatus {
  available: boolean;
  reason: string | null;
  model: string;
  configured: boolean;
  enabled: boolean;
  usage_today: { requests: number; estimated_cost_usd: number };
  limits: { requests_per_day: number; budget_usd_per_day: number };
}

export interface AppSettings {
  settings: {
    ai_enabled: boolean;
    ai_daily_request_limit: number;
    ai_daily_budget_usd: number;
    ai_max_context_chars: number;
    send_code_to_ai: boolean;
  };
  ai: AIStatus;
}

export interface Health {
  status: string;
  database: string;
  runner: { available: boolean; reason: string; image: string; limits: { time_s: number; memory_mb: number } };
  ai: { configured: boolean };
}
