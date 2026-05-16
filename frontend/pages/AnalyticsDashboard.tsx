import { useEffect, useState } from "react";
import { api, auth } from "../api/client";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";

interface DayCount {
  date: string;
  count: number;
}

interface PlatformCount {
  platform: string;
  count: number;
}

interface AnalyticsSummary {
  leads_by_day: DayCount[];
  platform_breakdown: PlatformCount[];
  avg_intent_score: number;
  total_leads: number;
  contacted_leads: number;
  new_this_week: number;
  posts_scanned: number;
}

const PLATFORM_LABELS: Record<string, string> = {
  reddit: "Reddit",
  telegram: "Telegram",
  discord: "Discord",
  linkedin: "LinkedIn",
  job_board: "Job Board",
  hackernews: "Hacker News",
  stackoverflow: "Stack Overflow",
  devto: "Dev.to",
  github: "GitHub",
  indiehackers: "Indie Hackers",
  quora: "Quora",
};

const PLATFORM_COLORS: Record<string, string> = {
  reddit: "bg-orange-500",
  telegram: "bg-blue-400",
  discord: "bg-indigo-500",
  linkedin: "bg-blue-700",
  job_board: "bg-emerald-500",
  hackernews: "bg-amber-500",
  stackoverflow: "bg-orange-400",
  devto: "bg-gray-700",
  github: "bg-gray-600",
  indiehackers: "bg-teal-600",
  quora: "bg-red-600",
};

// ── Pure-SVG sparkline ─────────────────────────────────────────────────────────

function Sparkline({ data, label }: { data: DayCount[]; label: string }) {
  if (!data.length) return null;
  const counts = data.map((d) => d.count);
  const maxVal = Math.max(...counts, 1);
  const W = 320;
  const H = 64;
  const pad = 4;

  const pts = counts
    .map((v, i) => {
      const x = pad + (i / (counts.length - 1)) * (W - pad * 2);
      const y = H - pad - (v / maxVal) * (H - pad * 2);
      return `${x},${y}`;
    })
    .join(" ");

  const areaPath =
    `M ${pad},${H - pad} ` +
    counts
      .map((v, i) => {
        const x = pad + (i / (counts.length - 1)) * (W - pad * 2);
        const y = H - pad - (v / maxVal) * (H - pad * 2);
        return `L ${x},${y}`;
      })
      .join(" ") +
    ` L ${W - pad},${H - pad} Z`;

  return (
    <div>
      <div className="flex items-end justify-between mb-1">
        <span className="text-xs text-gray-400 font-medium uppercase tracking-wide">{label}</span>
        <div className="flex gap-3 text-xs text-gray-400">
          {data.map((d) => (
            <span key={d.date} className="text-center w-10 truncate">{d.date.split(" ")[1]}</span>
          ))}
        </div>
      </div>
      <svg
        width="100%"
        viewBox={`0 0 ${W} ${H}`}
        className="overflow-visible"
        preserveAspectRatio="none"
      >
        <defs>
          <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.18" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#sparkGrad)" />
        <polyline
          fill="none"
          stroke="#6366f1"
          strokeWidth="2"
          strokeLinejoin="round"
          strokeLinecap="round"
          points={pts}
        />
        {counts.map((v, i) => {
          const x = pad + (i / (counts.length - 1)) * (W - pad * 2);
          const y = H - pad - (v / maxVal) * (H - pad * 2);
          return (
            <circle key={i} cx={x} cy={y} r="3" fill="#6366f1" />
          );
        })}
      </svg>
      <div className="flex gap-3 text-xs text-gray-400 mt-1">
        {data.map((d) => (
          <span key={d.date} className="text-center w-10 font-medium text-gray-700">
            {d.count}
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Stat card ──────────────────────────────────────────────────────────────────

function StatCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: boolean;
}) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-1">{label}</p>
      <p className={`text-3xl font-bold ${accent ? "text-indigo-600" : "text-gray-900"}`}>
        {value}
      </p>
      {sub && <p className="text-xs text-gray-400 mt-1">{sub}</p>}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AnalyticsDashboard() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .get<AnalyticsSummary>("/analytics/summary", auth.accessToken())
      .then(setData)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const topPlatformCount = data?.platform_breakdown?.[0]?.count ?? 1;
  const contactRate =
    data && data.total_leads > 0
      ? Math.round((data.contacted_leads / data.total_leads) * 100)
      : 0;

  return (
    <div className="flex flex-col h-screen">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-8">
          <div className="max-w-4xl mx-auto">

            {/* Header */}
            <div className="mb-6">
              <h2 className="text-xl font-semibold text-gray-900">Analytics</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Lead volume, channel performance, and outreach metrics.
              </p>
            </div>

            {loading ? (
              <div className="text-sm text-gray-400 py-16 text-center">Loading…</div>
            ) : !data ? (
              <div className="text-sm text-gray-400 py-16 text-center">
                No data yet. Leads will appear here once your monitor starts scanning.
              </div>
            ) : (
              <div className="flex flex-col gap-6">

                {/* Stat cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <StatCard label="Total leads" value={data.total_leads} />
                  <StatCard
                    label="New this week"
                    value={data.new_this_week}
                    accent
                    sub="Last 7 days"
                  />
                  <StatCard
                    label="Avg intent score"
                    value={`${Math.round(data.avg_intent_score * 100)}%`}
                    sub="Across all leads"
                  />
                  <StatCard
                    label="Contact rate"
                    value={`${contactRate}%`}
                    sub={`${data.contacted_leads} contacted`}
                  />
                </div>

                {/* Leads-per-day sparkline */}
                <div className="bg-white border border-gray-200 rounded-xl p-6">
                  <h3 className="text-sm font-semibold text-gray-700 mb-4">Leads over the last 7 days</h3>
                  <Sparkline data={data.leads_by_day} label="Leads / day" />
                </div>

                {/* Platform breakdown */}
                {data.platform_breakdown.length > 0 && (
                  <div className="bg-white border border-gray-200 rounded-xl p-6">
                    <h3 className="text-sm font-semibold text-gray-700 mb-4">
                      Leads by channel
                    </h3>
                    <div className="flex flex-col gap-3">
                      {data.platform_breakdown.map(({ platform, count }) => {
                        const pct = Math.round((count / topPlatformCount) * 100);
                        const color = PLATFORM_COLORS[platform] ?? "bg-gray-400";
                        return (
                          <div key={platform}>
                            <div className="flex items-center justify-between mb-1">
                              <span className="text-sm text-gray-700">
                                {PLATFORM_LABELS[platform] ?? platform}
                              </span>
                              <span className="text-sm font-medium text-gray-900">{count}</span>
                            </div>
                            <div className="w-full bg-gray-100 rounded-full h-2">
                              <div
                                className={`${color} h-2 rounded-full transition-all duration-500`}
                                style={{ width: `${pct}%` }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* Posts scanned footer */}
                {data.posts_scanned > 0 && (
                  <p className="text-xs text-gray-400 text-center pb-2">
                    {data.posts_scanned.toLocaleString()} posts scanned in total across all syncs
                  </p>
                )}

              </div>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
