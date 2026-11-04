"use client";

import Link from "next/link";

import { PageContainer } from "@/components/app-shell";
import { CriteriaList, ErrorState, LoadingBlock, PageHeader, Panel, StateBadge, Tag } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { Criterion, SkillStateName } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface SkillAnalytics {
  skills: {
    id: string;
    title: string;
    status: string;
    state: SkillStateName | null;
    criteria: Criterion[];
    hint_dependency: number | null;
    failure_tags: Record<string, number>;
    evidence: { total: number; passing: number; by_source: Record<string, number> };
    confirmation: "confirmed" | "partially_confirmed" | "insufficient_data";
  }[];
}

export default function SkillsPage() {
  const { t, tk, formatNumber } = useI18n();
  const { data, error, loading, reload } = useApi<SkillAnalytics>("/analytics/skills");
  if (error)
    return (
      <PageContainer>
        <ErrorState error={error} onRetry={() => void reload()} />
      </PageContainer>
    );
  if (loading || !data) return <LoadingBlock />;
  const active = data.skills.filter((s) => s.status === "active");
  return (
    <PageContainer>
      <PageHeader
        title={t("skills.title")}
        subtitle={t("skills.subtitle")}
        actions={
          <a href="/api/v1/export/progress?format=json" className="text-sm text-accent hover:underline" download>
            {t("skills.export")}
          </a>
        }
      />
      <ul className="space-y-3">
        {active.map((s) => (
          <li key={s.id}>
            <Panel
              title={
                <Link href={`/skills/${s.id}`} className="hover:text-accent">
                  {s.title}
                </Link>
              }
              actions={
                <span className="flex items-center gap-2">
                  <Tag tone={s.confirmation === "confirmed" ? "success" : s.confirmation === "partially_confirmed" ? "warning" : "neutral"}>
                    {t(`skills.confirmation.${s.confirmation}`)}
                  </Tag>
                  {s.state && <StateBadge state={s.state} />}
                </span>
              }
            >
              <div className="grid gap-4 md:grid-cols-[1fr_auto]">
                <CriteriaList criteria={s.criteria} />
                <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs md:text-right">
                  <dt className="text-subtle">{t("skills.evidence")}</dt>
                  <dd className="font-mono">
                    {s.evidence.passing}/{s.evidence.total}
                  </dd>
                  <dt className="text-subtle">{t("skills.hint_dependency")}</dt>
                  <dd className="font-mono">
                    {s.hint_dependency === null
                      ? t("common.never")
                      : formatNumber(s.hint_dependency, { style: "percent", maximumFractionDigits: 0 })}
                  </dd>
                </dl>
              </div>
              {Object.keys(s.failure_tags).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {Object.entries(s.failure_tags).map(([tag, n]) => (
                    <Tag key={tag}>
                      {tk(`status.${tag}`, tag)} · {n}
                    </Tag>
                  ))}
                </div>
              )}
            </Panel>
          </li>
        ))}
      </ul>
    </PageContainer>
  );
}
