"use client";

import { useState, type FormEvent } from "react";

import { apiErrorMessage } from "@/components/practice/results";
import { Button, InlineNotice, Markdown, Spinner, Tag } from "@/components/ui";
import { ApiError, get, post } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Exercise, SubmissionSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function HintsPanel({
  exercise,
  onRevealed,
}: {
  exercise: Exercise;
  onRevealed: (hints: Exercise["hints_revealed"]) => void;
}) {
  const { t, tk } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const revealed = exercise.hints_revealed;
  const next = revealed.length + 1;

  if (exercise.hints_blocked) return <InlineNotice>{tk(`error.${exercise.hints_blocked}`, t("hints.blocked"))}</InlineNotice>;

  async function reveal() {
    setBusy(true);
    try {
      const h = await post<{ level: number; text: string }>(`/exercises/${exercise.id}/hint`, { level: next });
      onRevealed([...revealed, { level: h.level, text: h.text }]);
      setError(null);
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3" data-testid="hints">
      <p className="text-xs text-subtle">{t("hints.intro")}</p>
      <ol className="space-y-2">
        {revealed.map((h) => (
          <li key={h.level} className="rounded-md border border-border bg-surface-2 p-3">
            <p className="mb-1 text-xs font-medium text-subtle">{t("hints.level", { n: h.level })}</p>
            <Markdown className="text-sm">{h.text}</Markdown>
          </li>
        ))}
      </ol>
      {next <= exercise.hints_total ? (
        <Button size="sm" onClick={() => void reveal()} disabled={busy}>
          {t("hints.reveal", { n: next })}
        </Button>
      ) : (
        <p className="text-xs text-subtle">{t("hints.none_left")}</p>
      )}
      {error && <p className="text-sm text-danger">{apiErrorMessage(t, tk, error)}</p>}
    </div>
  );
}

export function AttemptsPanel({
  exerciseId,
  refreshKey,
  onLoadCode,
}: {
  exerciseId: string;
  refreshKey: number;
  onLoadCode: (code: string) => void;
}) {
  const { t, formatDate } = useI18n();
  const { data, loading } = useApi<{ items: SubmissionSummary[] }>(`/exercises/${exerciseId}/attempts?r=${refreshKey}`);
  if (loading && !data) return <Spinner />;
  const items = data?.items ?? [];
  if (items.length === 0) return <p className="text-sm text-muted">{t("attempts.empty")}</p>;

  async function load(id: string) {
    const s = await get<{ source_code: string }>(`/submissions/${id}`);
    onLoadCode(s.source_code);
  }

  return (
    <ul className="divide-y divide-border" data-testid="attempts">
      {items.map((s) => (
        <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
          <span className="flex flex-wrap items-center gap-2">
            <Tag tone={s.kind === "submit" ? "accent" : "neutral"}>{s.kind === "run" ? t("attempts.run") : t("attempts.submit")}</Tag>
            {s.job?.total ? (
              <Tag tone={s.job.passed === s.job.total ? "success" : "danger"}>
                {s.job.passed}/{s.job.total}
              </Tag>
            ) : (
              <Tag>{s.job?.status ?? "—"}</Tag>
            )}
            {s.hint_level > 0 && <span className="text-xs text-warning">{t("attempts.hints", { n: s.hint_level })}</span>}
            <span className="text-xs text-subtle">{formatDate(s.submitted_at)}</span>
          </span>
          <Button size="sm" variant="ghost" onClick={() => void load(s.id)}>
            {t("attempts.load")}
          </Button>
        </li>
      ))}
    </ul>
  );
}

interface MentorReply {
  text: string;
  usage: { input_tokens: number | null; output_tokens: number | null; estimated_cost_usd: number | null };
}

export function MentorPanel({ exerciseId, jobId }: { exerciseId: string; jobId: string | null }) {
  const { t, tk } = useI18n();
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [reply, setReply] = useState<MentorReply | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function send(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      setReply(await post<MentorReply>("/mentor/message", { exercise_id: exerciseId, job_id: jobId, message }));
      setError(null);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3" data-testid="mentor">
      <p className="text-xs text-subtle">{t("mentor.intro")}</p>
      <form onSubmit={send} className="space-y-2">
        <label className="sr-only" htmlFor="mentor-input">
          {t("mentor.title")}
        </label>
        <textarea
          id="mentor-input"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={3}
          maxLength={2000}
          placeholder={t("mentor.placeholder")}
          className="block w-full resize-y rounded-md border border-border bg-surface-2 px-2.5 py-2 text-sm focus:border-accent"
        />
        <Button type="submit" size="sm" disabled={busy || !message.trim()}>
          {busy ? <Spinner /> : t("mentor.send")}
        </Button>
      </form>
      {error && (
        <InlineNotice tone={error.code === "ai_unavailable" ? "neutral" : "danger"}>
          <span role="alert">{apiErrorMessage(t, tk, error)}</span>
        </InlineNotice>
      )}
      {reply && (
        <div className="rounded-md border border-border bg-surface-2 p-3">
          <p className="mb-2 flex flex-wrap items-center gap-2 text-xs text-subtle">
            <Tag tone="warning">{t("mentor.source")}</Tag>
            {reply.usage.input_tokens !== null && (
              <span className="font-mono">
                {t("mentor.cost", {
                  i: reply.usage.input_tokens ?? 0,
                  o: reply.usage.output_tokens ?? 0,
                  c: reply.usage.estimated_cost_usd?.toFixed(4) ?? "?",
                })}
              </span>
            )}
          </p>
          <Markdown className="text-sm">{reply.text}</Markdown>
        </div>
      )}
    </div>
  );
}
