"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, get } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => Promise<void>;
  setData: (d: T) => void;
}

interface Snapshot<T> {
  key: string | null;
  data: T | null;
  error: ApiError | null;
}

const toApiError = (e: unknown) => (e instanceof ApiError ? e : new ApiError(0, "network_error", String(e)));

/**
 * Minimal GET hook. `loading` is derived (no data for the current path yet), so
 * a reload keeps showing the previous data instead of flashing a spinner.
 */
export function useApi<T>(path: string | null): ApiState<T> {
  const [snap, setSnap] = useState<Snapshot<T>>({ key: null, data: null, error: null });

  useEffect(() => {
    if (path === null) return;
    let alive = true;
    get<T>(path)
      .then((data) => alive && setSnap({ key: path, data, error: null }))
      .catch((e: unknown) => alive && setSnap({ key: path, data: null, error: toApiError(e) }));
    return () => {
      alive = false;
    };
  }, [path]);

  const reload = useCallback(async () => {
    if (path === null) return;
    try {
      const data = await get<T>(path);
      setSnap({ key: path, data, error: null });
    } catch (e) {
      setSnap((s) => ({ key: path, data: s.key === path ? s.data : null, error: toApiError(e) }));
    }
  }, [path]);

  const setData = useCallback((data: T) => setSnap((s) => ({ ...s, data })), []);
  const current = snap.key === path;
  return {
    data: current ? snap.data : null,
    error: current ? snap.error : null,
    loading: path !== null && !current,
    reload,
    setData,
  };
}
