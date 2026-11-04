"use client";

import { useState, type FormEvent } from "react";

import { useApp } from "@/components/app-context";
import { PageContainer, useHealth } from "@/components/app-shell";
import { RunnerUnavailable } from "@/components/runner-unavailable";
import { Button, cx, ErrorState, InlineNotice, LoadingBlock, PageHeader, Panel } from "@/components/ui";
import { ApiError, patch, post } from "@/lib/api";
import { LOCALES, useI18n, type Locale } from "@/lib/i18n";
import { applyTheme, readTheme, type Theme } from "@/lib/theme";
import type { AppSettings, Profile } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const field = "mt-1 block h-8 w-full rounded-md border border-border bg-surface-2 px-2.5 text-sm focus:border-accent";

function ProfileSection() {
  const { profile, setProfile } = useApp();
  const { t } = useI18n();
  const [name, setName] = useState(profile?.display_name ?? "");
  const [goal, setGoal] = useState(profile?.daily_goal_minutes ?? 120);
  const [days, setDays] = useState(profile?.days_per_week ?? 5);
  const [locale, setLocaleValue] = useState<Locale>(profile?.locale ?? "ru");
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  async function save(e: FormEvent) {
    e.preventDefault();
    try {
      const p = await patch<Profile>("/profile", { display_name: name.trim(), daily_goal_minutes: goal, days_per_week: days, locale });
      setProfile(p);
      setSaved(true);
      setError(null);
    } catch (err) {
      setError(err as ApiError);
    }
  }

  return (
    <Panel title={t("settings.profile")}>
      <form onSubmit={save} className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm sm:col-span-2">
          {t("onboarding.name")}
          <input className={field} value={name} maxLength={80} required onChange={(e) => { setName(e.target.value); setSaved(false); }} />
        </label>
        <label className="block text-sm">
          {t("onboarding.goal")}
          <input
            className={field}
            type="number"
            min={15}
            max={600}
            step={5}
            value={goal}
            onChange={(e) => { setGoal(Number(e.target.value)); setSaved(false); }}
          />
        </label>
        <label className="block text-sm">
          {t("onboarding.days")}
          <input className={field} type="number" min={1} max={7} value={days} onChange={(e) => { setDays(Number(e.target.value)); setSaved(false); }} />
        </label>
        <label className="block text-sm">
          {t("onboarding.locale")}
          <select className={field} value={locale} onChange={(e) => { setLocaleValue(e.target.value as Locale); setSaved(false); }}>
            {LOCALES.map((l) => (
              <option key={l} value={l}>
                {l === "ru" ? "Русский" : "English"}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-end gap-3 sm:col-span-2">
          <Button type="submit" variant="primary">
            {t("common.save")}
          </Button>
          {saved && <span className="text-xs text-success" role="status">{t("common.saved")}</span>}
        </div>
        {error && (
          <div className="sm:col-span-2">
            <ErrorState error={error} />
          </div>
        )}
      </form>
    </Panel>
  );
}

function AppearanceSection() {
  const { t } = useI18n();
  // Page content only renders client-side (after the profile loads), so reading storage here is safe.
  const [theme, setTheme] = useState<Theme>(() => (typeof window === "undefined" ? "dark" : readTheme()));
  return (
    <Panel title={t("settings.appearance")}>
      <fieldset>
        <legend className="text-sm">{t("settings.theme")}</legend>
        <div className="mt-2 flex gap-2">
          {(["dark", "light"] as const).map((th) => (
            <label
              key={th}
              className={cx(
                "inline-flex h-8 cursor-pointer items-center rounded-md border px-3 text-sm",
                theme === th ? "border-accent bg-accent-soft" : "border-border text-muted hover:text-text",
              )}
            >
              <input
                type="radio"
                name="theme"
                className="sr-only"
                checked={theme === th}
                onChange={() => {
                  setTheme(th);
                  applyTheme(th);
                }}
              />
              {t(`settings.theme.${th}`)}
            </label>
          ))}
        </div>
      </fieldset>
    </Panel>
  );
}

function AISection() {
  const { t } = useI18n();
  const { data, error, loading, setData } = useApi<AppSettings>("/settings");
  if (error) return <ErrorState error={error} />;
  if (loading || !data) return <LoadingBlock />;
  const ai = data.ai;
  const status = ai.available
    ? t("settings.ai.status.available", { model: ai.model })
    : ai.reason === "disabled_in_settings"
      ? t("settings.ai.status.disabled_in_settings")
      : t("settings.ai.status.no_api_key");

  async function update(change: Partial<AppSettings["settings"]>) {
    setData(await patch<AppSettings>("/settings", change));
  }

  return (
    <Panel title={t("settings.ai")}>
      <InlineNotice tone={ai.available ? "success" : "neutral"}>{status}</InlineNotice>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <label className="flex items-center gap-2 text-sm sm:col-span-2">
          <input type="checkbox" checked={data.settings.ai_enabled} onChange={(e) => void update({ ai_enabled: e.target.checked })} />
          {t("settings.ai.enabled")}
        </label>
        <label className="block text-sm">
          {t("settings.ai.limit")}
          <input
            className={field}
            type="number"
            min={0}
            max={1000}
            defaultValue={data.settings.ai_daily_request_limit}
            onBlur={(e) => void update({ ai_daily_request_limit: Number(e.target.value) })}
          />
        </label>
        <label className="block text-sm">
          {t("settings.ai.budget")}
          <input
            className={field}
            type="number"
            min={0}
            max={100}
            step={0.1}
            defaultValue={data.settings.ai_daily_budget_usd}
            onBlur={(e) => void update({ ai_daily_budget_usd: Number(e.target.value) })}
          />
        </label>
        <div className="sm:col-span-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={data.settings.send_code_to_ai} onChange={(e) => void update({ send_code_to_ai: e.target.checked })} />
            {t("settings.ai.send_code")}
          </label>
          <p className="mt-1 text-xs text-subtle">{t("settings.ai.send_code_note")}</p>
        </div>
      </div>
      <p className="mt-3 text-xs text-subtle">
        {t("settings.ai.usage", { n: ai.usage_today.requests, c: ai.usage_today.estimated_cost_usd.toFixed(4) })}
      </p>
    </Panel>
  );
}

function DataSection() {
  const { t } = useI18n();
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  async function backup() {
    try {
      const r = await post<{ file: string }>("/backup");
      setDone(r.file);
      setError(null);
    } catch (e) {
      setError(e as ApiError);
    }
  }
  return (
    <Panel title={t("settings.data")}>
      <p className="text-sm text-muted">{t("settings.data.note")}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button onClick={() => void backup()}>{t("settings.backup")}</Button>
        <a className="inline-flex h-8 items-center rounded-md border border-border px-3 text-sm hover:bg-surface-2" href="/api/v1/export/progress?format=json" download>
          {t("settings.export_json")}
        </a>
        <a className="inline-flex h-8 items-center rounded-md border border-border px-3 text-sm hover:bg-surface-2" href="/api/v1/export/progress?format=csv" download>
          {t("settings.export_csv")}
        </a>
      </div>
      {done && <p className="mt-2 text-xs text-success" role="status">{t("settings.backup_done", { file: done })}</p>}
      {error && <div className="mt-2"><ErrorState error={error} /></div>}
    </Panel>
  );
}

function SystemSection() {
  const { t } = useI18n();
  const health = useHealth();
  return (
    <Panel title={t("settings.system")}>
      <div id="system" className="space-y-2 text-sm">
        {!health ? (
          <LoadingBlock />
        ) : health.runner.available ? (
          <p>
            {t("settings.system.runner")}: <span className="text-success">{t("settings.system.ok")}</span> ·{" "}
            <span className="text-muted">{t("settings.system.limits", { s: health.runner.limits.time_s, mb: health.runner.limits.memory_mb })}</span>
            <br />
            <span className="font-mono text-xs text-subtle">{health.runner.image}</span>
          </p>
        ) : (
          <RunnerUnavailable reason={health.runner.reason} />
        )}
      </div>
    </Panel>
  );
}

export default function SettingsPage() {
  const { t } = useI18n();
  return (
    <PageContainer>
      <PageHeader title={t("settings.title")} />
      <div className="space-y-4">
        <ProfileSection />
        <AppearanceSection />
        <AISection />
        <DataSection />
        <SystemSection />
      </div>
    </PageContainer>
  );
}
