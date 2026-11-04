"use client";

import Link from "next/link";

import { useApp } from "@/components/app-context";
import { PageContainer } from "@/components/app-shell";
import { RunnerUnavailable } from "@/components/runner-unavailable";
import { ButtonLink, CriteriaList, ErrorState, LoadingBlock, PageHeader, Panel, Stat, StateBadge, Tag } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { Dashboard, NextStep, Rate } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function nextHref(step: NextStep): string {
  switch (step.type) {
    case "lesson":
      return `/learn/${step.lesson_id}`;
    case "exercise":
    case "exercise_no_hints":
      return `/practice/${step.exercise_id}`;
    case "assessment":
      return `/assessment/${step.skill_id}`;
    case "review":
      return "/review";
  }
}

function RateValue({ rate }: { rate: Rate }) {
  const { t, formatNumber } = useI18n();
  if (!rate.sufficient || rate.value === null) {
    return (
      <span className="text-sm font-normal text-subtle">
        {t("common.insufficient_data")} <span className="font-mono text-xs">({t("dashboard.insight.sample", { n: rate.denominator })})</span>
      </span>
    );
  }
  return (
    <span>
      {formatNumber(rate.value, { style: "percent", maximumFractionDigits: 0 })}{" "}
      <span className="font-mono text-xs font-normal text-subtle">
        {rate.numerator}/{rate.denominator}
      </span>
    </span>
  );
}

export default function DashboardPage() {
  const { profile } = useApp();
  const { t, tk, formatDate } = useI18n();
  const { data, error, loading, reload } = useApi<Dashboard>(profile?.onboarding_completed ? "/dashboard" : null);

  if (!profile?.onboarding_completed) return <LoadingBlock />;
  if (error)
    return (
      <PageContainer>
        <ErrorState error={error} onRetry={() => void reload()} />
      </PageContainer>
    );
  if (loading || !data) return <LoadingBlock />;

  const step = data.next_step;
  const goalPct = Math.min(100, Math.round((data.today.active_minutes / Math.max(1, data.today.goal_minutes)) * 100));

  return (
    <PageContainer wide>
      <PageHeader title={t("dashboard.greeting", { name: data.profile.display_name })} />
      {!data.runner.available && (
        <div className="mb-4">
          <RunnerUnavailable reason={data.runner.reason} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={t("dashboard.next")} className="lg:col-span-2">
          {step ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs uppercase tracking-wide text-subtle">{t(`dashboard.next.${step.type}`)}</p>
                <p className="mt-0.5 truncate text-lg font-semibold">
                  {"title" in step ? step.title : (data.current_skill?.title ?? step.skill_id)}
                </p>
              </div>
              <ButtonLink href={nextHref(step)} variant="primary">
                {t("common.continue")}
              </ButtonLink>
            </div>
          ) : (
            <p className="text-sm text-muted">{t("dashboard.next.none")}</p>
          )}
          {data.current_skill && (
            <div className="mt-4 border-t border-border pt-4">
              <div className="mb-2 flex flex-wrap items-center gap-2">
                <span className="text-xs text-subtle">{t("dashboard.current")}:</span>
                <Link href={`/skills/${data.current_skill.id}`} className="text-sm font-medium hover:text-accent">
                  {data.current_skill.title}
                </Link>
                <StateBadge state={data.current_skill.state} />
              </div>
              <p className="mb-2 text-xs text-subtle">{t("dashboard.requirements")}</p>
              <CriteriaList criteria={data.current_skill.criteria} />
            </div>
          )}
        </Panel>

        <Panel title={t("dashboard.today")}>
          <dl className="grid grid-cols-3 gap-3 lg:grid-cols-1">
            <Stat
              label={t("dashboard.today.active")}
              value={`${data.today.active_minutes} / ${data.today.goal_minutes} ${t("common.min_short")}`}
            />
            <Stat label={t("dashboard.today.submissions")} value={data.today.submissions} />
            <Stat label={t("dashboard.today.solved")} value={data.today.exercises_solved} />
          </dl>
          <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-3" aria-hidden>
            <div className="h-full bg-accent" style={{ width: `${goalPct}%` }} />
          </div>
          <p className="mt-2 text-xs text-subtle">{t("dashboard.today.active_hint")}</p>
        </Panel>

        <Panel title={t("dashboard.reviews_due")}>
          {data.reviews_due > 0 ? (
            <div className="flex items-center justify-between gap-3">
              <span className="text-2xl font-semibold tabular-nums">{data.reviews_due}</span>
              <ButtonLink href="/review" size="sm">
                {t("review.start")}
              </ButtonLink>
            </div>
          ) : (
            <p className="text-sm text-muted">{t("dashboard.reviews_due_none")}</p>
          )}
        </Panel>

        <Panel title={t("dashboard.insights")} className="lg:col-span-2">
          <dl className="grid gap-4 sm:grid-cols-3">
            <Stat label={t("dashboard.insight.independent")} value={<RateValue rate={data.insights.independent_accuracy} />} />
            <Stat label={t("dashboard.insight.hints")} value={<RateValue rate={data.insights.hint_dependency} />} />
            <Stat label={t("dashboard.insight.recall")} value={<RateValue rate={data.insights.review_recall} />} />
          </dl>
          {data.insights.top_errors.length > 0 && (
            <div className="mt-4 border-t border-border pt-3">
              <p className="mb-2 text-xs text-subtle">{t("dashboard.insight.errors")}</p>
              <div className="flex flex-wrap gap-1.5">
                {data.insights.top_errors.map((e) => (
                  <Tag key={e.error_type}>
                    {tk(`status.${e.error_type}`, e.error_type)} · {e.count}
                  </Tag>
                ))}
              </div>
            </div>
          )}
        </Panel>

        <Panel title={t("dashboard.recent")} className="lg:col-span-3" padded={false}>
          {data.recent_attempts.length === 0 ? (
            <p className="p-4 text-sm text-muted">{t("dashboard.recent_empty")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {data.recent_attempts.map((a) => (
                <li key={a.submission_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
                  <Link href={`/practice/${a.exercise_id}`} className="min-w-0 truncate font-mono text-xs hover:text-accent">
                    {a.exercise_id}
                  </Link>
                  <span className="flex items-center gap-2">
                    <Tag>{a.kind === "run" ? t("attempts.run") : t("attempts.submit")}</Tag>
                    {a.total !== null && a.total > 0 && (
                      <Tag tone={a.passed === a.total ? "success" : "danger"}>
                        {a.passed}/{a.total}
                      </Tag>
                    )}
                    {a.status === "timed_out" && <Tag tone="warning">{t("status.timeout")}</Tag>}
                    <span className="text-xs text-subtle">{formatDate(a.submitted_at)}</span>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </PageContainer>
  );
}
