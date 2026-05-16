import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api/client";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";

// ── Types ─────────────────────────────────────────────────────────────────────

interface SuggestedChannel {
  id: number;
  strategy_id: number | null;
  platform_type: string;
  name: string;
  url: string | null;
  status: "pending" | "active" | "inactive" | "rejected" | "watching";
  created_at: string;
}

interface ChannelHealth {
  channel_id: number;
  last_lead_at: string | null;
  lead_count: number;
}

interface StrategyTitle {
  id: number;
  title: string | null;
}

// ── Channel health helper ─────────────────────────────────────────────────────

function healthColor(lastLeadAt: string | null): string {
  if (!lastLeadAt) return "text-gray-400";
  const days = (Date.now() - new Date(lastLeadAt).getTime()) / 86400000;
  if (days < 7) return "text-green-600";
  if (days < 30) return "text-yellow-600";
  return "text-red-500";
}

function healthLabel(lastLeadAt: string | null, leadCount: number): string {
  if (!lastLeadAt) return leadCount === 0 ? "No leads yet" : "Unknown";
  const days = Math.floor((Date.now() - new Date(lastLeadAt).getTime()) / 86400000);
  if (days === 0) return "Lead today";
  if (days === 1) return "Lead yesterday";
  return `Lead ${days}d ago`;
}

// ── Constants ─────────────────────────────────────────────────────────────────

const SYNC_INTERVAL_OPTIONS = [
  { value: 0, label: "Default" },
  { value: 1, label: "Every 1h" },
  { value: 2, label: "Every 2h" },
  { value: 4, label: "Every 4h" },
  { value: 8, label: "Every 8h" },
  { value: 24, label: "Every 24h" },
];

const PLATFORM_ICONS: Record<string, string> = {
  reddit: "🟠",
  telegram: "✈️",
  discord: "💬",
  linkedin: "💼",
  job_board: "📋",
};

const PLATFORM_LABELS: Record<string, string> = {
  reddit: "Reddit",
  telegram: "Telegram",
  discord: "Discord",
  linkedin: "LinkedIn",
  job_board: "Job Board",
};

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-gray-100 text-gray-500 ring-gray-400/20",
  watching: "bg-green-50 text-green-700 ring-green-600/20",
  rejected: "bg-red-50 text-red-400 ring-red-400/20",
  active: "bg-blue-50 text-blue-700 ring-blue-600/20",
  inactive: "bg-gray-100 text-gray-400 ring-gray-400/20",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

// For platforms where the URL is deterministic from the name, build it client-side.
// For Discord / LinkedIn / Job Board, the real URL comes from server-side scraping
// stored in channel.url — if it's still null, we show a "Find link" button instead.
function staticUrl(channel: SuggestedChannel): string | null {
  if (channel.url) return channel.url;
  const slug = channel.name.replace(/^(@|r\/|\/r\/)/, "").trim();
  switch (channel.platform_type) {
    case "reddit":
      return `https://www.reddit.com/r/${encodeURIComponent(slug)}`;
    case "telegram":
      return /\s/.test(slug) ? null : `https://t.me/${slug}`;
    default:
      return null;
  }
}

function ExternalIcon() {
  return <span style={{ fontSize: "11px", marginLeft: "4px", opacity: 0.6 }}>↗</span>;
}

// ── Channel row ───────────────────────────────────────────────────────────────

function ChannelRow({
  channel,
  health,
  onStatusChange,
  onSyncIntervalChange,
  onUrlResolved,
}: {
  channel: SuggestedChannel;
  health?: ChannelHealth;
  onStatusChange: (id: number, status: SuggestedChannel["status"], discordChannelId?: string) => Promise<void>;
  onSyncIntervalChange: (id: number, hours: number) => Promise<void>;
  onUrlResolved: (id: number, url: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [showManualInput, setShowManualInput] = useState(false);
  const [manualUrl, setManualUrl] = useState("");
  const [savingUrl, setSavingUrl] = useState(false);
  const [syncInterval, setSyncInterval] = useState(0);
  // Discord-specific: ask for real channel ID before watching
  const [showDiscordIdInput, setShowDiscordIdInput] = useState(false);
  const [discordChannelId, setDiscordChannelId] = useState("");
  const url = staticUrl(channel);
  const isDiscord = channel.platform_type === "discord";

  async function act(status: SuggestedChannel["status"], discordId?: string) {
    setBusy(true);
    await onStatusChange(channel.id, status, discordId);
    setBusy(false);
  }

  function handleWatchClick() {
    if (isDiscord && !showDiscordIdInput) {
      setShowDiscordIdInput(true);
      return;
    }
    act("watching", discordChannelId || undefined);
    setShowDiscordIdInput(false);
  }

  async function handleSyncChange(hours: number) {
    setSyncInterval(hours);
    await onSyncIntervalChange(channel.id, hours);
  }

  async function handleResolve() {
    setResolving(true);
    try {
      const updated = await api.post<SuggestedChannel>(
        `/suggested-channels/${channel.id}/resolve`,
        {},
        auth.accessToken()
      );
      if (updated.url) {
        onUrlResolved(channel.id, updated.url);
        return;
      }
    } catch {
      // fall through to manual input
    } finally {
      setResolving(false);
    }
    setShowManualInput(true);
  }

  async function handleSaveManualUrl() {
    const trimmed = manualUrl.trim();
    if (!trimmed.startsWith("http")) return;
    setSavingUrl(true);
    try {
      await api.patch(
        `/suggested-channels/${channel.id}`,
        { status: channel.status, url: trimmed },
        auth.accessToken()
      );
      onUrlResolved(channel.id, trimmed);
      setShowManualInput(false);
    } catch {
      // ignore
    } finally {
      setSavingUrl(false);
    }
  }

  const isWatching = channel.status === "watching";
  const isRejected = channel.status === "rejected";

  return (
    <tr className="hover:bg-gray-50 transition-colors">
      {/* Platform */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="flex items-center gap-2">
          <span className="text-lg">{PLATFORM_ICONS[channel.platform_type] ?? "🌐"}</span>
          <span className="text-sm text-gray-600">{PLATFORM_LABELS[channel.platform_type] ?? channel.platform_type}</span>
        </span>
      </td>

      {/* Name */}
      <td className="px-4 py-3 text-sm font-medium text-gray-800">
        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="group inline-flex items-center text-indigo-600 hover:text-indigo-800 hover:underline"
          >
            {channel.name}
            <ExternalIcon />
          </a>
        ) : showManualInput ? (
          <div className="flex flex-col gap-1.5">
            <span className="text-xs text-gray-400">Paste the invite / group URL:</span>
            <div className="flex items-center gap-1.5">
              <input
                type="url"
                value={manualUrl}
                onChange={(e) => setManualUrl(e.target.value)}
                placeholder="https://discord.gg/…"
                className="text-xs border border-gray-300 rounded px-2 py-1 w-44 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                autoFocus
              />
              <button
                onClick={handleSaveManualUrl}
                disabled={savingUrl || !manualUrl.startsWith("http")}
                className="text-xs bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white px-2 py-1 rounded font-medium"
              >
                {savingUrl ? "Saving…" : "Save"}
              </button>
              <button
                onClick={() => setShowManualInput(false)}
                className="text-xs text-gray-400 hover:text-gray-600 px-1"
              >
                ✕
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-gray-700">{channel.name}</span>
            <button
              onClick={handleResolve}
              disabled={resolving}
              title="Auto-find a link, or paste one manually if not found"
              className="text-xs px-2 py-0.5 rounded border border-indigo-200 text-indigo-500 hover:bg-indigo-50 transition-colors disabled:opacity-50"
            >
              {resolving ? "Finding…" : "Find link"}
            </button>
          </div>
        )}
      </td>

      {/* Status + sync interval + health */}
      <td className="px-4 py-3 whitespace-nowrap">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium ring-1 ring-inset ${STATUS_STYLES[channel.status] ?? ""}`}>
              {channel.status}
            </span>
            {isWatching && (
              <select
                value={syncInterval}
                onChange={(e) => handleSyncChange(Number(e.target.value))}
                className="text-xs border border-gray-200 rounded-md px-1.5 py-0.5 bg-white text-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                title="How often to check this channel"
              >
                {SYNC_INTERVAL_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            )}
          </div>
          {isWatching && health && (
            <span className={`text-xs ${healthColor(health.last_lead_at)}`}>
              {healthLabel(health.last_lead_at, health.lead_count)}
              {health.lead_count > 0 && (
                <span className="text-gray-400 ml-1">· {health.lead_count} total</span>
              )}
            </span>
          )}
        </div>
      </td>

      {/* Actions */}
      <td className="px-4 py-3 text-right">
        {/* Discord channel ID prompt */}
        {isDiscord && showDiscordIdInput && !isWatching && (
          <div className="flex flex-col items-end gap-1.5 mb-2">
            <p className="text-xs text-gray-400 text-right leading-tight">
              Paste the Discord channel ID<br />
              <span className="text-gray-300">(Right-click channel → Copy Channel ID)</span>
            </p>
            <div className="flex items-center gap-1.5">
              <input
                type="text"
                value={discordChannelId}
                onChange={(e) => setDiscordChannelId(e.target.value.trim())}
                placeholder="e.g. 123456789012345678"
                className="text-xs border border-gray-300 rounded px-2 py-1 w-44 focus:outline-none focus:ring-1 focus:ring-indigo-400 font-mono"
                autoFocus
              />
              <button
                onClick={() => setShowDiscordIdInput(false)}
                className="text-xs text-gray-400 hover:text-gray-600 px-1"
              >
                ✕
              </button>
            </div>
          </div>
        )}

        <div className="flex justify-end gap-2">
          {!isWatching && (
            <button
              onClick={handleWatchClick}
              disabled={busy}
              className="text-xs bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-md font-medium transition-colors"
            >
              {isDiscord && showDiscordIdInput ? "Confirm Watch" : "Watch"}
            </button>
          )}
          {isWatching && (
            <button
              onClick={() => act("inactive")}
              disabled={busy}
              className="text-xs border border-gray-200 hover:bg-gray-100 disabled:opacity-50 text-gray-500 px-3 py-1.5 rounded-md font-medium transition-colors"
            >
              Pause
            </button>
          )}
          {!isRejected && !isWatching && (
            <button
              onClick={() => act("rejected")}
              disabled={busy}
              className="text-xs border border-gray-200 hover:bg-gray-100 disabled:opacity-50 text-gray-400 px-3 py-1.5 rounded-md font-medium transition-colors"
            >
              Skip
            </button>
          )}
          {isRejected && (
            <button
              onClick={() => act("pending")}
              disabled={busy}
              className="text-xs text-indigo-500 hover:underline disabled:opacity-50 text-xs font-medium"
            >
              Restore
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

const PLATFORM_FILTER_OPTIONS = [
  { value: "", label: "All platforms" },
  { value: "reddit", label: "Reddit" },
  { value: "telegram", label: "Telegram" },
  { value: "discord", label: "Discord" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "job_board", label: "Job Board" },
];

const STATUS_FILTER_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "watching", label: "Watching" },
  { value: "rejected", label: "Skipped" },
  { value: "inactive", label: "Paused" },
];

const ALL_PLATFORMS = [
  { value: "reddit", label: "Reddit" },
  { value: "telegram", label: "Telegram" },
  { value: "discord", label: "Discord" },
  { value: "linkedin", label: "LinkedIn" },
  { value: "hackernews", label: "Hacker News" },
  { value: "stackoverflow", label: "Stack Overflow" },
  { value: "devto", label: "Dev.to" },
  { value: "github", label: "GitHub" },
  { value: "indiehackers", label: "Indie Hackers" },
  { value: "job_board", label: "Job Board" },
];

export default function SuggestedChannels() {
  const navigate = useNavigate();
  const [channels, setChannels] = useState<SuggestedChannel[]>([]);
  const [strategies, setStrategies] = useState<StrategyTitle[]>([]);
  const [healthMap, setHealthMap] = useState<Map<number, ChannelHealth>>(new Map());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [platformFilter, setPlatformFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [strategyFilter, setStrategyFilter] = useState("");

  // Add-manually form state
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState({ name: "", url: "", platform_type: "reddit", strategy_id: "" });
  const [addSaving, setAddSaving] = useState(false);

  // Load strategy titles + channel health once
  useEffect(() => {
    api.get<StrategyTitle[]>("/business/titles", auth.accessToken())
      .then(setStrategies)
      .catch(() => {});
    api.get<ChannelHealth[]>("/analytics/channel_health", auth.accessToken())
      .then((data) => {
        const m = new Map<number, ChannelHealth>();
        data.forEach((h) => m.set(h.channel_id, h));
        setHealthMap(m);
      })
      .catch(() => {});
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (platformFilter) params.set("platform_type", platformFilter);
      if (statusFilter) params.set("status", statusFilter);
      if (strategyFilter) params.set("strategy_id", strategyFilter);
      const qs = params.toString();
      const data = await api.get<SuggestedChannel[]>(
        `/suggested-channels/${qs ? `?${qs}` : ""}`,
        auth.accessToken()
      );
      setChannels(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load channels");
    } finally {
      setLoading(false);
    }
  }, [platformFilter, statusFilter, strategyFilter]);

  useEffect(() => { load(); }, [load]);

  async function handleStatusChange(
    id: number,
    status: SuggestedChannel["status"],
    discordChannelId?: string,
  ) {
    try {
      const body: Record<string, unknown> = { status };
      if (discordChannelId) body.discord_channel_id = discordChannelId;
      await api.patch(`/suggested-channels/${id}`, body, auth.accessToken());
      setChannels((prev) => prev.map((c) => (c.id === id ? { ...c, status } : c)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update channel");
    }
  }

  async function handleSyncIntervalChange(id: number, hours: number) {
    try {
      const channel = channels.find((c) => c.id === id);
      if (!channel) return;
      await api.patch(
        `/suggested-channels/${id}`,
        { status: channel.status, sync_interval_hours: hours || null },
        auth.accessToken()
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update sync interval");
    }
  }

  function handleUrlResolved(id: number, url: string) {
    setChannels((prev) => prev.map((c) => (c.id === id ? { ...c, url } : c)));
  }

  async function handleAddChannel() {
    if (!addForm.name.trim()) return;
    setAddSaving(true);
    try {
      const body: Record<string, unknown> = {
        platform_type: addForm.platform_type,
        name: addForm.name.trim(),
        url: addForm.url.trim() || null,
        status: "watching",
      };
      if (addForm.strategy_id) body.strategy_id = Number(addForm.strategy_id);
      const ch = await api.post<SuggestedChannel>("/suggested-channels/", body, auth.accessToken());
      setChannels((prev) => [ch, ...prev]);
      setAddForm({ name: "", url: "", platform_type: "reddit", strategy_id: "" });
      setShowAddForm(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add channel");
    } finally {
      setAddSaving(false);
    }
  }

  const watchingCount = channels.filter((c) => c.status === "watching").length;

  return (
    <div className="flex flex-col h-screen">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-8">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-xl font-semibold text-gray-900">Channels</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                AI-suggested channels to monitor for leads.
                {watchingCount > 0 && (
                  <span className="ml-2 text-green-600 font-medium">{watchingCount} being watched.</span>
                )}
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setShowAddForm((v) => !v)}
                className="text-sm border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 px-3 py-2 rounded-md font-medium transition-colors"
              >
                + Add manually
              </button>
              <button
                onClick={() => navigate("/dashboard/business")}
                className="text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md font-medium transition-colors"
              >
                + New strategy
              </button>
            </div>
          </div>

          {/* Add manually form */}
          {showAddForm && (
            <div className="bg-white border border-gray-200 rounded-xl p-5 mb-4">
              <h3 className="text-sm font-semibold text-gray-700 mb-3">Add a channel manually</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                <div>
                  <label className="text-xs font-medium text-gray-500 block mb-1">Platform</label>
                  <select
                    value={addForm.platform_type}
                    onChange={(e) => setAddForm((f) => ({ ...f, platform_type: e.target.value }))}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    {ALL_PLATFORMS.map((p) => (
                      <option key={p.value} value={p.value}>{p.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 block mb-1">Channel name / handle</label>
                  <input
                    type="text"
                    value={addForm.name}
                    onChange={(e) => setAddForm((f) => ({ ...f, name: e.target.value }))}
                    placeholder="e.g. r/entrepreneur or @channel"
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div>
                  <label className="text-xs font-medium text-gray-500 block mb-1">URL <span className="text-gray-400">(optional)</span></label>
                  <input
                    type="url"
                    value={addForm.url}
                    onChange={(e) => setAddForm((f) => ({ ...f, url: e.target.value }))}
                    placeholder="https://…"
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                {strategies.length > 0 && (
                  <div>
                    <label className="text-xs font-medium text-gray-500 block mb-1">Strategy <span className="text-gray-400">(optional)</span></label>
                    <select
                      value={addForm.strategy_id}
                      onChange={(e) => setAddForm((f) => ({ ...f, strategy_id: e.target.value }))}
                      className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                    >
                      <option value="">No strategy</option>
                      {strategies.map((s) => (
                        <option key={s.id} value={String(s.id)}>{s.title ?? `Strategy #${s.id}`}</option>
                      ))}
                    </select>
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={handleAddChannel}
                  disabled={addSaving || !addForm.name.trim()}
                  className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white text-sm font-medium px-4 py-2 rounded-md transition-colors"
                >
                  {addSaving ? "Adding…" : "Add & Watch"}
                </button>
                <button
                  onClick={() => setShowAddForm(false)}
                  className="text-sm text-gray-500 hover:text-gray-700 px-4 py-2"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}

          {/* Filters */}
          <div className="flex flex-wrap gap-3 mb-5">
            {strategies.length > 0 && (
              <select
                value={strategyFilter}
                onChange={(e) => setStrategyFilter(e.target.value)}
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
              value={platformFilter}
              onChange={(e) => setPlatformFilter(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              {PLATFORM_FILTER_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400"
            >
              {STATUS_FILTER_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            {(platformFilter || statusFilter || strategyFilter) && (
              <button
                onClick={() => { setPlatformFilter(""); setStatusFilter(""); setStrategyFilter(""); }}
                className="text-sm text-gray-400 hover:text-gray-700 px-2"
              >
                Clear
              </button>
            )}
          </div>

          {error && (
            <div className="mb-4 px-4 py-3 rounded-lg bg-red-50 border border-red-200 text-sm text-red-600">
              {error}
            </div>
          )}

          <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50">
                  {["Platform", "Channel", "Status", ""].map((col) => (
                    <th
                      key={col}
                      className="text-left px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {loading ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-12 text-center text-gray-400 text-sm">
                      <div className="flex items-center justify-center gap-2">
                        <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3V4a8 8 0 00-8 8z" />
                        </svg>
                        Loading channels…
                      </div>
                    </td>
                  </tr>
                ) : channels.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-16 text-center text-gray-400 text-sm">
                      <div className="flex flex-col items-center gap-3">
                        <span className="text-3xl">📡</span>
                        <span>No channels yet.</span>
                        <button
                          onClick={() => navigate("/dashboard/business")}
                          className="text-indigo-600 text-xs hover:underline font-medium"
                        >
                          Describe your business to get suggestions →
                        </button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  channels.map((ch) => (
                    <ChannelRow
                      key={ch.id}
                      channel={ch}
                      health={healthMap.get(ch.id)}
                      onStatusChange={handleStatusChange}
                      onSyncIntervalChange={handleSyncIntervalChange}
                      onUrlResolved={handleUrlResolved}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>

          {!loading && channels.length > 0 && (
            <p className="mt-3 text-xs text-gray-400 text-right">
              {channels.length} channel{channels.length !== 1 ? "s" : ""}
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
