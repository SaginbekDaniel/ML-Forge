"use client";

import { useEffect, useState } from "react";

import { Button, CodeBlock, cx, InlineNotice, Spinner, StateBadge, Tag } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Job, TestResultView } from "@/lib/types";

const TERMINAL = new Set(["completed", "failed", "timed_out", "cancelled"]);
export const isTerminal = (job: Job | null) => job !== null && TERMINAL.has(job.status);

export type DisplayState =
  | "empty"
  | "queued"
  | "running"
  | "passed"
  | "partial"
  | "failed"
  | "timeout"
  | "cancelled"
  | "memory"
  | "runner_failed"
  | "ran"
  | "ran_error";

/** Single place that maps a job to the UI state (spec §6.2 state list). */
export function displayState(job: Job | null): DisplayState {
  if (!job) return "empty";
  if (job.status === "queued") return "queued";
  if (job.status === "running") return "running";
  if (job.status === "cancelled") return "cancelled";
  if (job.status === "timed_out") return "timeout";
  if (job.status === "failed") return job.exit_reason === "memory_limit" ? "memory" : "runner_failed";
  const total = job.total ?? 0;
  if (total === 0) return job.exit_reason === "ran" ? "ran" : "ran_error";
  if (job.passed === total) return job.kind === "run" && job.run_output && !job.run_output.passed ? "ran_error" : "passed";
  return (job.passed ?? 0) > 0 ? "partial" : "failed";
}

function RunningLabel({ since }: { since: number | null }) {
  const { t } = useI18n();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(id);
  }, []);
  const seconds = since ? Math.max(0, (now - since) / 1000).toFixed(1) : "0.0";
  return <Spinner label={t("results.running", { s: seconds })} />;
}

export function JobSummary({
  job,
  startedAt,
  onCancel,
  threshold,
}: {
  job: Job | null;
  startedAt: number | null;
  onCancel: () => void;
  threshold: number;
}) {
  const { t, tk } = useI18n();
  const state = displayState(job);
  if (state === "empty") return null;
  if (state === "queued" || state === "running") {
    return (
      <div className="flex items-center justify-between gap-3" aria-live="polite" data-testid="job-summary" data-state={state}>
        {state === "queued" ? <Spinner label={t("results.queued")} /> : <RunningLabel since={startedAt} />}
        <Button size="sm" variant="ghost" onClick={onCancel}>
          {t("practice.cancel")}
        </Button>
      </div>
    );
  }
  const j = job!;
  const tone =
    state === "passed" || state === "ran"
      ? "success"
      : state === "partial"
        ? "warning"
        : state === "cancelled"
          ? "neutral"
          : "danger";
  const title = {
    passed: t("results.passed"),
    partial: t("results.partial", { passed: j.passed ?? 0, total: j.total ?? 0 }),
    failed: t("results.failed", { passed: j.passed ?? 0, total: j.total ?? 0 }),
    timeout: t("results.timeout", { s: j.time_budget_s }),
    cancelled: t("results.cancelled"),
    memory: t("results.memory", { mb: j.memory_limit_mb ?? 256 }),
    runner_failed: t("results.runner_failed"),
    ran: t("results.ran"),
    ran_error: t("results.ran_error"),
  }[state];
  const firstFailing = j.results.find((r) => !r.passed);
  const nextKey =
    state === "partial" && firstFailing && firstFailing.tags?.includes("edge_case") && firstFailing.status === "wrong_answer"
      ? "next.edge"
      : firstFailing
        ? `next.${firstFailing.status}`
        : j.run_output && !j.run_output.passed
          ? `next.${j.run_output.status}`
          : null;

  return (
    <div className="space-y-2" aria-live="polite" data-testid="job-summary" data-state={state}>
      <InlineNotice tone={tone}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="font-medium">{title}</span>
          <span className="flex flex-wrap items-center gap-2 text-xs text-muted">
            {j.edge_cases_total ? <span>{t("results.edge", { a: j.edge_cases_passed ?? 0, b: j.edge_cases_total })}</span> : null}
            {j.duration_ms !== null && <span className="font-mono">{t("results.duration", { ms: j.duration_ms })}</span>}
            <Tag tone="accent">{t("results.verified")}</Tag>
          </span>
        </div>
      </InlineNotice>
      {nextKey && state !== "cancelled" && state !== "runner_failed" && (
        <p className="text-sm text-muted">{tk(nextKey, "")}</p>
      )}
      {j.kind === "run" && <p className="text-xs text-subtle">{t("results.run_only")}</p>}
      {j.kind === "submit" && j.score !== null && (
        <p className="flex flex-wrap items-center gap-2 text-xs text-subtle">
          {j.counts_as_evidence ? (
            <Tag tone="success">{t("results.counts")}</Tag>
          ) : (
            <span>{t("results.not_counts", { pct: Math.round(threshold * 100) })}</span>
          )}
          {j.skill?.state && (
            <span className="inline-flex items-center gap-1">
              {t("results.skill_now", { state: "" })}
              <StateBadge state={j.skill.state} />
            </span>
          )}
        </p>
      )}
    </div>
  );
}

function Field({ label, value }: { label: string; value: string | null | undefined }) {
  if (value === null || value === undefined) return null;
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wide text-subtle">{label}</p>
      <pre className="mt-0.5 overflow-x-auto whitespace-pre-wrap break-words rounded-sm bg-code px-2 py-1 font-mono text-xs">
        {value === "" ? "''" : value}
      </pre>
    </div>
  );
}

export function TestList({ results }: { results: TestResultView[] }) {
  const { t, tk } = useI18n();
  return (
    <ul className="space-y-2" data-testid="test-results">
      {results.map((r, i) => (
        <li
          key={r.test_id}
          data-testid="test-result"
          data-passed={r.passed}
          data-visibility={r.visibility}
          className={cx("rounded-md border px-3 py-2", r.passed ? "border-border" : "border-danger/30 bg-danger-soft")}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-2 text-sm">
              <span aria-hidden className={cx("font-mono text-xs", r.passed ? "text-success" : "text-danger")}>
                {r.passed ? "✓" : "✗"}
              </span>
              <span className="truncate">
                {r.visibility === "hidden" ? `${t("results.hidden")} #${i + 1}` : r.description || r.test_id}
              </span>
            </span>
            <span className="flex items-center gap-2 text-xs text-subtle">
              <span>{tk(`status.${r.status}`, r.status)}</span>
              {r.error_type && r.status === "runtime_error" && <code className="font-mono">{r.error_type}</code>}
              {r.line ? <span>{t("results.line", { n: r.line })}</span> : null}
              {r.duration_ms !== null && <span className="font-mono">{t("results.duration", { ms: Math.round(r.duration_ms) })}</span>}
            </span>
          </div>
          {r.visibility === "public" && !r.passed && (
            <div className="mt-2 grid gap-2 sm:grid-cols-3">
              <Field label={t("practice.input")} value={r.input} />
              <Field label={t("practice.expected")} value={r.expected} />
              <Field label={t("practice.actual")} value={r.actual ?? (r.message ? r.message : null)} />
            </div>
          )}
          {r.visibility === "public" && !r.passed && r.status === "compile_error" && r.message && (
            <p className="mt-2 font-mono text-xs text-danger">{r.message}</p>
          )}
          {r.visibility === "public" && r.stdout && !r.passed && r.stdout.trimEnd() !== (r.actual ?? "").trimEnd() && (
            <div className="mt-2">
              <Field label={t("results.stdout")} value={r.stdout} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

export function ConsoleView({ job }: { job: Job | null }) {
  const { t } = useI18n();
  const out = job?.run_output;
  if (!out) return <p className="text-sm text-muted">{t("results.empty")}</p>;
  return (
    <div className="space-y-2" data-testid="console">
      <CodeBlock code={out.stdout || t("results.no_output")} label={t("results.stdout")} />
      {out.stdout_truncated && <p className="text-xs text-warning">{t("results.truncated")}</p>}
      {(out.stderr || out.actual || out.message) && (
        <CodeBlock code={[out.actual, out.stderr].filter(Boolean).join("\n") || out.message || ""} label={t("results.stderr")} />
      )}
      {!out.passed && out.line ? <p className="text-xs text-subtle">{t("results.line", { n: out.line })}</p> : null}
    </div>
  );
}

export function apiErrorMessage(t: ReturnType<typeof useI18n>["t"], tk: ReturnType<typeof useI18n>["tk"], e: ApiError) {
  return tk(`error.${e.code}`, t("error.generic", { message: e.message }));
}
