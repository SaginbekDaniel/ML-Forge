"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { PageContainer } from "@/components/app-shell";
import { apiErrorMessage } from "@/components/practice/results";
import { Button, ErrorState, LoadingBlock, PageHeader, Panel, Tag } from "@/components/ui";
import { ApiError, post } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { ReviewItem } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface ReviewsToday {
  due: ReviewItem[];
  upcoming: ReviewItem[];
  recent: ReviewItem[];
}

export default function ReviewPage() {
  const { t, tk, formatDate } = useI18n();
  const router = useRouter();
  const { data, error, loading, reload } = useApi<ReviewsToday>("/reviews/today");
  const [startError, setStartError] = useState<ApiError | null>(null);

  async function start(item: ReviewItem) {
    try {
      const started = await post<ReviewItem>(`/reviews/${item.id}/start`);
      router.push(`/practice/${started.exercise_id}?mode=review&review=${item.id}`);
    } catch (e) {
      setStartError(e as ApiError);
    }
  }

  if (error)
    return (
      <PageContainer>
        <ErrorState error={error} onRetry={() => void reload()} />
      </PageContainer>
    );
  if (loading || !data) return <LoadingBlock />;

  return (
    <PageContainer>
      <PageHeader title={t("review.title")} subtitle={t("review.subtitle")} />
      {startError && <p className="mb-3 text-sm text-danger" role="alert">{apiErrorMessage(t, tk, startError)}</p>}
      <div className="space-y-4">
        <Panel title={t("review.due")} padded={false}>
          {data.due.length === 0 ? (
            <p className="p-4 text-sm text-muted">{t("review.none_due")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {data.due.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-3">
                  <div>
                    <p className="text-sm font-medium">{r.skill_title}</p>
                    <p className="text-xs text-subtle">
                      {t("review.due_at", { date: formatDate(r.due_at) })} · {t("review.interval", { n: r.interval_days })}
                    </p>
                  </div>
                  <Button size="sm" variant="primary" onClick={() => void start(r)}>
                    {t("review.start")}
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title={t("review.upcoming")} padded={false}>
          {data.upcoming.length === 0 ? (
            <p className="p-4 text-sm text-muted">{t("review.none_upcoming")}</p>
          ) : (
            <ul className="divide-y divide-border">
              {data.upcoming.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 text-sm">
                  <span>{r.skill_title}</span>
                  <span className="text-xs text-subtle">{t("review.due_at", { date: formatDate(r.due_at) })}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        {data.recent.length > 0 && (
          <Panel title={t("review.recent")} padded={false}>
            <ul className="divide-y divide-border">
              {data.recent.map((r) => (
                <li key={r.id} className="flex items-center justify-between gap-2 px-4 py-2.5 text-sm">
                  <span>{r.skill_title}</span>
                  <Tag tone={r.last_outcome === "passed" ? "success" : "danger"}>
                    {r.last_outcome === "passed" ? t("review.outcome.passed") : t("review.outcome.failed")}
                  </Tag>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </PageContainer>
  );
}
