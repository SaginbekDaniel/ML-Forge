"use client";

import { useI18n } from "@/lib/i18n";

/** Honest "runner unavailable" state with the exact fix — never a fake green check. */
export function RunnerUnavailable({ reason }: { reason: string }) {
  const { t, tk } = useI18n();
  return (
    <div role="alert" className="rounded-lg border border-warning/30 bg-warning-soft p-4 text-sm">
      <p className="font-semibold">{t("runner.unavailable.title")}</p>
      <p className="mt-1 text-muted">{tk(`runner.reason.${reason}`, reason)}</p>
      <p className="mt-2">{t("runner.unavailable.body")}</p>
      <pre className="mt-2 overflow-x-auto rounded-md border border-border bg-code px-3 py-2 font-mono text-xs">make runner-build</pre>
    </div>
  );
}
