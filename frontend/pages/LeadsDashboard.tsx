import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import LeadsTable from "../components/LeadsTable";
import { api, auth } from "../api/client";

interface UserProfile {
  id: number;
  email: string;
  has_strategy: boolean;
}

interface SyncStatus {
  last_sync_at: string | null;
  posts_scanned: number;
  new_leads: number;
  is_running: boolean;
  runtime_seconds: number;
}

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "just now";
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  return `${d}d ago`;
}

// ── Sync status banner ────────────────────────────────────────────────────────

function SyncBanner({ onExport }: { onExport: () => void }) {
  const [status, setStatus] = useState<SyncStatus | null>(null);

  const fetchStatus = useCallback(() => {
    api.get<SyncStatus>("/monitor/status", auth.accessToken())
      .then(setStatus)
      .catch(() => {});
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 30_000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  return (
    <div className="flex items-center justify-between mb-6">
      <div>
        <h2 className="text-xl font-semibold text-gray-900">Leads</h2>
        <p className="text-sm text-gray-500 mt-0.5">
          High-intent signals from your monitored channels, scored by AI.
        </p>
      </div>

      <div className="flex items-center gap-3">
        {/* Sync status pill */}
        {status && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-white border border-gray-200 rounded-full text-xs text-gray-500 shadow-sm">
            {status.is_running ? (
              <>
                <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
                <span>Scanning…</span>
              </>
            ) : status.last_sync_at ? (
              <>
                <span className="w-2 h-2 rounded-full bg-green-500" />
                <span>Synced {relativeTime(status.last_sync_at)}</span>
                {status.posts_scanned > 0 && (
                  <>
                    <span className="text-gray-300">·</span>
                    <span>{status.posts_scanned.toLocaleString()} posts scanned</span>
                  </>
                )}
                {status.new_leads > 0 && (
                  <>
                    <span className="text-gray-300">·</span>
                    <span className="text-indigo-600 font-medium">{status.new_leads} leads found</span>
                  </>
                )}
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-gray-300" />
                <span>First sync starting…</span>
              </>
            )}
          </div>
        )}

        {/* Export CSV */}
        <button
          onClick={onExport}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-gray-600 bg-white border border-gray-200 rounded-lg hover:border-gray-300 hover:text-gray-900 transition-colors shadow-sm"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
          </svg>
          Export CSV
        </button>
      </div>
    </div>
  );
}

// ── Onboarding empty state ────────────────────────────────────────────────────

function OnboardingPrompt() {
  return (
    <div className="flex flex-col items-center justify-center flex-1 py-24 text-center">
      <div className="w-16 h-16 rounded-2xl bg-indigo-50 flex items-center justify-center mb-6">
        <svg className="w-8 h-8 text-indigo-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round"
            d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
        </svg>
      </div>

      <h3 className="text-lg font-semibold text-gray-900 mb-2">Set up your first strategy</h3>
      <p className="text-sm text-gray-500 max-w-sm mb-8 leading-relaxed">
        Describe your business and Claude will automatically find the best communities
        to monitor and surface high-intent leads for you.
      </p>

      <div className="flex flex-col items-center gap-6 w-full max-w-xs">
        {/* Step indicators */}
        <div className="flex items-start gap-4 text-left w-full">
          {[
            { step: "1", label: "Describe your business", sub: "Paste your website or describe what you sell" },
            { step: "2", label: "We find your channels", sub: "AI picks Reddit, HN, Slack groups and more" },
            { step: "3", label: "Leads appear here", sub: "High-intent buyers, scored and ready to contact" },
          ].map(({ step, label, sub }) => (
            <div key={step} className="flex flex-col items-center gap-1 flex-1">
              <div className="w-7 h-7 rounded-full bg-indigo-600 text-white flex items-center justify-center text-xs font-bold mb-1">
                {step}
              </div>
              <p className="text-xs font-medium text-gray-800 text-center">{label}</p>
              <p className="text-xs text-gray-400 text-center">{sub}</p>
            </div>
          ))}
        </div>

        <Link
          to="/dashboard/business"
          className="w-full bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium py-2.5 rounded-lg text-center transition-colors"
        >
          Analyze my business →
        </Link>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function LeadsDashboard() {
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [exportFn, setExportFn] = useState<(() => void) | null>(null);

  useEffect(() => {
    api.get<UserProfile>("/users/me", auth.accessToken())
      .then(setProfile)
      .catch(() => setProfile(null))
      .finally(() => setProfileLoading(false));
  }, []);

  const handleExport = () => {
    if (exportFn) exportFn();
  };

  return (
    <div className="flex flex-col h-screen">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-8 flex flex-col">

          {profileLoading ? null : !profile?.has_strategy ? (
            <OnboardingPrompt />
          ) : (
            <>
              <SyncBanner onExport={handleExport} />
              <LeadsTable onRegisterExport={(fn) => setExportFn(() => fn)} />
            </>
          )}

        </main>
      </div>
    </div>
  );
}
