"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, use, useCallback, useEffect, useRef, useState } from "react";

import { CodeEditor } from "@/components/code-editor";
import { AttemptsPanel, HintsPanel, MentorPanel } from "@/components/practice/panels";
import { apiErrorMessage, ConsoleView, isTerminal, JobSummary, TestList } from "@/components/practice/results";
import { RunnerUnavailable } from "@/components/runner-unavailable";
import {
  Button,
  ButtonLink,
  CodeBlock,
  cx,
  ErrorState,
  InlineNotice,
  LoadingBlock,
  Markdown,
  StateBadge,
  Tabs,
  Tag,
} from "@/components/ui";
import { ApiError, get, newRequestId, post, put } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Exercise, Job } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { useMediaQuery } from "@/lib/use-media";

type Mode = "practice" | "independent" | "review" | "diagnostic";
type ResultTab = "tests" | "console" | "attempts" | "hints" | "mentor";
type MobileTab = "task" | "code" | "results";
type DraftStatus = "idle" | "saving" | "saved" | "error";

const PASS_THRESHOLD = 0.85;
const POLL_MS = 400;

function TaskPane({ ex, mode }: { ex: Exercise; mode: Mode }) {
  const { t } = useI18n();
  return (
    <div className="space-y-4">
      <div>
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-lg font-semibold tracking-tight">{ex.title}</h1>
          {ex.progress.solved && <Tag tone="success">{t("practice.solved_badge")}</Tag>}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-subtle">
          <Link href={`/skills/${ex.skill_id}`} className="hover:text-text">
            {ex.skill_title}
          </Link>
          <StateBadge state={ex.skill_state} />
          <span>{t("practice.difficulty", { n: ex.difficulty })}</span>
          <span>{t("common.minutes", { n: ex.estimated_minutes })}</span>
        </p>
      </div>
      {mode !== "practice" && (
        <InlineNotice tone={mode === "diagnostic" ? "accent" : "warning"}>
          <p className="font-medium">{t(`practice.mode.${mode}`)}</p>
          <p className="mt-0.5 text-muted">{t(`practice.mode.${mode}_note`)}</p>
        </InlineNotice>
      )}
      <Markdown>{ex.prompt_md}</Markdown>
      {ex.public_examples.length > 0 && (
        <div>
          <h2 className="mb-2 text-sm font-semibold">{t("practice.examples")}</h2>
          <div className="space-y-2">
            {ex.public_examples.map((e, i) => (
              <div key={i} className="grid gap-2 sm:grid-cols-2">
                <CodeBlock code={e.input} label={t("practice.input")} />
                <CodeBlock code={e.output} label={t("practice.expected")} />
              </div>
            ))}
          </div>
        </div>
      )}
      {ex.hidden_tests_count > 0 && <p className="text-xs text-subtle">{t("practice.hidden_tests", { n: ex.hidden_tests_count })}</p>}
      {ex.lesson_id && mode === "practice" && (
        <Link href={`/learn/${ex.lesson_id}`} className="inline-block text-sm text-accent hover:underline">
          {t("practice.lesson_link")}
        </Link>
      )}
    </div>
  );
}

function PracticeWorkspace({ exerciseId }: { exerciseId: string }) {
  const { t, tk } = useI18n();
  const search = useSearchParams();
  const requestedMode = (search.get("mode") as Mode | null) ?? "practice";
  const assessmentId = search.get("assessment");
  const reviewId = search.get("review");
  const { data: exercise, error, loading, reload, setData } = useApi<Exercise>(`/exercises/${exerciseId}`);
  const wide = useMediaQuery("(min-width: 1200px)");

  const mode: Mode = exercise?.role === "diagnostic" ? "diagnostic" : exercise?.role === "assessment" ? "independent" : requestedMode;
  const guided = mode === "practice";

  // null = untouched: the editor shows the server draft (or starter code) until the learner types.
  const [editedCode, setCode] = useState<string | null>(null);
  const code = editedCode ?? (exercise ? (exercise.draft?.code ?? exercise.starter_code) : null);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [stdin, setStdin] = useState("");
  const [explanation, setExplanation] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [jobStartedAt, setJobStartedAt] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [draftStatus, setDraftStatus] = useState<DraftStatus>("idle");
  const [resultTab, setResultTab] = useState<ResultTab>("tests");
  const [mobileTab, setMobileTab] = useState<MobileTab>("task");
  const [attemptsKey, setAttemptsKey] = useState(0);
  const [assessmentDone, setAssessmentDone] = useState(false);
  const saveTimer = useRef<number | null>(null);
  const pendingSave = useRef<string | null>(null);

  const flushDraft = useCallback(
    async (keepalive = false) => {
      const pending = pendingSave.current;
      if (pending === null) return;
      pendingSave.current = null;
      setDraftStatus("saving");
      try {
        if (keepalive) {
          await fetch(`/api/v1/exercises/${exerciseId}/draft`, {
            method: "PUT",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ code: pending }),
            keepalive: true,
          });
        } else {
          await put(`/exercises/${exerciseId}/draft`, { code: pending });
        }
        setDraftStatus("saved");
      } catch {
        setDraftStatus("error");
      }
    },
    [exerciseId],
  );

  const onCodeChange = useCallback(
    (next: string) => {
      setCode(next);
      pendingSave.current = next;
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      saveTimer.current = window.setTimeout(() => void flushDraft(), 700);
    },
    [flushDraft],
  );

  // Persist the draft when leaving the page or reloading (spec §6.2).
  useEffect(() => {
    const onHide = () => void flushDraft(true);
    window.addEventListener("pagehide", onHide);
    return () => {
      window.removeEventListener("pagehide", onHide);
      onHide();
    };
  }, [flushDraft]);

  // Poll the active job until it reaches a terminal state; the API never blocks on execution.
  useEffect(() => {
    if (!activeJobId) return;
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const j = await get<Job>(`/jobs/${activeJobId}`);
        if (!alive) return;
        setJob(j);
        if (!isTerminal(j)) {
          timer = window.setTimeout(() => void tick(), POLL_MS);
          return;
        }
        setBusy(false);
        setActiveJobId(null);
        setAttemptsKey((k) => k + 1);
        if (j.kind === "submit") {
          if (mode === "independent") setAssessmentDone(true);
          void reload();
        }
      } catch (e) {
        if (!alive) return;
        setSubmitError(e as ApiError);
        setBusy(false);
        setActiveJobId(null);
      }
    };
    void tick();
    return () => {
      alive = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [activeJobId, mode, reload]);

  const execute = useCallback(
    async (kind: "run" | "submit") => {
      if (!exercise || code === null || busy) return;
      if (kind === "submit" && mode === "independent" && assessmentDone) return;
      setBusy(true);
      setSubmitError(null);
      setJob(null);
      setJobStartedAt(Date.now());
      setResultTab(kind === "run" ? "console" : "tests");
      setMobileTab("results");
      if (saveTimer.current) window.clearTimeout(saveTimer.current);
      pendingSave.current = null; // the submission itself stores the code as the draft
      try {
        const res = await post<{ job_id: string }>("/submissions", {
          exercise_id: exercise.id,
          exercise_version: exercise.version,
          source_code: code,
          kind,
          mode,
          client_request_id: newRequestId(),
          assessment_id: mode === "independent" ? assessmentId : undefined,
          review_item_id: mode === "review" && reviewId ? Number(reviewId) : undefined,
          stdin: kind === "run" && stdin ? stdin : undefined,
          explanation: kind === "submit" && explanation.trim() ? explanation : undefined,
        });
        setDraftStatus("saved");
        setActiveJobId(res.job_id);
      } catch (e) {
        setSubmitError(e as ApiError);
        setBusy(false);
      }
    },
    [exercise, code, busy, mode, assessmentDone, assessmentId, reviewId, stdin, explanation],
  );

  async function cancel() {
    if (job) await post(`/jobs/${job.id}/cancel`).catch(() => undefined);
  }

  function resetCode() {
    if (!exercise) return;
    if (window.confirm(t("practice.reset_confirm"))) onCodeChange(exercise.starter_code);
  }

  if (error)
    return (
      <div className="p-4">
        <ErrorState error={error} onRetry={() => void reload()} />
      </div>
    );
  if (loading && !exercise) return <LoadingBlock />;
  if (!exercise || code === null) return <LoadingBlock />;

  const locked = Boolean(exercise.lock);
  const runnerDown = submitError?.code === "runner_unavailable";
  const submitDisabled = busy || locked || (mode === "independent" && assessmentDone);

  const resultTabs: { id: ResultTab; label: string }[] = [
    { id: "tests", label: t("results.tab.tests") },
    { id: "console", label: t("results.tab.console") },
    { id: "attempts", label: t("results.tab.attempts") },
    ...(guided
      ? [
          { id: "hints" as const, label: `${t("results.tab.hints")} ${exercise.hints_revealed.length}/${exercise.hints_total}` },
          { id: "mentor" as const, label: t("results.tab.mentor") },
        ]
      : []),
  ];

  const lockBanner = locked ? (
    <div className="border-b border-border px-4 py-2">
      <InlineNotice tone="warning">{t("practice.locked")}</InlineNotice>
    </div>
  ) : null;

  const toolbar = (
    <div className="flex flex-wrap items-center gap-2 border-b border-border bg-surface px-3 py-2">
      <Button onClick={() => void execute("run")} disabled={busy || locked} title={t("practice.run_hint")}>
        {t("practice.run")}
      </Button>
      <Button variant="primary" onClick={() => void execute("submit")} disabled={submitDisabled} title={t("practice.submit_hint")}>
        {t("practice.submit")}
      </Button>
      <span className="hidden text-xs text-subtle md:inline">
        {t("practice.run_hint")} · {t("practice.submit_hint")}
      </span>
      <span className="ml-auto flex items-center gap-2">
        <span className="text-xs text-subtle" aria-live="polite" data-testid="draft-status">
          {draftStatus === "saving" && t("practice.draft_saving")}
          {draftStatus === "saved" && t("practice.draft_saved")}
          {draftStatus === "error" && <span className="text-danger">{t("practice.draft_error")}</span>}
        </span>
        <Button size="sm" variant="ghost" onClick={resetCode} disabled={busy}>
          {t("practice.reset")}
        </Button>
      </span>
    </div>
  );

  const editor = (
    <div className="flex min-h-0 flex-1 flex-col">
      <p id="editor-help" className="sr-only">
        {t("practice.editor_help")}
      </p>
      <div className="min-h-[280px] flex-1">
        <CodeEditor
          value={code}
          onChange={onCodeChange}
          onRun={() => void execute("run")}
          onSubmit={() => void execute("submit")}
          label={t("practice.editor_label")}
          describedBy="editor-help"
        />
      </div>
      {exercise.execution_mode === "script" && (
        <details className="border-t border-border bg-surface px-3 py-2">
          <summary className="cursor-pointer text-xs text-muted">{t("practice.stdin")}</summary>
          <textarea
            value={stdin}
            onChange={(e) => setStdin(e.target.value)}
            rows={2}
            aria-label={t("practice.stdin")}
            className="mt-2 block w-full rounded-md border border-border bg-code px-2 py-1.5 font-mono text-xs"
          />
        </details>
      )}
      {exercise.type === "debug" && exercise.explain_prompt && (
        <div className="border-t border-border bg-surface px-3 py-2">
          <label className="block text-xs text-muted" htmlFor="explanation">
            {t("practice.explanation")}: {exercise.explain_prompt}
          </label>
          <textarea
            id="explanation"
            value={explanation}
            onChange={(e) => setExplanation(e.target.value)}
            rows={2}
            maxLength={4000}
            className="mt-1 block w-full rounded-md border border-border bg-surface-2 px-2 py-1.5 text-sm"
          />
          <p className="mt-1 text-[11px] text-subtle">{t("practice.explanation_note")}</p>
        </div>
      )}
    </div>
  );

  const results = (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="space-y-2 border-b border-border px-3 py-2.5">
        {runnerDown ? (
          <RunnerUnavailable reason={String(submitError?.details.reason ?? "")} />
        ) : submitError ? (
          <InlineNotice tone="danger">
            <span role="alert">{apiErrorMessage(t, tk, submitError)}</span>
          </InlineNotice>
        ) : (
          <JobSummary job={job} startedAt={jobStartedAt} onCancel={() => void cancel()} threshold={PASS_THRESHOLD} />
        )}
        {mode === "independent" && assessmentDone && job?.kind === "submit" && (
          <InlineNotice tone={job.counts_as_evidence ? "success" : "warning"}>
            {job.counts_as_evidence ? t("assessment.result.passed") : t("assessment.result.failed")}{" "}
            <Link href={`/skills/${exercise.skill_id}`} className="text-accent underline">
              {t("assessment.back_to_skill")}
            </Link>
          </InlineNotice>
        )}
        {mode === "diagnostic" && job?.kind === "submit" && isTerminal(job) && (
          <ButtonLink href="/onboarding" size="sm">
            {t("practice.back_to_onboarding")}
          </ButtonLink>
        )}
        {mode === "practice" && job?.kind === "submit" && job.passed === job.total && exercise.next_exercise_id && (
          <ButtonLink href={`/practice/${exercise.next_exercise_id}`} size="sm" variant="primary">
            {t("practice.next")}
          </ButtonLink>
        )}
      </div>
      <Tabs tabs={resultTabs} value={resultTab} onChange={setResultTab} label={t("practice.results")} className="border-b border-border px-2 py-1.5" />
      <div role="tabpanel" id={`panel-${resultTab}`} aria-labelledby={`tab-${resultTab}`} className="min-h-0 flex-1 overflow-y-auto p-3">
        {resultTab === "tests" &&
          (job && job.results.length > 0 ? <TestList results={job.results} /> : <p className="text-sm text-muted">{t("results.empty")}</p>)}
        {resultTab === "console" && <ConsoleView job={job} />}
        {resultTab === "attempts" && <AttemptsPanel exerciseId={exercise.id} refreshKey={attemptsKey} onLoadCode={onCodeChange} />}
        {resultTab === "hints" && guided && (
          <HintsPanel exercise={exercise} onRevealed={(hints) => setData({ ...exercise, hints_revealed: hints })} />
        )}
        {resultTab === "mentor" && guided && <MentorPanel exerciseId={exercise.id} jobId={job?.id ?? null} />}
      </div>
    </div>
  );

  if (wide) {
    // >= 1200px: 42 / 58 split (spec §6.2)
    return (
      <div className="flex h-dvh flex-col">
        {lockBanner}
        <div className="grid min-h-0 flex-1 grid-cols-[42fr_58fr]">
          <div className="min-h-0 overflow-y-auto border-r border-border px-6 py-5">
            <TaskPane ex={exercise} mode={mode} />
          </div>
          <div className="flex min-h-0 flex-col">
            {toolbar}
            <div className="flex min-h-0 flex-[3] flex-col">{editor}</div>
            <div className="flex min-h-0 flex-[2] flex-col border-t border-border bg-surface">{results}</div>
          </div>
        </div>
      </div>
    );
  }

  // < 1200px: one tabbed column. The editor stays mounted (hidden) to keep undo history.
  return (
    <div className="flex flex-col">
      {lockBanner}
      <Tabs
        tabs={[
          { id: "task", label: t("practice.task") },
          { id: "code", label: t("practice.code") },
          { id: "results", label: t("practice.results") },
        ]}
        value={mobileTab}
        onChange={setMobileTab}
        label={t("practice.task")}
        className="sticky top-12 z-20 border-b border-border bg-bg px-3 py-1.5 lg:top-0"
      />
      {mobileTab === "task" && (
        <div className="px-4 py-4">
          <TaskPane ex={exercise} mode={mode} />
          <Button variant="primary" className="mt-4" onClick={() => setMobileTab("code")}>
            {t("practice.code")}
          </Button>
        </div>
      )}
      <div className={cx(mobileTab === "task" && "hidden", "sticky top-[5.75rem] z-10 lg:top-11")}>{toolbar}</div>
      <div className={cx(mobileTab !== "code" && "hidden", "flex h-[calc(100dvh-9rem)] min-h-[320px] flex-col lg:h-[calc(100dvh-5.5rem)]")}>
        {editor}
      </div>
      {mobileTab === "results" && <div className="flex min-h-[50dvh] flex-col">{results}</div>}
    </div>
  );
}

export default function PracticePage({ params }: { params: Promise<{ exerciseId: string }> }) {
  const { exerciseId } = use(params);
  return (
    <Suspense fallback={<LoadingBlock />}>
      <PracticeWorkspace key={exerciseId} exerciseId={exerciseId} />
    </Suspense>
  );
}
