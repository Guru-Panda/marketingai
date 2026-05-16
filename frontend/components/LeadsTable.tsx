import { useCallback, useEffect, useRef, useState } from "react";
import { api, auth } from "../api/client";
import { Lead, LeadFilters, LeadStatus, useLeads } from "../hooks/useLeads";

interface StrategyTitle {
  id: number;
  title: string | null;
}

// ── Platform meta ─────────────────────────────────────────────────────────────

const PLATFORMS = [
  { value: "", label: "All platforms" },
  { value: "reddit", label: "Reddit" },
  { value: "telegram", label: "Telegram" },
  { value: "discord", label: "Discord" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "job_board", label: "Job Board" },
  { value: "hackernews", label: "Hacker News" },
  { value: "stackoverflow", label: "Stack Overflow" },
  { value: "devto", label: "Dev.to" },
  { value: "github", label: "GitHub" },
  { value: "indiehackers", label: "IndieHackers" },
];

const STATUSES = [
  { value: "", label: "All statuses" },
  { value: "new", label: "New" },
  { value: "contacted", label: "Contacted" },
  { value: "qualified", label: "Qualified" },
  { value: "rejected", label: "Rejected" },
];

const PLATFORM_ICONS: Record<string, string> = {
  reddit: "🟠",
  telegram: "✈️",
  discord: "💬",
  linkedin: "💼",
  job_board: "📋",
  hackernews: "🔶",
  stackoverflow: "📚",
  devto: "👩‍💻",
  github: "🐙",
  indiehackers: "🚀",
};

const STATUS_STYLES: Record<string, string> = {
  new: "bg-blue-50 text-blue-700 ring-blue-600/20",
  contacted: "bg-yellow-50 text-yellow-700 ring-yellow-600/20",
  qualified: "bg-green-50 text-green-700 ring-green-600/20",
  rejected: "bg-gray-100 text-gray-500 ring-gray-500/20",
  ignored: "bg-gray-100 text-gray-400 ring-gray-400/20",
  do_not_contact: "bg-red-50 text-red-600 ring-red-600/20",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function scoreColor(score: number): string {
  if (score >= 0.8) return "text-green-600 font-semibold";
  if (score >= 0.5) return "text-yellow-600 font-medium";
  return "text-gray-400";
}

function scoreBar(score: number): JSX.Element {
  const pct = Math.round(score * 100);
  const bg =
    score >= 0.8 ? "bg-green-500" : score >= 0.5 ? "bg-yellow-400" : "bg-gray-300";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${bg}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs tabular-nums ${scoreColor(score)}`}>{pct}%</span>
    </div>
  );
}

// ── CSV export ────────────────────────────────────────────────────────────────

function exportToCSV(leads: Lead[]) {
  const headers = [
    "ID", "Platform", "Author", "Username", "Email", "Phone", "Location",
    "Intent Score", "Status", "Summary", "Keywords", "Source URL", "Created At",
  ];
  const rows = leads.map((l) => [
    l.id,
    l.source_platform,
    l.author_name ?? "",
    l.author_username ?? "",
    l.author_email ?? "",
    l.author_phone ?? "",
    l.author_location ?? "",
    (l.intent_score * 100).toFixed(0) + "%",
    l.status,
    (l.content_summary || l.content.slice(0, 200)).replace(/"/g, '""'),
    (l.keywords || []).join("; "),
    l.source_url ?? "",
    new Date(l.created_at).toLocaleString(),
  ]);

  const csv = [headers, ...rows]
    .map((row) => row.map((v) => `"${v}"`).join(","))
    .join("\n");

  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `leads-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Copy button ───────────────────────────────────────────────────────────────

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <button
      onClick={copy}
      className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border transition-colors ${
        copied
          ? "bg-green-50 text-green-700 border-green-200"
          : "bg-white text-gray-600 border-gray-200 hover:border-indigo-300 hover:text-indigo-600"
      }`}
    >
      {copied ? (
        <>
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
          Copied!
        </>
      ) : (
        <>
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
          </svg>
          {label}
        </>
      )}
    </button>
  );
}

// ── Filter bar ────────────────────────────────────────────────────────────────

interface FilterBarProps {
  filters: LeadFilters;
  onChange: (f: LeadFilters) => void;
  strategies: StrategyTitle[];
  search: string;
  onSearch: (v: string) => void;
}

function FilterBar({ filters, onChange, strategies, search, onSearch }: FilterBarProps) {
  const set = (patch: Partial<LeadFilters>) => onChange({ ...filters, ...patch });

  return (
    <div className="flex flex-wrap gap-3 mb-5">
      {/* Text search */}
      <div className="relative">
        <svg className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
        <input
          type="text"
          placeholder="Search leads…"
          value={search}
          onChange={(e) => onSearch(e.target.value)}
          className="pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 w-48"
        />
      </div>

      {strategies.length > 0 && (
        <select
          value={filters.strategy_id != null ? String(filters.strategy_id) : ""}
          onChange={(e) => set({ strategy_id: e.target.value ? Number(e.target.value) : undefined })}
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
        >
          <option value="">All businesses</option>
          {strategies.map((s) => (
            <option key={s.id} value={String(s.id)}>
              {s.title || `Strategy #${s.id}`}
            </option>
          ))}
        </select>
      )}

      <select
        value={filters.platform ?? ""}
        onChange={(e) => set({ platform: e.target.value || undefined })}
        className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
      >
        {PLATFORMS.map((p) => (
          <option key={p.value} value={p.value}>{p.label}</option>
        ))}
      </select>

      <select
        value={filters.status ?? ""}
        onChange={(e) => set({ status: e.target.value || undefined })}
        className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
      >
        {STATUSES.map((s) => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
      </select>

      <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-2">
        <span className="text-xs text-gray-500 whitespace-nowrap">Intent ≥</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={filters.min_intent_score ?? 0}
          onChange={(e) => set({ min_intent_score: Number(e.target.value) || undefined })}
          className="w-24 accent-indigo-500"
        />
        <span className="text-xs font-medium text-gray-700 w-8 tabular-nums">
          {Math.round((filters.min_intent_score ?? 0) * 100)}%
        </span>
      </div>

      <button
        onClick={() => set({ has_contact: filters.has_contact ? undefined : true })}
        className={`text-sm px-3 py-2 rounded-lg border font-medium transition-colors ${
          filters.has_contact
            ? "bg-indigo-600 text-white border-indigo-600"
            : "bg-white text-gray-700 border-gray-200 hover:border-indigo-300"
        }`}
      >
        Has contact
      </button>

      {(Object.values(filters).some((v) => v != null && v !== false) || search) && (
        <button
          onClick={() => { onChange({}); onSearch(""); }}
          className="text-sm text-gray-400 hover:text-gray-700 px-2"
        >
          Clear
        </button>
      )}
    </div>
  );
}

// ── Row action menu ───────────────────────────────────────────────────────────

interface ActionMenuProps {
  lead: Lead;
  onStatusChange: (id: number, status: LeadStatus) => void;
}

function ActionMenu({ lead, onStatusChange }: ActionMenuProps) {
  const [open, setOpen] = useState(false);

  const options: { label: string; value: LeadStatus }[] = (
    [
      { label: "Mark contacted", value: "contacted" as LeadStatus },
      { label: "Mark qualified", value: "qualified" as LeadStatus },
      { label: "Ignore", value: "ignored" as LeadStatus },
      { label: "Do not contact", value: "do_not_contact" as LeadStatus },
    ] as { label: string; value: LeadStatus }[]
  ).filter((o) => o.value !== lead.status);

  return (
    <div className="relative">
      <button
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
        className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
      >
        <svg className="w-4 h-4" viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
        </svg>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-1 w-44 bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1">
            {options.map((opt) => (
              <button
                key={opt.value}
                onClick={() => { onStatusChange(lead.id, opt.value); setOpen(false); }}
                className="w-full text-left px-4 py-2 text-sm text-gray-700 hover:bg-gray-50"
              >
                {opt.label}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// ── Cross-platform dedup ──────────────────────────────────────────────────────

/**
 * Returns a map of author_username → Set of platforms they appear on.
 * Only includes usernames that appear on 2+ platforms.
 */
function buildDedupMap(leads: Lead[]): Map<string, Set<string>> {
  const raw = new Map<string, Set<string>>();
  for (const l of leads) {
    if (!l.author_username) continue;
    if (!raw.has(l.author_username)) raw.set(l.author_username, new Set());
    raw.get(l.author_username)!.add(l.source_platform);
  }
  const result = new Map<string, Set<string>>();
  for (const [username, platforms] of raw.entries()) {
    if (platforms.size >= 2) result.set(username, platforms);
  }
  return result;
}

// ── Lead detail panel ─────────────────────────────────────────────────────────

// ── Tone selector for outreach ────────────────────────────────────────────────

const TONES = [
  { value: "casual",       label: "Casual",       emoji: "😊" },
  { value: "professional", label: "Professional",  emoji: "💼" },
  { value: "direct",       label: "Direct",        emoji: "🎯" },
  { value: "empathetic",   label: "Empathetic",    emoji: "🤝" },
] as const;

type ToneValue = typeof TONES[number]["value"];

// ── Intent score explanation helper ──────────────────────────────────────────

function IntentBreakdown({ score, keywords, buyerPhrases }: {
  score: number;
  keywords: string[];
  buyerPhrases: string[];
}) {
  const matched = buyerPhrases.filter((bp) =>
    keywords.some((kw) => kw.toLowerCase().includes(bp.toLowerCase()) || bp.toLowerCase().includes(kw.toLowerCase()))
  );

  const scoreLabel =
    score >= 0.85 ? "Strong buying signal — highly likely to purchase" :
    score >= 0.70 ? "Moderate intent — worth reaching out to" :
    score >= 0.50 ? "Weak signal — may be early-stage interest" :
    "Low intent — general discussion, unlikely to buy";

  const scoreTier =
    score >= 0.85 ? "text-green-700 bg-green-50 border-green-200" :
    score >= 0.70 ? "text-yellow-700 bg-yellow-50 border-yellow-200" :
    "text-gray-600 bg-gray-50 border-gray-200";

  return (
    <div className={`rounded-lg border px-3 py-2.5 text-xs ${scoreTier} mt-2`}>
      <p className="font-medium mb-1">{scoreLabel}</p>
      {matched.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          <span className="text-xs opacity-70 mr-1">Matched buyer phrases:</span>
          {matched.map((bp) => (
            <span key={bp} className="px-1.5 py-0.5 rounded bg-white/60 border border-current/20 font-medium">{bp}</span>
          ))}
        </div>
      )}
      {keywords.length > 0 && matched.length === 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          <span className="text-xs opacity-70 mr-1">Matched signals:</span>
          {keywords.slice(0, 4).map((kw) => (
            <span key={kw} className="px-1.5 py-0.5 rounded bg-white/60 border border-current/20">{kw}</span>
          ))}
        </div>
      )}
    </div>
  );
}

function DetailPanel({ lead, onClose, onStatusChange, dedupPlatforms }: {
  lead: Lead;
  onClose: () => void;
  onStatusChange: (id: number, status: LeadStatus) => void;
  dedupPlatforms?: Set<string>;
}) {
  const [outreach, setOutreach] = useState<string | null>(lead.outreach_template ?? null);
  const [generatingOutreach, setGeneratingOutreach] = useState(false);
  const [selectedTone, setSelectedTone] = useState<ToneValue>("professional");
  const [strategyBuyerPhrases, setStrategyBuyerPhrases] = useState<string[]>([]);

  // Load buyer phrases from the lead's strategy for the score explanation
  useEffect(() => {
    if (lead.strategy_id) {
      api.get<{ buyer_phrases: string[] }>(`/business/${lead.strategy_id}`, auth.accessToken())
        .then((s) => setStrategyBuyerPhrases(s.buyer_phrases ?? []))
        .catch(() => {});
    }
  }, [lead.strategy_id]);

  const hasContact =
    lead.author_name || lead.author_username || lead.author_email ||
    lead.author_phone || lead.author_location || lead.author_url;

  const generateOutreach = useCallback(async () => {
    setGeneratingOutreach(true);
    try {
      const res = await api.post<{ outreach_template: string }>(
        `/leads/${lead.id}/outreach`, { tone: selectedTone }, auth.accessToken()
      );
      setOutreach(res.outreach_template);
    } catch {
      // silently ignore
    } finally {
      setGeneratingOutreach(false);
    }
  }, [lead.id, selectedTone]);

  return (
    <>
      <div className="fixed inset-0 bg-black/20 z-30 transition-opacity" onClick={onClose} />

      <div className="fixed right-0 top-0 h-full w-full max-w-md bg-white shadow-xl z-40 flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
          <div className="flex items-center gap-2">
            <span className="text-lg">{PLATFORM_ICONS[lead.source_platform] ?? "🌐"}</span>
            <div>
              <p className="text-sm font-semibold text-gray-900 capitalize">{lead.source_platform} lead</p>
              <p className="text-xs text-gray-400">{relativeTime(lead.created_at)}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {lead.source_url && (
              <a
                href={lead.source_url}
                target="_blank"
                rel="noopener noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-md hover:bg-indigo-100 transition-colors"
              >
                <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                </svg>
                View post
              </a>
            )}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Contact card */}
          <div className="px-6 pt-5 pb-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Contact details</h3>

            {hasContact ? (
              <div className="bg-gray-50 rounded-xl border border-gray-200 divide-y divide-gray-100">
                {lead.author_name && (
                  <div className="flex items-center gap-3 px-4 py-3">
                    <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                    </svg>
                    <div>
                      <p className="text-xs text-gray-400">Name</p>
                      <p className="text-sm text-gray-800 select-all">{lead.author_name}</p>
                    </div>
                  </div>
                )}
                {lead.author_username && (
                  <div className="flex items-center gap-3 px-4 py-3">
                    <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                    </svg>
                    <div>
                      <p className="text-xs text-gray-400">Username</p>
                      {lead.author_url ? (
                        <a href={lead.author_url} target="_blank" rel="noopener noreferrer"
                          className="text-sm text-indigo-600 hover:underline">
                          @{lead.author_username}
                        </a>
                      ) : (
                        <p className="text-sm text-gray-800 select-all">@{lead.author_username}</p>
                      )}
                    </div>
                  </div>
                )}
                {lead.author_email && (
                  <div className="flex items-center gap-3 px-4 py-3">
                    <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                    </svg>
                    <div>
                      <p className="text-xs text-gray-400">Email</p>
                      <a href={`mailto:${lead.author_email}`} className="text-sm text-indigo-600 hover:underline select-all">{lead.author_email}</a>
                    </div>
                  </div>
                )}
                {lead.author_phone && (
                  <div className="flex items-center gap-3 px-4 py-3">
                    <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
                    </svg>
                    <div>
                      <p className="text-xs text-gray-400">Phone</p>
                      <p className="text-sm text-gray-800 select-all">{lead.author_phone}</p>
                    </div>
                  </div>
                )}
                {lead.author_location && (
                  <div className="flex items-center gap-3 px-4 py-3">
                    <svg className="w-4 h-4 text-gray-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
                    </svg>
                    <div>
                      <p className="text-xs text-gray-400">Location</p>
                      <p className="text-sm text-gray-800">{lead.author_location}</p>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-gray-50 rounded-xl border border-gray-100 px-4 py-5 text-center">
                <p className="text-sm text-gray-400">No contact details found.</p>
                <p className="text-xs text-gray-300 mt-1">Author info wasn't exposed by the platform.</p>
              </div>
            )}
          </div>

          {/* Intent + status */}
          <div className="px-6 pb-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Signal</h3>
            <div className="bg-gray-50 rounded-xl border border-gray-200 divide-y divide-gray-100">
              <div className="flex items-center justify-between px-4 py-3">
                <span className="text-sm text-gray-600">Intent score</span>
                {scoreBar(lead.intent_score)}
              </div>
              <div className="px-4 py-2">
                <IntentBreakdown
                  score={lead.intent_score}
                  keywords={lead.keywords ?? []}
                  buyerPhrases={strategyBuyerPhrases}
                />
              </div>
              <div className="flex items-center justify-between px-4 py-3">
                <span className="text-sm text-gray-600">Status</span>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[lead.status] ?? "bg-gray-100 text-gray-500"}`}>
                  {lead.status.replace(/_/g, " ")}
                </span>
              </div>
              {dedupPlatforms && dedupPlatforms.size > 1 && (
                <div className="flex items-center gap-3 px-4 py-3">
                  <span className="text-sm text-gray-600">Cross-platform</span>
                  <div className="flex flex-wrap gap-1">
                    {[...dedupPlatforms].map((p) => (
                      <span key={p} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded">
                        {PLATFORM_ICONS[p] ?? "🌐"} {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Summary */}
          <div className="px-6 pb-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">AI summary</h3>
            <p className="text-sm text-gray-700 bg-gray-50 rounded-xl border border-gray-200 px-4 py-3 leading-relaxed">
              {lead.content_summary || "No summary available."}
            </p>
          </div>

          {/* Keywords */}
          {lead.keywords.length > 0 && (
            <div className="px-6 pb-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Matched keywords</h3>
              <div className="flex flex-wrap gap-1.5">
                {lead.keywords.map((kw) => (
                  <span key={kw} className="px-2 py-1 text-xs bg-indigo-50 text-indigo-600 rounded-md border border-indigo-100">{kw}</span>
                ))}
              </div>
            </div>
          )}

          {/* Outreach template */}
          <div className="px-6 pb-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Outreach template</h3>
              {outreach && <CopyButton text={outreach} label="Copy message" />}
            </div>

            {/* Tone selector */}
            <div className="flex gap-1.5 mb-3">
              {TONES.map((t) => (
                <button
                  key={t.value}
                  onClick={() => setSelectedTone(t.value)}
                  className={`flex items-center gap-1 px-2.5 py-1 text-xs rounded-full border transition-colors ${
                    selectedTone === t.value
                      ? "bg-indigo-600 text-white border-indigo-600"
                      : "bg-white text-gray-500 border-gray-200 hover:border-indigo-300 hover:text-indigo-600"
                  }`}
                >
                  <span>{t.emoji}</span>
                  <span>{t.label}</span>
                </button>
              ))}
            </div>

            {outreach ? (
              <div>
                <div className="bg-indigo-50 rounded-xl border border-indigo-100 px-4 py-3 mb-2">
                  <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{outreach}</p>
                </div>
                <button
                  onClick={generateOutreach}
                  disabled={generatingOutreach}
                  className="text-xs text-indigo-600 hover:underline disabled:opacity-50"
                >
                  {generatingOutreach ? "Regenerating…" : `↻ Regenerate as ${selectedTone}`}
                </button>
              </div>
            ) : (
              <div className="bg-gray-50 rounded-xl border border-gray-200 px-4 py-4 flex flex-col items-center gap-3 text-center">
                <p className="text-xs text-gray-400">No outreach template yet.</p>
                <button
                  onClick={generateOutreach}
                  disabled={generatingOutreach}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs bg-indigo-600 text-white rounded-md hover:bg-indigo-700 disabled:opacity-60 transition-colors"
                >
                  {generatingOutreach ? "Generating…" : `✨ Generate ${selectedTone} message`}
                </button>
              </div>
            )}
          </div>

          {/* Original post */}
          <div className="px-6 pb-6">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">Original post</h3>
            <div className="bg-gray-50 rounded-xl border border-gray-200 px-4 py-3">
              <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">{lead.content}</p>
            </div>
          </div>
        </div>

        {/* Footer actions */}
        <div className="px-6 py-4 border-t border-gray-200 bg-white flex gap-2">
          {lead.status !== "contacted" && (
            <button
              onClick={() => onStatusChange(lead.id, "contacted")}
              className="flex-1 bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium py-2 rounded-lg transition-colors"
            >
              Mark as contacted
            </button>
          )}
          <select
            value={lead.status}
            onChange={(e) => onStatusChange(lead.id, e.target.value as LeadStatus)}
            className={`text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 ${lead.status !== "contacted" ? "w-36 shrink-0" : "flex-1"}`}
          >
            <option value="new">New</option>
            <option value="contacted">Contacted</option>
            <option value="qualified">Qualified</option>
            <option value="rejected">Rejected</option>
            <option value="ignored">Ignore</option>
            <option value="do_not_contact">Do not contact</option>
          </select>
        </div>
      </div>
    </>
  );
}

// ── Main table ────────────────────────────────────────────────────────────────

interface LeadsTableProps {
  onRegisterExport?: (fn: () => void) => void;
}

export default function LeadsTable({ onRegisterExport }: LeadsTableProps) {
  const [filters, setFilters] = useState<LeadFilters>({});
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Lead | null>(null);
  const [strategies, setStrategies] = useState<StrategyTitle[]>([]);
  const { leads, loading, error, updateStatus } = useLeads(filters);

  // Build cross-platform dedup map (username → platforms seen on)
  const dedupMap = buildDedupMap(leads);

  useEffect(() => {
    api.get<StrategyTitle[]>("/business/titles", auth.accessToken())
      .then(setStrategies)
      .catch(() => {});
  }, []);

  const visible = leads.filter(
    (l) => l.status !== "ignored" && l.status !== "do_not_contact"
  ).filter((l) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (l.content_summary || l.content).toLowerCase().includes(q) ||
      (l.author_name ?? "").toLowerCase().includes(q) ||
      (l.author_username ?? "").toLowerCase().includes(q) ||
      (l.author_email ?? "").toLowerCase().includes(q) ||
      (l.keywords || []).some((k) => k.toLowerCase().includes(q))
    );
  });

  // Register export function with parent
  const exportRef = useRef<() => void>(() => exportToCSV(visible));
  exportRef.current = () => exportToCSV(visible);
  useEffect(() => {
    if (onRegisterExport) onRegisterExport(() => exportRef.current());
  }, [onRegisterExport]);

  const handleStatusChange = async (id: number, status: LeadStatus) => {
    await updateStatus(id, status);
    setSelected((prev) => prev && prev.id === id ? { ...prev, status } : prev);
  };

  return (
    <div>
      <FilterBar
        filters={filters}
        onChange={setFilters}
        strategies={strategies}
        search={search}
        onSearch={setSearch}
      />

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-600">{error}</div>
      )}

      {/* Mobile card view */}
      <div className="md:hidden flex flex-col gap-3">
        {loading ? (
          <div className="py-8 text-center text-sm text-gray-400">Loading…</div>
        ) : visible.length === 0 ? (
          <div className="py-12 text-center text-sm text-gray-400">
            {search ? `No leads match "${search}"` : "No leads yet — channels are being monitored."}
          </div>
        ) : visible.map((lead) => (
          <div
            key={lead.id}
            onClick={() => setSelected(lead)}
            className="bg-white border border-gray-200 rounded-xl p-4 cursor-pointer hover:border-indigo-200 active:bg-indigo-50 transition-colors"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2">
                <span>{PLATFORM_ICONS[lead.source_platform] ?? "🌐"}</span>
                <span className="text-xs text-gray-500 capitalize">{lead.source_platform}</span>
                {lead.author_username && dedupMap.has(lead.author_username) && (
                  <span className="text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded px-1.5 py-0.5">🔗 Multi</span>
                )}
              </div>
              <div className="flex items-center gap-2 shrink-0">
                {scoreBar(lead.intent_score)}
                <span className={`text-xs px-2 py-0.5 rounded-md ring-1 ring-inset font-medium ${STATUS_STYLES[lead.status] ?? ""}`}>
                  {lead.status.replace(/_/g, " ")}
                </span>
              </div>
            </div>
            <p className="text-sm text-gray-800 font-medium line-clamp-2 mb-1">
              {lead.content_summary || lead.content.slice(0, 120)}
            </p>
            {lead.author_name && (
              <p className="text-xs text-gray-400">{lead.author_name}{lead.author_location ? ` · ${lead.author_location}` : ""}</p>
            )}
            <div className="flex items-center gap-1.5 mt-2 flex-wrap">
              {lead.author_email && (
                <span className="text-xs bg-green-50 text-green-700 border border-green-200 rounded px-1.5 py-0.5">✉ Email</span>
              )}
              {lead.keywords.slice(0, 3).map((kw) => (
                <span key={kw} className="text-xs bg-gray-100 text-gray-500 rounded px-1.5 py-0.5">{kw}</span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Desktop table view */}
      <div className="hidden md:block bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              {["Platform", "Content", "Intent", "Status", "Created", ""].map((col) => (
                <th key={col} className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center">
                  <div className="flex items-center justify-center gap-2 text-gray-400 text-sm">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3V4a8 8 0 00-8 8z" />
                    </svg>
                    Loading leads…
                  </div>
                </td>
              </tr>
            ) : visible.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-16 text-center text-gray-400 text-sm">
                  <div className="flex flex-col items-center gap-3">
                    <svg className="w-10 h-10 text-gray-200" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
                    </svg>
                    {search
                      ? <span>No leads match "<strong>{search}</strong>"</span>
                      : <span>No leads yet — channels are being monitored. Check back soon.</span>
                    }
                  </div>
                </td>
              </tr>
            ) : (
              visible.map((lead) => (
                <tr
                  key={lead.id}
                  onClick={() => setSelected(lead)}
                  className={`hover:bg-indigo-50/40 transition-colors cursor-pointer ${selected?.id === lead.id ? "bg-indigo-50/60" : ""}`}
                >
                  {/* Platform */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="flex items-center gap-1.5">
                      <span>{PLATFORM_ICONS[lead.source_platform] ?? "🌐"}</span>
                      <span className="text-gray-700 capitalize text-xs">{lead.source_platform}</span>
                    </span>
                  </td>

                  {/* Content */}
                  <td className="px-4 py-3 max-w-sm">
                    <p className="text-gray-800 truncate font-medium text-xs" title={lead.content_summary}>
                      {lead.content_summary || lead.content.slice(0, 100)}
                    </p>
                    {lead.author_name && (
                      <p className="text-xs text-gray-400 mt-0.5 truncate">
                        {lead.author_name}{lead.author_location ? ` · ${lead.author_location}` : ""}
                      </p>
                    )}
                    <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
                      {lead.author_email && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-green-50 text-green-700 border border-green-200 rounded" title={lead.author_email}>
                          ✉ Email
                        </span>
                      )}
                      {lead.author_username && (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-indigo-50 text-indigo-600 border border-indigo-200 rounded">
                          @{lead.author_username.length > 14 ? lead.author_username.slice(0, 14) + "…" : lead.author_username}
                        </span>
                      )}
                      {lead.source_url && (
                        <a
                          href={lead.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(e) => e.stopPropagation()}
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-gray-50 text-gray-500 border border-gray-200 rounded hover:text-indigo-600 hover:border-indigo-200"
                        >
                          ↗ Post
                        </a>
                      )}
                      {lead.author_username && dedupMap.has(lead.author_username) && (
                        <span
                          title={`Also seen on: ${[...dedupMap.get(lead.author_username)!].filter(p => p !== lead.source_platform).join(", ")}`}
                          className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs bg-purple-50 text-purple-700 border border-purple-200 rounded"
                        >
                          🔗 Multi-platform
                        </span>
                      )}
                    </div>
                    {lead.keywords.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {lead.keywords.slice(0, 3).map((kw) => (
                          <span key={kw} className="px-1.5 py-0.5 text-xs bg-gray-100 text-gray-500 rounded">{kw}</span>
                        ))}
                      </div>
                    )}
                  </td>

                  {/* Intent score */}
                  <td className="px-4 py-3 whitespace-nowrap">{scoreBar(lead.intent_score)}</td>

                  {/* Status badge */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[lead.status] ?? "bg-gray-100 text-gray-500"}`}>
                      {lead.status.replace(/_/g, " ")}
                    </span>
                  </td>

                  {/* Created at */}
                  <td className="px-4 py-3 whitespace-nowrap text-gray-400 text-xs">
                    {relativeTime(lead.created_at)}
                  </td>

                  {/* Actions */}
                  <td className="px-4 py-3 whitespace-nowrap text-right">
                    <ActionMenu lead={lead} onStatusChange={handleStatusChange} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>{/* end desktop table */}

      {!loading && visible.length > 0 && (
        <p className="mt-3 text-xs text-gray-400 text-right">
          {visible.length} lead{visible.length !== 1 ? "s" : ""} · click any row to view details
        </p>
      )}

      {selected && (
        <DetailPanel
          lead={selected}
          onClose={() => setSelected(null)}
          onStatusChange={handleStatusChange}
          dedupPlatforms={selected.author_username ? dedupMap.get(selected.author_username) : undefined}
        />
      )}
    </div>
  );
}
