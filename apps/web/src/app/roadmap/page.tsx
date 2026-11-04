"use client";

import Link from "next/link";

import { PageContainer } from "@/components/app-shell";
import { cx, ErrorState, LoadingBlock, PageHeader, StateBadge } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { Roadmap, SkillSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function SkillRow({ skill, titles }: { skill: SkillSummary; titles: Record<string, string> }) {
  const { t, locale } = useI18n();
  const dim = skill.state === "locked" || skill.state === "planned";
  const title = locale === "en" && skill.title_en ? skill.title_en : skill.title;
  return (
    <li
      className={cx(
        "relative rounded-lg border bg-surface p-4",
        skill.state === "in_progress" || skill.state === "available" ? "border-border-strong" : "border-border",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className={cx("text-base font-semibold", dim && "text-muted")}>
            {skill.status === "active" ? (
              <Link href={`/skills/${skill.id}`} className="hover:text-accent">
                {title}
              </Link>
            ) : (
              title
            )}
          </h3>
          <p className="mt-0.5 font-mono text-xs text-subtle">{skill.id}</p>
        </div>
        <StateBadge state={skill.state} />
      </div>
      <p className="mt-2 text-sm text-muted">{skill.description}</p>
      {skill.prerequisites.length > 0 && (
        <p className="mt-2 text-xs text-subtle">
          {t("roadmap.requires", { list: skill.prerequisites.map((p) => titles[p] ?? p).join(", ") })}
        </p>
      )}
      {skill.status === "planned" ? (
        <p className="mt-3 text-xs text-subtle">{t("roadmap.planned_note")}</p>
      ) : (
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          {skill.lesson_id && (
            <Link href={`/learn/${skill.lesson_id}`} className="text-accent hover:underline">
              {t("roadmap.lesson")}
              {skill.lesson_completed ? " ✓" : ""}
            </Link>
          )}
          <span className="text-muted">{t("roadmap.exercises", { a: skill.exercises_solved, b: skill.exercises_total })}</span>
          <span className="text-xs text-subtle">
            {t("roadmap.criteria", { a: skill.criteria.filter((c) => c.met).length, b: skill.criteria.length })}
          </span>
        </div>
      )}
    </li>
  );
}

export default function RoadmapPage() {
  const { t, tk } = useI18n();
  const { data, error, loading, reload } = useApi<Roadmap>("/roadmap");
  if (error)
    return (
      <PageContainer>
        <ErrorState error={error} onRetry={() => void reload()} />
      </PageContainer>
    );
  if (loading || !data) return <LoadingBlock />;
  const titles = Object.fromEntries(data.tracks.flatMap((tr) => tr.skills.map((s) => [s.id, s.title])));
  return (
    <PageContainer>
      <PageHeader title={t("roadmap.title")} subtitle={t("roadmap.subtitle")} />
      <p className="mb-6 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs text-muted">
        {t("roadmap.policy", {
          n: data.policy.min_distinct_exercises,
          pct: Math.round(data.policy.pass_threshold * 100),
          intervals: data.policy.review_intervals_days.join(" → "),
        })}
      </p>
      {data.tracks.map((track) => (
        <section key={track.id} className="mb-8">
          <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-subtle">
            {tk(`roadmap.track.${track.id}`, track.id)}
          </h2>
          <ol className="grid gap-3 sm:grid-cols-2">
            {track.skills.map((s) => (
              <SkillRow key={s.id} skill={s} titles={titles} />
            ))}
          </ol>
        </section>
      ))}
    </PageContainer>
  );
}
