"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import { ApiError, get } from "@/lib/api";
import { I18nProvider, type Locale } from "@/lib/i18n";
import type { Profile } from "@/lib/types";

interface AppValue {
  profile: Profile | null;
  profileLoaded: boolean;
  profileError: ApiError | null;
  reloadProfile: () => Promise<Profile | null>;
  setProfile: (p: Profile) => void;
  locale: Locale;
  setLocale: (l: Locale) => void;
}

const AppContext = createContext<AppValue | null>(null);

export function AppProvider({ children }: { children: ReactNode }) {
  const [profile, setProfileState] = useState<Profile | null>(null);
  const [profileLoaded, setLoaded] = useState(false);
  const [profileError, setError] = useState<ApiError | null>(null);
  const [locale, setLocaleState] = useState<Locale>("ru");
  const router = useRouter();
  const pathname = usePathname();

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    document.documentElement.lang = l;
  }, []);

  const setProfile = useCallback(
    (p: Profile) => {
      setProfileState(p);
      setLocale(p.locale);
    },
    [setLocale],
  );

  const reloadProfile = useCallback(async () => {
    try {
      const p = await get<Profile>("/profile");
      setProfile(p);
      setError(null);
      return p;
    } catch (e) {
      const err = e instanceof ApiError ? e : new ApiError(0, "network_error", String(e));
      if (err.code !== "profile_required") setError(err);
      setProfileState(null);
      return null;
    } finally {
      setLoaded(true);
    }
  }, [setProfile]);

  // Initial load (subscribe-style: state is only set from the async callback).
  useEffect(() => {
    let alive = true;
    get<Profile>("/profile")
      .then((p) => alive && setProfile(p))
      .catch((e: unknown) => {
        if (!alive) return;
        const err = e instanceof ApiError ? e : new ApiError(0, "network_error", String(e));
        if (err.code !== "profile_required") setError(err);
      })
      .finally(() => alive && setLoaded(true));
    return () => {
      alive = false;
    };
  }, [setProfile]);

  // First run: no profile, or onboarding not finished -> onboarding (spec E2E #1).
  useEffect(() => {
    if (!profileLoaded || profileError) return;
    const onOnboarding = pathname.startsWith("/onboarding");
    const inDiagnosticTask = pathname.startsWith("/practice/") && typeof window !== "undefined" &&
      new URLSearchParams(window.location.search).get("mode") === "diagnostic";
    if ((!profile || !profile.onboarding_completed) && !onOnboarding && !inDiagnosticTask) {
      router.replace("/onboarding");
    }
  }, [profile, profileLoaded, profileError, pathname, router]);

  const value = useMemo(
    () => ({ profile, profileLoaded, profileError, reloadProfile, setProfile, locale, setLocale }),
    [profile, profileLoaded, profileError, reloadProfile, setProfile, locale, setLocale],
  );
  return (
    <AppContext.Provider value={value}>
      <I18nProvider locale={locale}>{children}</I18nProvider>
    </AppContext.Provider>
  );
}

export function useApp(): AppValue {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp outside AppProvider");
  return ctx;
}
