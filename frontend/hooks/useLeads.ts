import { useCallback, useEffect, useRef, useState } from "react";
import { api, auth } from "../api/client";

export type LeadStatus = "new" | "contacted" | "qualified" | "rejected" | "ignored" | "do_not_contact";

export interface Lead {
  id: number;
  user_id: number;
  strategy_id: number | null;
  source_platform: string;
  external_id: string;
  content: string;
  content_summary: string;
  intent_score: number;
  keywords: string[];
  status: LeadStatus;
  created_at: string;
  source_url: string | null;
  author_name: string | null;
  author_username: string | null;
  author_url: string | null;
  author_email: string | null;
  author_phone: string | null;
  author_location: string | null;
  outreach_template: string | null;
  feedback: number | null;
}

export interface LeadFilters {
  platform?: string;
  status?: string;
  strategy_id?: number;
  min_intent_score?: number;
  max_intent_score?: number;
  from_date?: string;
  to_date?: string;
  has_contact?: boolean;
}

function buildQuery(filters: LeadFilters): string {
  const params = new URLSearchParams();
  if (filters.platform) params.set("platform", filters.platform);
  if (filters.status) params.set("status", filters.status);
  if (filters.strategy_id != null) params.set("strategy_id", String(filters.strategy_id));
  if (filters.min_intent_score != null)
    params.set("min_intent_score", String(filters.min_intent_score));
  if (filters.max_intent_score != null)
    params.set("max_intent_score", String(filters.max_intent_score));
  if (filters.from_date) params.set("from_date", filters.from_date);
  if (filters.to_date) params.set("to_date", filters.to_date);
  if (filters.has_contact != null) params.set("has_contact", String(filters.has_contact));
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function useLeads(filters: LeadFilters) {
  const [leads, setLeads] = useState<Lead[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const fetch = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    try {
      const data = await api.get<Lead[]>(
        `/leads/${buildQuery(filters)}`,
        auth.accessToken()
      );
      if (!ctrl.signal.aborted) setLeads(data);
    } catch (e: unknown) {
      if (!ctrl.signal.aborted)
        setError(e instanceof Error ? e.message : "Failed to load leads");
    } finally {
      if (!ctrl.signal.aborted) setLoading(false);
    }
  }, [JSON.stringify(filters)]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    fetch();
    return () => abortRef.current?.abort();
  }, [fetch]);

  const updateStatus = useCallback(
    async (id: number, status: LeadStatus) => {
      await api.patch(`/leads/${id}/status`, { status }, auth.accessToken());
      setLeads((prev) =>
        prev.map((l) => (l.id === id ? { ...l, status } : l))
      );
    },
    []
  );

  return { leads, loading, error, refetch: fetch, updateStatus };
}
