"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { ActivityTracker } from "@/components/activity-tracker";
import { useApp } from "@/components/app-context";
import { cx, ErrorState, LoadingBlock } from "@/components/ui";
import { useI18n } from "@/lib/i18n";
import type { MessageKey } from "@/lib/i18n/ru";
import type { Health } from "@/lib/types";

const NAV: { href: string; key: MessageKey; match: (p: string) => boolean }[] = [
  { href: "/", key: "nav.dashboard", match: (p) => p === "/" },
  { href: "/roadmap", key: "nav.roadmap", match: (p) => p.startsWith("/roadmap") || p.startsWith("/learn") },
  { href: "/review", key: "nav.review", match: (p) => p.startsWith("/review") },
  { href: "/skills", key: "nav.skills", match: (p) => p.startsWith("/skills") || p.startsWith("/assessment") },
  { href: "/settings", key: "nav.settings", match: (p) => p.startsWith("/settings") },
];

function Logo() {
  const { t } = useI18n();
  return (
    <Link href="/" className="flex items-center gap-2 rounded-md font-semibold tracking-tight">
      <span aria-hidden className="inline-flex size-6 items-center justify-center rounded-md bg-accent font-mono text-xs text-accent-contrast">
        ML
      </span>
      <span>{t("app.name")}</span>
    </Link>
  );
}

function RunnerIndicator() {
  const { t } = useI18n();
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    let alive = true;
    const load = () =>
      fetch("/health", { cache: "no-store" })
        .then((r) => (r.ok ? (r.json() as Promise<Health>) : null))
        .then((h) => alive && setHealth(h))
        .catch(() => alive && setHealth(null));
    void load();
    const id = window.setInterval(load, 30_000);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, []);
  const ok = health?.runner.available ?? false;
  return (
    <Link href="/settings#system" className="flex items-center gap-2 rounded-md px-2 py-1 text-xs text-muted hover:text-text">
      <span aria-hidden className={cx("size-2 rounded-full", ok ? "bg-success" : "bg-danger")} />
      {t("settings.system.runner")}: {ok ? t("settings.system.ok") : t("settings.system.down")}
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { t } = useI18n();
  return (
    <ul className="space-y-0.5">
      {NAV.map((item) => {
        const active = item.match(pathname);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cx(
                "flex h-8 items-center rounded-md px-2.5 text-sm transition-colors",
                active ? "bg-surface-3 font-medium text-text" : "text-muted hover:bg-surface-2 hover:text-text",
              )}
            >
              {t(item.key)}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { profile, profileLoaded, profileError, reloadProfile } = useApp();
  const { t } = useI18n();
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const bare = pathname.startsWith("/onboarding");

  let content: ReactNode = children;
  if (!profileLoaded) content = <LoadingBlock />;
  else if (profileError)
    content = (
      <div className="mx-auto max-w-xl p-6">
        <ErrorState error={profileError} onRetry={() => void reloadProfile()} />
      </div>
    );

  if (bare) {
    return (
      <div className="min-h-dvh">
        <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:bg-surface focus:px-3 focus:py-2">
          {t("nav.skip")}
        </a>
        <header className="flex h-12 items-center border-b border-border px-4">
          <Logo />
        </header>
        <main id="main" className="px-4 py-6">
          {content}
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[208px_minmax(0,1fr)]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-50 focus:bg-surface focus:px-3 focus:py-2">
        {t("nav.skip")}
      </a>
      <ActivityTracker enabled={Boolean(profile?.onboarding_completed)} />

      {/* Desktop sidebar */}
      <aside className="sticky top-0 hidden h-dvh flex-col border-r border-border bg-surface px-3 py-4 lg:flex">
        <div className="px-1.5">
          <Logo />
        </div>
        <nav aria-label={t("nav.main")} className="mt-6 flex-1">
          <NavLinks />
        </nav>
        <RunnerIndicator />
      </aside>

      {/* Mobile / tablet top bar */}
      <header className="sticky top-0 z-30 border-b border-border bg-surface lg:hidden">
        <div className="flex h-12 items-center justify-between px-4">
          <Logo />
          <button
            type="button"
            className="inline-flex h-8 items-center rounded-md border border-border px-2.5 text-sm text-muted hover:text-text"
            aria-expanded={menuOpen}
            aria-controls="mobile-nav"
            onClick={() => setMenuOpen((v) => !v)}
          >
            {t("nav.menu")}
          </button>
        </div>
        {menuOpen && (
          <nav id="mobile-nav" aria-label={t("nav.main")} className="border-t border-border px-3 py-2">
            <NavLinks onNavigate={() => setMenuOpen(false)} />
            <div className="mt-2 border-t border-border pt-2">
              <RunnerIndicator />
            </div>
          </nav>
        )}
      </header>

      <main id="main" className="min-w-0">
        {content}
      </main>
    </div>
  );
}

/** Standard padded container for regular (non-workspace) pages. */
export function PageContainer({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return <div className={cx("mx-auto w-full px-4 py-5 sm:px-6 lg:py-8", wide ? "max-w-6xl" : "max-w-4xl")}>{children}</div>;
}

export function useHealth() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    fetch("/health", { cache: "no-store" })
      .then((r) => (r.ok ? (r.json() as Promise<Health>) : null))
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);
  return health;
}
