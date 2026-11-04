"use client";

import { PageContainer } from "@/components/app-shell";
import { ButtonLink } from "@/components/ui";
import { useI18n } from "@/lib/i18n";

export default function NotFound() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <p className="text-lg font-semibold">404</p>
      <p className="mt-1 text-muted">{t("error.not_found")}</p>
      <ButtonLink href="/" className="mt-4">
        {t("nav.dashboard")}
      </ButtonLink>
    </PageContainer>
  );
}
