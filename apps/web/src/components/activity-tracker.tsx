"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef } from "react";

import { post } from "@/lib/api";

const BUCKET_S = 5;
const FLUSH_S = 30;

/**
 * Measures *active* study time: 5-second buckets that contain real input
 * (keys, pointer, scroll) while the tab is visible. Sent every 30 s; the server
 * additionally caps credit by wall-clock time. No activity -> nothing counted.
 */
export function ActivityTracker({ enabled }: { enabled: boolean }) {
  const pathname = usePathname();
  const activeBuckets = useRef(new Set<number>());

  useEffect(() => {
    if (!enabled) return;
    const mark = () => {
      if (document.visibilityState === "visible") activeBuckets.current.add(Math.floor(Date.now() / 1000 / BUCKET_S));
    };
    const events = ["keydown", "pointerdown", "wheel", "touchstart"] as const;
    events.forEach((e) => window.addEventListener(e, mark, { passive: true }));
    const timer = window.setInterval(() => {
      const seconds = activeBuckets.current.size * BUCKET_S;
      activeBuckets.current.clear();
      if (seconds === 0) return;
      const category = pathname.startsWith("/learn")
        ? "learn"
        : pathname.startsWith("/review")
          ? "review"
          : pathname.startsWith("/practice")
            ? "practice"
            : "other";
      post("/sessions/heartbeat", { category, active_seconds: Math.min(seconds, 60) }).catch(() => undefined);
    }, FLUSH_S * 1000);
    return () => {
      events.forEach((e) => window.removeEventListener(e, mark));
      window.clearInterval(timer);
    };
  }, [enabled, pathname]);

  return null;
}
