"use client";

import { useRouter } from "next/navigation";
import { use, useState } from "react";

import { PageContainer } from "@/components/app-shell";
import { apiErrorMessage } from "@/components/practice/results";
import { Button, ErrorState, InlineNotice, LoadingBlock, PageHeader, Panel } from "@/components/ui";
import { ApiError, post } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { Assessment, SkillDetail } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export default function AssessmentPage({ params }: { params: Promise<{ skillId: string }> }) {
  const { skillId } = use(params);
  const { t, tk } = useI18n();
  const router = useRouter();
  const { data: skill, error, loading, reload } = useApi<SkillDetail>(`/skills/${skillId}`);
  const [startError, setStartError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);

  if (error)
    return (
      <PageContainer>
        <ErrorState error={error} onRetry={() => void reload()} />
      </PageContainer>
    );
  if (loading || !skill) return <LoadingBlock />;

  const seenAll = skill.assessment_variants > 0 && new Set(skill.assessments.map((a) => a.exercise_id)).size >= skill.assessment_variants;
  const active = skill.assessments.find((a) => a.status === "active");

  async function start() {
    setBusy(true);
    try {
      const a = await post<Assessment>("/assessments", { skill_id: skillId });
      router.push(`/practice/${a.exercise_id}?mode=independent&assessment=${a.id}`);
    } catch (e) {
      setStartError(e as ApiError);
      setBusy(false);
    }
  }

  return (
    <PageContainer>
      <PageHeader title={t("assessment.title")} subtitle={skill.title} />
      <Panel>
        <p className="text-sm">{t("assessment.intro", { skill: skill.title })}</p>
        {seenAll && !active && (
          <div className="mt-3">
            <InlineNotice tone="warning">{t("assessment.seen_warning")}</InlineNotice>
          </div>
        )}
        {startError && <p className="mt-3 text-sm text-danger" role="alert">{apiErrorMessage(t, tk, startError)}</p>}
        <Button variant="primary" className="mt-4" onClick={() => void start()} disabled={busy}>
          {active ? t("common.continue") : t("assessment.start")}
        </Button>
      </Panel>
    </PageContainer>
  );
}
