"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { en } from "./en";
import { ru, type MessageKey } from "./ru";

export type Locale = "ru" | "en";
export const LOCALES: Locale[] = ["ru", "en"];
const DICTS: Record<Locale, Record<MessageKey, string>> = { ru, en };

export type Vars = Record<string, string | number>;

export function translate(locale: Locale, key: MessageKey, vars?: Vars): string {
  const template = DICTS[locale][key] ?? ru[key] ?? key;
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, name: string) => (name in vars ? String(vars[name]) : `{${name}}`));
}

/** Translate a dynamic key (e.g. from an API enum) with a graceful fallback. */
export function hasKey(key: string): key is MessageKey {
  return key in ru;
}

interface I18nValue {
  locale: Locale;
  t: (key: MessageKey, vars?: Vars) => string;
  tk: (key: string, fallback: string, vars?: Vars) => string;
  formatDate: (iso: string, opts?: Intl.DateTimeFormatOptions) => string;
  formatNumber: (n: number, opts?: Intl.NumberFormatOptions) => string;
}

const I18nContext = createContext<I18nValue | null>(null);

export function I18nProvider({ locale, children }: { locale: Locale; children: ReactNode }) {
  const t = useCallback((key: MessageKey, vars?: Vars) => translate(locale, key, vars), [locale]);
  const tk = useCallback(
    (key: string, fallback: string, vars?: Vars) => (hasKey(key) ? translate(locale, key, vars) : fallback),
    [locale],
  );
  const value = useMemo<I18nValue>(() => {
    const tag = locale === "ru" ? "ru-RU" : "en-GB";
    return {
      locale,
      t,
      tk,
      formatDate: (iso, opts) =>
        new Intl.DateTimeFormat(tag, opts ?? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(
          new Date(iso),
        ),
      formatNumber: (n, opts) => new Intl.NumberFormat(tag, opts).format(n),
    };
  }, [locale, t, tk]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
