import { useEffect, useState } from "react";
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

// ── Filter bar ────────────────────────────────────────────────────────────────

interface FilterBarProps {
  filters: LeadFilters;
  onChange: (f: LeadFilters) => void;
  strategies: StrategyTitle[];
}

function FilterBar({ filters, onChange, strategies }: FilterBarProps) {
  const set = (patch: Partial<LeadFilters>) => onChange({ ...filters, ...patch });

  return (
    <div className="flex flex-wrap gap-3 mb-5">
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

      <input
        type="date"
        value={filters.from_date ?? ""}
        onChange={(e) => set({ from_date: e.target.value || undefined })}
        className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
      />

      <input
        type="date"
        value={filters.to_date ?? ""}
        onChange={(e) => set({ to_date: e.target.value || undefined })}
        className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
      />

      <div className="flex items-center gap-2 bg-white border border-gray-200 rounded-lg px-3 py-2">
        <span className="text-xs text-gray-500 whitespace-nowrap">Intent ≥</span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={filters.min_intent_score ?? 0}
          onChange={(e) =>
            set({ min_intent_score: Number(e.target.value) || undefined })
          }
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

      {Object.values(filters).some((v) => v != null && v !== false) && (
        <button
          onClick={() => onChange({})}
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
                onClick={() => {
                  onStatusChange(lead.id, opt.value);
                  setOpen(false);
                }}
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

// ── Lead detail panel ─────────────────────────────────────────────────────────

interface DetailRow {
  icon: JSX.Element;
  label: string;
  value: string;
  href?: string; // only for profile links, not contact details
}

function DetailPanel({ lead, onClose, onStatusChange }: {
  lead: Lead;
  onClose: () => void;
  onStatusChange: (id: number, status: LeadStatus) => void;
}) {
  const hasContact =
    lead.author_name || lead.author_username || lead.author_email ||
    lead.author_phone || lead.author_location || lead.author_url;

  const rows: DetailRow[] = [];

  if (lead.author_name) {
    rows.push({
      icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
        </svg>
      ),
      label: "Name",
      value: lead.author_name,
    });
  }

  if (lead.author_username && lead.author_username !== lead.author_name) {
    rows.push({
      icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
      label: "Username",
      value: `@${lead.author_username}`,
      href: lead.author_url ?? undefined,
    });
  }

  if (lead.author_email) {
    rows.push({
      icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
        </svg>
      ),
      label: "Email",
      value: lead.author_email,
    });
  }

  if (lead.author_phone) {
    rows.push({
      icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 002.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 01-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 00-1.091-.852H4.5A2.25 2.25 0 002.25 4.5v2.25z" />
        </svg>
      ),
      label: "Phone",
      value: lead.author_phone,
    });
  }

  if (lead.author_location) {
    rows.push({
      icon: (
        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 11-6 0 3 3 0 016 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1115 0z" />
        </svg>
      ),
      label: "Location",
      value: lead.author_location,
    });
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-black/20 z-30 transition-opacity"
        onClick={onClose}
      />

      {/* Panel */}
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
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto">
          {/* Contact card */}
          <div className="px-6 pt-5 pb-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
              Contact details
            </h3>

            {hasContact ? (
              <div className="bg-gray-50 rounded-xl border border-gray-200 divide-y divide-gray-100">
                {rows.map((r) => (
                  <div key={r.label} className="flex items-start gap-3 px-4 py-3">
                    <span className="text-gray-400 mt-0.5 shrink-0">{r.icon}</span>
                    <div className="min-w-0">
                      <p className="text-xs text-gray-400 mb-0.5">{r.label}</p>
                      {r.href ? (
                        <a
                          href={r.href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm text-indigo-600 hover:underline break-all"
                        >
                          {r.value}
                        </a>
                      ) : (
                        <p className="text-sm text-gray-800 break-words select-all">{r.value}</p>
                      )}
                    </div>
                  </div>
                ))}

                {/* Profile link if username didn't already include it */}
                {lead.author_url && !lead.author_username && (
                  <div className="flex items-start gap-3 px-4 py-3">
                    <span className="text-gray-400 mt-0.5 shrink-0">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
                      </svg>
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs text-gray-400 mb-0.5">Profile</p>
                      <a
                        href={lead.author_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-indigo-600 hover:underline break-all"
                      >
                        {lead.author_url}
                      </a>
                    </div>
                  </div>
                )}

                {/* Source post link */}
                {lead.source_url && (
                  <div className="flex items-start gap-3 px-4 py-3">
                    <span className="text-gray-400 mt-0.5 shrink-0">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                      </svg>
                    </span>
                    <div className="min-w-0">
                      <p className="text-xs text-gray-400 mb-0.5">Original post</p>
                      <a
                        href={lead.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-indigo-600 hover:underline break-all"
                      >
                        View on {lead.source_platform}
                      </a>
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="bg-gray-50 rounded-xl border border-gray-100 px-4 py-5 text-center">
                <p className="text-sm text-gray-400">
                  No contact details found for this lead.
                </p>
                <p className="text-xs text-gray-300 mt-1">
                  Platform didn't expose author info and no contact was mentioned in the post.
                </p>
              </div>
            )}
          </div>

          {/* Intent + status */}
          <div className="px-6 pb-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
              Signal
            </h3>
            <div className="bg-gray-50 rounded-xl border border-gray-200 divide-y divide-gray-100">
              <div className="flex items-center justify-between px-4 py-3">
                <span className="text-sm text-gray-600">Intent score</span>
                {scoreBar(lead.intent_score)}
              </div>
              <div className="flex items-center justify-between px-4 py-3">
                <span className="text-sm text-gray-600">Status</span>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[lead.status] ?? "bg-gray-100 text-gray-500"}`}>
                  {lead.status.replace(/_/g, " ")}
                </span>
              </div>
            </div>
          </div>

          {/* Summary */}
          <div className="px-6 pb-4">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
              AI summary
            </h3>
            <p className="text-sm text-gray-700 bg-gray-50 rounded-xl border border-gray-200 px-4 py-3 leading-relaxed">
              {lead.content_summary || "No summary available."}
            </p>
          </div>

          {/* Keywords */}
          {lead.keywords.length > 0 && (
            <div className="px-6 pb-4">
              <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
                Matched keywords
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {lead.keywords.map((kw) => (
                  <span key={kw} className="px-2 py-1 text-xs bg-indigo-50 text-indigo-600 rounded-md border border-indigo-100">
                    {kw}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Original post */}
          <div className="px-6 pb-6">
            <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
              Original post
            </h3>
            <div className="bg-gray-50 rounded-xl border border-gray-200 px-4 py-3">
              <p className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed">
                {lead.content}
              </p>
            </div>
          </div>
        </div>

        {/* Footer actions */}
        <div className="px-6 py-4 border-t border-gray-200 bg-white">
          <select
            value={lead.status}
            onChange={(e) => onStatusChange(lead.id, e.target.value as LeadStatus)}
            className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
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

export default function LeadsTable() {
  const [filters, setFilters] = useState<LeadFilters>({});
  const [selected, setSelected] = useState<Lead | null>(null);
  const [strategies, setStrategies] = useState<StrategyTitle[]>([]);
  const { leads, loading, error, updateStatus } = useLeads(filters);

  useEffect(() => {
    api.get<StrategyTitle[]>("/business/titles", auth.accessToken())
      .then(setStrategies)
      .catch(() => {});
  }, []);

  const visible = leads.filter(
    (l) => l.status !== "ignored" && l.status !== "do_not_contact"
  );

  const handleStatusChange = async (id: number, status: LeadStatus) => {
    await updateStatus(id, status);
    setSelected((prev) => prev && prev.id === id ? { ...prev, status } : prev);
  };

  return (
    <div>
      <FilterBar filters={filters} onChange={setFilters} strategies={strategies} />

      {error && (
        <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-600">
          {error}
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50">
              {["Platform", "Content", "Source", "Intent", "Status", "Created", ""].map(
                (col) => (
                  <th
                    key={col}
                    className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide"
                  >
                    {col}
                  </th>
                )
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {loading ? (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center">
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
                <td colSpan={7} className="px-4 py-16 text-center text-gray-400 text-sm">
                  <div className="flex flex-col items-center gap-3">
                    <svg className="w-10 h-10 text-gray-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                        d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0H4" />
                    </svg>
                    <span>No leads yet. They'll appear here once channels are actively monitored.</span>
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
                      <span className="text-gray-700 capitalize">{lead.source_platform}</span>
                    </span>
                  </td>

                  {/* Content snippet */}
                  <td className="px-4 py-3 max-w-xs">
                    <p className="text-gray-700 truncate" title={lead.content_summary}>
                      {lead.content_summary || lead.content.slice(0, 100)}
                    </p>
                    {lead.author_name && (
                      <p className="text-xs text-indigo-500 mt-0.5 truncate">
                        {lead.author_name}
                        {lead.author_location ? ` · ${lead.author_location}` : ""}
                      </p>
                    )}
                    {/* Contact badges */}
                    {(lead.author_email || lead.author_username || lead.author_url) && (
                      <div className="flex items-center gap-1.5 mt-1.5">
                        {lead.author_email && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-green-50 text-green-700 border border-green-200 rounded" title={lead.author_email}>
                            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                              <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                            </svg>
                            Email
                          </span>
                        )}
                        {lead.author_username && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-indigo-50 text-indigo-600 border border-indigo-200 rounded" title={`@${lead.author_username}`}>
                            @{lead.author_username.length > 14 ? lead.author_username.slice(0, 14) + "…" : lead.author_username}
                          </span>
                        )}
                        {lead.author_url && !lead.author_username && (
                          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 text-xs bg-indigo-50 text-indigo-600 border border-indigo-200 rounded">
                            Profile
                          </span>
                        )}
                      </div>
                    )}
                    {lead.keywords.length > 0 && (
                      <div className="flex flex-wrap gap-1 mt-1">
                        {lead.keywords.slice(0, 3).map((kw) => (
                          <span key={kw} className="px-1.5 py-0.5 text-xs bg-gray-100 text-gray-500 rounded">
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                  </td>

                  {/* Source link */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span className="text-xs text-gray-400 font-mono">{lead.external_id}</span>
                  </td>

                  {/* Intent score */}
                  <td className="px-4 py-3 whitespace-nowrap">{scoreBar(lead.intent_score)}</td>

                  {/* Status badge */}
                  <td className="px-4 py-3 whitespace-nowrap">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset ${
                        STATUS_STYLES[lead.status] ?? "bg-gray-100 text-gray-500"
                      }`}
                    >
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
      </div>

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
        />
      )}
    </div>
  );
}
