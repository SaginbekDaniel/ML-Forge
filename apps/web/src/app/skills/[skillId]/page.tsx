"use client";

import Link from "next/link";
import { use } from "react";

import { PageContainer } from "@/components/app-shell";
import {
  ButtonLink,
  CriteriaList,
  ErrorState,
  LoadingBlock,
  PageHeader,
  Panel,
  StateBadge,
  Tag,
} from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { SkillDetail } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const UNLOCKED = new Set(["available", "in_progress", "mastered", "needs_review"]);

export default function SkillPage({ params }: { params: Promise<{ skillId: string }> }) {
  const { skillId } = use(params);
  const { t, tk, formatDate, formatNumber } = useI18n();
  const { data: s, error, loading, reload } = useApi<SkillDetail>(`/skills/${skillId}`);
  if (error)
    return (
      <PageContainer>
        <ErrorState error={error} onRetry={() => void reload()} />
      </PageContainer>
    );
  if (loading || !s) return <LoadingBlock />;
  const unlocked = UNLOCKED.has(s.state);

  return (
    <PageContainer>
      <nav className="mb-3 text-xs text-subtle">
        <Link href="/skills" className="hover:text-text">
          {t("nav.skills")}
        </Link>
      </nav>
      <PageHeader
        title={s.title}
        subtitle={s.description}
        actions={
          <>
            {s.lesson_id && <ButtonLink href={`/learn/${s.lesson_id}`}>{t("roadmap.lesson")}</ButtonLink>}
            {unlocked && s.assessment_variants > 0 && (
              <ButtonLink href={`/assessment/${s.id}`} variant="primary">
                {t("skills.start_assessment")}
              </ButtonLink>
            )}
          </>
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <StateBadge state={s.state} />
        {s.prerequisite_details.length > 0 && (
          <span className="text-xs text-subtle">
            {t("skills.prerequisites")}:{" "}
            {s.prerequisite_details.map((p, i) => (
              <span key={p.id}>
                {i > 0 && ", "}
                <Link href={`/skills/${p.id}`} className="hover:text-text">
                  {p.title}
                </Link>{" "}
                ({t(`state.${p.state}`)})
              </span>
            ))}
          </span>
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title={t("dashboard.requirements")}>
          <CriteriaList criteria={s.criteria} />
          {!unlocked && <p className="mt-3 text-xs text-subtle">{t("skills.assessment_unavailable")}</p>}
          <dl className="mt-4 grid grid-cols-2 gap-2 border-t border-border pt-3 text-xs">
            <dt className="text-subtle">{t("skills.hint_dependency")}</dt>
            <dd className="font-mono">
              {s.hint_dependency === null ? t("common.never") : formatNumber(s.hint_dependency, { style: "percent", maximumFractionDigits: 0 })}
            </dd>
          </dl>
          {Object.keys(s.failure_tags).length > 0 && (
            <div className="mt-3">
              <p className="mb-1.5 text-xs text-subtle">{t("skills.failure_tags")}</p>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(s.failure_tags).map(([tag, n]) => (
                  <Tag key={tag}>
                    {tk(`status.${tag}`, tag)} · {n}
                  </Tag>
                ))}
              </div>
            </div>
          )}
        </Panel>

        <Panel title={t("skills.exercises")} padded={false}>
          <ul className="divide-y divide-border">
            {s.exercises.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5">
                <Link href={`/practice/${e.id}`} className="min-w-0 truncate text-sm hover:text-accent">
                  {e.title}
                </Link>
                <span className="flex items-center gap-1.5 text-xs">
                  {e.solved ? (
                    <Tag tone="success">{t("practice.solved_badge")}</Tag>
                  ) : e.best_score !== null ? (
                    <Tag tone="warning">{t("skills.score", { pct: Math.round(e.best_score * 100) })}</Tag>
                  ) : null}
                  {e.hints_used > 0 && <Tag>{t("skills.with_hints", { n: e.hints_used })}</Tag>}
                </span>
              </li>
            ))}
          </ul>
        </Panel>

        <Panel title={t("skills.evidence")} className="lg:col-span-2" padded={false}>
          {s.evidence.length === 0 ? (
            <p className="p-4 text-sm text-muted">{t("skills.evidence_empty")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {s.evidence.map((e) => (
                <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2 text-sm">
                  <span className="flex flex-wrap items-center gap-2">
                    <Tag tone={e.counts ? "success" : "neutral"}>{t("skills.score", { pct: Math.round(e.score * 100) })}</Tag>
                    <span>{tk(`skills.source.${e.source_type}`, e.source_type)}</span>
                    {e.exercise_id && <span className="font-mono text-xs text-subtle">{e.exercise_id}</span>}
                    {e.hint_level > 0 && <span className="text-xs text-warning">{t("skills.with_hints", { n: e.hint_level })}</span>}
                  </span>
                  <span className="flex items-center gap-2 text-xs text-subtle">
                    <Tag tone="accent">{tk(`skills.verification.${e.verification}`, e.verification)}</Tag>
                    {formatDate(e.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        {s.reviews.length > 0 && (
          <Panel title={t("skills.reviews")} className="lg:col-span-2" padded={false}>
            <ul className="divide-y divide-border">
              {s.reviews.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2 px-4 py-2 text-sm">
                  <span>{t("review.due_at", { date: formatDate(r.due_at) })}</span>
                  <span className="text-xs text-subtle">
                    {r.last_outcome ? t(`review.outcome.${r.last_outcome as "passed" | "failed"}`) : t("review.interval", { n: r.interval_days })}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </PageContainer>
  );
}
