import { useState, useEffect, useCallback } from "react";

const BASE = "/api/dashboard";

export function useApi<T>(path: string, interval: number = 0) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const resp = await fetch(`${BASE}${path}`);
      if (!resp.ok) throw new Error(`${resp.status}: ${resp.statusText}`);
      setData(await resp.json());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    fetchData();
    if (interval > 0) {
      const id = setInterval(fetchData, interval);
      return () => clearInterval(id);
    }
  }, [fetchData, interval]);

  return { data, error, loading, refetch: fetchData };
}

export async function postApi<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${resp.status}: ${text}`);
  }
  return resp.json();
}

export async function putApi<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { method: "PUT" });
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.json();
}

export async function deleteApi<T>(path: string): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!resp.ok) throw new Error(`${resp.status}`);
  return resp.json();
}
