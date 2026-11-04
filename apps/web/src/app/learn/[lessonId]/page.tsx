"use client";

import Link from "next/link";
import { use, useState, type FormEvent } from "react";

import { PageContainer } from "@/components/app-shell";
import {
  Button,
  ButtonLink,
  CodeBlock,
  ErrorState,
  InlineNotice,
  LoadingBlock,
  Markdown,
  Panel,
  StateBadge,
  Tag,
} from "@/components/ui";
import { ApiError, post } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Lesson } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface CheckResult {
  correct: boolean;
  expected: string;
  explanation_md: string;
}

function CheckQuestion({ lessonId, q, index }: { lessonId: string; q: Lesson["content"]["check_questions"][number]; index: number }) {
  const { t } = useI18n();
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<CheckResult | null>(null);
  const [error, setError] = useState<ApiError | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    try {
      setResult(await post<CheckResult>(`/lessons/${lessonId}/check`, { question_id: q.id, answer }));
      setError(null);
    } catch (err) {
      setError(err as ApiError);
    }
  }

  const inputId = `check-${q.id}`;
  return (
    <li className="rounded-md border border-border p-3">
      <div className="flex gap-2">
        <span className="font-mono text-xs text-subtle">{index + 1}.</span>
        <Markdown className="text-sm">{q.prompt_md}</Markdown>
      </div>
      <div className="mt-2">
        <CodeBlock code={q.code} />
      </div>
      <form onSubmit={submit} className="mt-2 flex flex-wrap items-center gap-2">
        <label htmlFor={inputId} className="sr-only">
          {t("onboarding.diag.predict_placeholder")}
        </label>
        <input
          id={inputId}
          value={answer}
          onChange={(e) => setAnswer(e.target.value)}
          disabled={result !== null}
          placeholder={t("onboarding.diag.predict_placeholder")}
          autoComplete="off"
          spellCheck={false}
          className="h-8 min-w-0 flex-1 rounded-md border border-border bg-surface-2 px-2.5 font-mono text-sm focus:border-accent"
        />
        <Button type="submit" size="sm" disabled={!answer.trim() || result !== null}>
          {t("lesson.check_submit")}
        </Button>
      </form>
      {error && <p className="mt-2 text-sm text-danger">{error.message}</p>}
      {result && (
        <div className="mt-2 space-y-1.5" role="status">
          {result.correct ? (
            <Tag tone="success">{t("lesson.check_correct")}</Tag>
          ) : (
            <p className="text-sm">
              <span className="text-danger">{t("lesson.check_wrong")}</span>{" "}
              <code className="rounded-sm bg-surface-3 px-1 font-mono text-xs">{result.expected}</code>
            </p>
          )}
          <Markdown className="text-sm text-muted">{result.explanation_md}</Markdown>
        </div>
      )}
    </li>
  );
}

export default function LessonPage({ params }: { params: Promise<{ lessonId: string }> }) {
  const { lessonId } = use(params);
  const { t } = useI18n();
  const { data, error, loading, reload, setData } = useApi<Lesson>(`/lessons/${lessonId}`);
  const [marking, setMarking] = useState(false);

  if (error)
    return (
      <PageContainer>
        <ErrorState error={error} onRetry={() => void reload()} />
      </PageContainer>
    );
  if (loading || !data) return <LoadingBlock />;
  const c = data.content;
  const locked = data.skill_state === "locked" || data.skill_state === "planned";

  async function markRead() {
    if (!data) return;
    setMarking(true);
    try {
      await post(`/lessons/${data.id}/complete`);
      setData({ ...data, completed: true });
    } finally {
      setMarking(false);
    }
  }

  return (
    <PageContainer>
      <nav className="mb-3 text-xs text-subtle">
        <Link href="/roadmap" className="hover:text-text">
          {t("nav.roadmap")}
        </Link>{" "}
        / <Link href={`/skills/${data.skill_id}`} className="hover:text-text">{data.skill_title}</Link>
      </nav>
      <header className="mb-5">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight">{data.title}</h1>
          <StateBadge state={data.skill_state} />
        </div>
        <p className="mt-1 text-sm text-muted">{c.summary}</p>
        <div className="mt-2 flex flex-wrap gap-2 text-xs text-subtle">
          <span>{t("common.minutes", { n: data.estimated_minutes })}</span>
          {data.examples_verified && <Tag tone="success">{t("lesson.verified")}</Tag>}
        </div>
      </header>

      {locked && (
        <div className="mb-4">
          <InlineNotice tone="warning">{t("lesson.locked_banner")}</InlineNotice>
        </div>
      )}

      <article className="space-y-6">
        <section aria-labelledby="sec-explanation">
          <h2 id="sec-explanation" className="mb-2 text-base font-semibold">{t("lesson.explanation")}</h2>
          <Markdown>{c.explanation_md}</Markdown>
        </section>

        <div className="grid gap-4 md:grid-cols-2">
          <Panel title={t("lesson.analogy")}>
            <Markdown className="text-sm">{c.analogy_md}</Markdown>
          </Panel>
          <Panel title={t("lesson.definition")}>
            <Markdown className="text-sm">{c.definition_md}</Markdown>
          </Panel>
        </div>

        <section aria-labelledby="sec-examples">
          <h2 id="sec-examples" className="mb-2 text-base font-semibold">{t("lesson.examples")}</h2>
          <div className="space-y-4">
            {c.examples.map((ex) => (
              <div key={ex.title} className="space-y-2">
                <h3 className="text-sm font-medium">{ex.title}</h3>
                <CodeBlock code={ex.code} />
                {ex.output && <CodeBlock code={ex.output} label={t("lesson.output")} />}
                {ex.note_md && <Markdown className="text-sm text-muted">{ex.note_md}</Markdown>}
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="sec-mistake" className="rounded-lg border border-warning/30 bg-warning-soft p-4">
          <h2 id="sec-mistake" className="mb-2 text-base font-semibold">{t("lesson.mistake")}</h2>
          <CodeBlock code={c.common_mistake.code} />
          {c.common_mistake.output !== null && (
            <div className="mt-2">
              <CodeBlock code={c.common_mistake.output} label={t("lesson.output")} />
            </div>
          )}
          <Markdown className="mt-2 text-sm">{c.common_mistake.problem_md}</Markdown>
          <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-subtle">{t("lesson.fix")}</p>
          <Markdown className="text-sm">{c.common_mistake.fix_md}</Markdown>
        </section>

        <section aria-labelledby="sec-check">
          <h2 id="sec-check" className="text-base font-semibold">{t("lesson.check")}</h2>
          <p className="mb-3 mt-1 text-sm text-muted">{t("lesson.check_intro")}</p>
          <ol className="space-y-3">
            {c.check_questions.map((q, i) => (
              <CheckQuestion key={q.id} lessonId={data.id} q={q} index={i} />
            ))}
          </ol>
        </section>

        <Panel title={t("lesson.recap")}>
          <Markdown className="text-sm">{c.recap_md}</Markdown>
        </Panel>

        <div className="grid gap-4 md:grid-cols-2">
          {c.terms.length > 0 && (
            <Panel title={t("lesson.terms")}>
              <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                {c.terms.map((term) => (
                  <div key={term.en} className="contents">
                    <dt className="font-mono text-xs text-accent">{term.en}</dt>
                    <dd className="text-muted">{term.ru}</dd>
                  </div>
                ))}
              </dl>
            </Panel>
          )}
          {c.resources.length > 0 && (
            <Panel title={t("lesson.resources")}>
              <ul className="space-y-1 text-sm">
                {c.resources.map((r) => (
                  <li key={r.url}>
                    <a href={r.url} target="_blank" rel="noreferrer noopener" className="text-accent hover:underline">
                      {r.title}
                    </a>
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>

        <Panel title={t("lesson.practice")}>
          <ul className="divide-y divide-border">
            {data.exercises.map((ex) => (
              <li key={ex.id} className="flex items-center justify-between gap-2 py-2 first:pt-0 last:pb-0">
                <Link href={`/practice/${ex.id}`} className="min-w-0 truncate text-sm hover:text-accent">
                  {ex.title}
                </Link>
                <span className="flex items-center gap-2">
                  <span className="text-xs text-subtle">{t("practice.difficulty", { n: ex.difficulty })}</span>
                  {ex.solved && <Tag tone="success">{t("practice.solved_badge")}</Tag>}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-4">
          {data.completed ? (
            <Tag tone="success">{t("lesson.read")}</Tag>
          ) : (
            <Button onClick={() => void markRead()} disabled={marking}>
              {t("lesson.mark_read")}
            </Button>
          )}
          {data.exercises[0] && !locked && (
            <ButtonLink href={`/practice/${data.exercises[0].id}`} variant="primary">
              {t("dashboard.next.exercise")}
            </ButtonLink>
          )}
          <span className="text-xs text-subtle">{t("lesson.read_note")}</span>
        </div>
      </article>
    </PageContainer>
  );
}
