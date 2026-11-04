"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { useApp } from "@/components/app-context";
import {
  Button,
  ButtonLink,
  CodeBlock,
  cx,
  ErrorState,
  InlineNotice,
  LoadingBlock,
  Markdown,
  Panel,
  Tag,
} from "@/components/ui";
import { ApiError, post } from "@/lib/api";
import { LOCALES, useI18n, type Locale } from "@/lib/i18n";
import type { Diagnostic, Profile } from "@/lib/types";

function ProfileForm() {
  const { setProfile, locale, setLocale } = useApp();
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [goal, setGoal] = useState(120);
  const [days, setDays] = useState(5);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      const tz = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
      const p = await post<Profile>("/profile", {
        display_name: name.trim(),
        locale,
        daily_goal_minutes: goal,
        days_per_week: days,
        timezone: tz,
      });
      setProfile(p);
    } catch (err) {
      setError(err as ApiError);
    } finally {
      setBusy(false);
    }
  }

  const field = "mt-1 block h-9 w-full rounded-md border border-border bg-surface-2 px-2.5 text-base focus:border-accent";
  return (
    <div className="mx-auto max-w-lg">
      <h1 className="text-xl font-semibold">{t("onboarding.title")}</h1>
      <p className="mt-2 text-sm text-muted">{t("onboarding.intro")}</p>
      <form onSubmit={submit} className="mt-6 space-y-4 rounded-lg border border-border bg-surface p-4">
        <label className="block text-sm">
          {t("onboarding.name")}
          <input className={field} required maxLength={80} value={name} onChange={(e) => setName(e.target.value)} autoComplete="nickname" />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="block text-sm">
            {t("onboarding.goal")}
            <select className={field} value={goal} onChange={(e) => setGoal(Number(e.target.value))}>
              {[30, 60, 90, 120, 180].map((m) => (
                <option key={m} value={m}>
                  {t("common.minutes", { n: m })}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            {t("onboarding.days")}
            <select className={field} value={days} onChange={(e) => setDays(Number(e.target.value))}>
              {[3, 4, 5, 6, 7].map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="block text-sm">
          {t("onboarding.locale")}
          <select className={field} value={locale} onChange={(e) => setLocale(e.target.value as Locale)}>
            {LOCALES.map((l) => (
              <option key={l} value={l}>
                {l === "ru" ? "Русский" : "English"}
              </option>
            ))}
          </select>
        </label>
        {error && <ErrorState error={error} />}
        <Button type="submit" variant="primary" disabled={busy || !name.trim()}>
          {t("onboarding.create")}
        </Button>
      </form>
    </div>
  );
}

function DiagnosticStep() {
  const { t } = useI18n();
  const { reloadProfile } = useApp();
  const router = useRouter();
  const [diag, setDiag] = useState<Diagnostic | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    post<Diagnostic>("/diagnostic/start")
      .then((d) => {
        setDiag(d);
        setAnswers(Object.fromEntries(Object.entries(d.answers).map(([k, v]) => [k, v.answer])));
      })
      .catch((e: ApiError) => setError(e));
  }, []);

  async function save(questionId: string, answer: string) {
    setAnswers((a) => ({ ...a, [questionId]: answer }));
    if (!diag || !answer.trim()) return;
    try {
      await post(`/diagnostic/${diag.id}/answer`, { question_id: questionId, answer });
    } catch (e) {
      setError(e as ApiError);
    }
  }

  async function finish() {
    if (!diag) return;
    setBusy(true);
    try {
      setDiag(await post<Diagnostic>(`/diagnostic/${diag.id}/complete`));
      await reloadProfile();
    } catch (e) {
      setError(e as ApiError);
    } finally {
      setBusy(false);
    }
  }

  async function skip() {
    await post("/onboarding/skip");
    await reloadProfile();
    router.push("/roadmap");
  }

  if (error && !diag) return <ErrorState error={error} />;
  if (!diag) return <LoadingBlock />;
  if (diag.status === "completed" && diag.result) return <DiagnosticResult diag={diag} />;

  const answered = diag.questions.filter((q) => (answers[q.id] ?? "").trim()).length;
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold">{t("onboarding.diag.title")}</h1>
        <p className="mt-2 text-sm text-muted">{t("onboarding.diag.intro")}</p>
      </div>
      <ol className="space-y-3">
        {diag.questions.map((q, i) => (
          <li key={q.id} className="rounded-lg border border-border bg-surface p-4">
            <div className="mb-2 flex items-start gap-2">
              <span className="font-mono text-xs text-subtle">{i + 1}.</span>
              <Markdown className="text-sm">{q.prompt_md}</Markdown>
            </div>
            {q.type === "self_assessment" && q.options ? (
              <fieldset>
                <legend className="sr-only">{q.prompt_md}</legend>
                <div className="flex flex-wrap gap-2">
                  {q.options.map((opt) => (
                    <label
                      key={opt}
                      className={cx(
                        "inline-flex h-8 cursor-pointer items-center rounded-md border px-2.5 text-sm",
                        answers[q.id] === opt ? "border-accent bg-accent-soft text-text" : "border-border text-muted hover:text-text",
                      )}
                    >
                      <input
                        type="radio"
                        className="sr-only"
                        name={q.id}
                        value={opt}
                        checked={answers[q.id] === opt}
                        onChange={() => void save(q.id, opt)}
                      />
                      {t(`onboarding.diag.self.${opt as "never_seen" | "seen_before" | "confident"}`)}
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : (
              <div className="space-y-2">
                {q.code && <CodeBlock code={q.code} />}
                <label className="block">
                  <span className="sr-only">{t("onboarding.diag.predict_placeholder")}</span>
                  <input
                    className="block h-9 w-full rounded-md border border-border bg-surface-2 px-2.5 font-mono text-sm focus:border-accent"
                    placeholder={t("onboarding.diag.predict_placeholder")}
                    defaultValue={answers[q.id] ?? ""}
                    onBlur={(e) => void save(q.id, e.target.value)}
                    autoComplete="off"
                    spellCheck={false}
                  />
                </label>
              </div>
            )}
          </li>
        ))}
      </ol>
      {diag.practical_exercise_id && (
        <Panel title={t("onboarding.diag.practical")}>
          <p className="text-sm text-muted">{t("onboarding.diag.practical_body")}</p>
          <ButtonLink href={`/practice/${diag.practical_exercise_id}?mode=diagnostic`} className="mt-3" size="sm">
            {t("onboarding.diag.open_practical")}
          </ButtonLink>
        </Panel>
      )}
      {error && <ErrorState error={error} />}
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" onClick={() => void finish()} disabled={busy}>
          {t("onboarding.diag.finish")}
        </Button>
        <Button variant="ghost" onClick={() => void skip()}>
          {t("onboarding.diag.skip")}
        </Button>
        <span className="text-xs text-subtle">{t("onboarding.diag.answered", { n: answered, total: diag.questions.length })}</span>
      </div>
    </div>
  );
}

function DiagnosticResult({ diag }: { diag: Diagnostic }) {
  const { t } = useI18n();
  const result = diag.result!;
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-semibold">{t("onboarding.result.title")}</h1>
      <ul className="space-y-2">
        {result.skills.map((s) => (
          <li key={s.skill_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border bg-surface px-4 py-3">
            <div>
              <p className="text-sm font-medium">{s.skill_title}</p>
              <p className="mt-0.5 text-xs text-subtle">
                {s.checks_correct}/{s.checks_total} ·{" "}
                {s.self_report ? t(`onboarding.diag.self.${s.self_report as "never_seen" | "seen_before" | "confident"}`) : "—"}
              </p>
            </div>
            <Tag tone={s.recommendation === "try_assessment_early" ? "success" : "accent"}>
              {t(`onboarding.result.rec.${s.recommendation}`)}
            </Tag>
          </li>
        ))}
      </ul>
      <Panel title={t("onboarding.diag.title")}>
        <ul className="space-y-1 text-sm">
          {diag.questions
            .filter((q) => q.type === "predict_output")
            .map((q) => {
              const a = diag.answers[q.id];
              return (
                <li key={q.id} className="flex flex-wrap gap-2">
                  <span className="font-mono text-xs text-subtle">{q.id}</span>
                  {a?.correct ? (
                    <span className="text-success">{t("onboarding.result.correct")}</span>
                  ) : (
                    <span className="text-danger">{t("onboarding.result.incorrect", { answer: result.answer_key[q.id] ?? "" })}</span>
                  )}
                </li>
              );
            })}
        </ul>
        {result.practical?.attempted && (
          <p className="mt-3 text-sm">
            {t("onboarding.diag.practical_done", { passed: result.practical.passed ?? 0, total: result.practical.total ?? 0 })}
          </p>
        )}
      </Panel>
      <InlineNotice>{t("onboarding.result.note")}</InlineNotice>
      <ButtonLink href="/roadmap" variant="primary">
        {t("onboarding.result.go")}
      </ButtonLink>
    </div>
  );
}

export default function OnboardingPage() {
  const { profile } = useApp();
  return profile ? <DiagnosticStep /> : <ProfileForm />;
}
