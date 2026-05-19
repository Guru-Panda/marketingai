import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api/client";
import Alert from "../components/Alert";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Strategy {
  id: number;
  title: string | null;
  main_problem: string;
  ideal_customer: string;
  keywords: string[];
  buyer_phrases: string[];
  exclude_keywords: string[];
  target_locations: string[];
  intent_threshold: number | null;
}

interface StrategyTitle {
  id: number;
  title: string | null;
}

interface SuggestedChannel {
  id: number;
  platform_type: string;
  name: string;
  url: string | null;
  status: string;
}

interface AnalyzeResponse {
  strategy: Strategy;
  channels: SuggestedChannel[];
}

// ── Tag input ─────────────────────────────────────────────────────────────────

function TagInput({
  tags,
  onChange,
  placeholder,
  colorClass = "bg-indigo-50 text-indigo-700 border-indigo-100",
}: {
  tags: string[];
  onChange: (tags: string[]) => void;
  placeholder?: string;
  colorClass?: string;
}) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  function add() {
    const val = input.trim();
    if (val && !tags.includes(val)) onChange([...tags, val]);
    setInput("");
  }

  return (
    <div
      className="flex flex-wrap gap-1.5 p-2 border border-gray-300 rounded-md min-h-[42px] cursor-text"
      onClick={() => inputRef.current?.focus()}
    >
      {tags.map((t) => (
        <span key={t} className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full border ${colorClass}`}>
          {t}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onChange(tags.filter((x) => x !== t)); }}
            className="opacity-50 hover:opacity-100 leading-none"
          >×</button>
        </span>
      ))}
      <input
        ref={inputRef}
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === ",") && input.trim()) {
            e.preventDefault();
            add();
          } else if (e.key === "Backspace" && !input && tags.length) {
            onChange(tags.slice(0, -1));
          }
        }}
        onBlur={add}
        placeholder={tags.length ? "" : placeholder}
        className="flex-1 min-w-[80px] text-xs outline-none bg-transparent text-gray-700 placeholder-gray-400"
      />
    </div>
  );
}

// ── Platform icons ────────────────────────────────────────────────────────────

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

// ── Suggested channel card ────────────────────────────────────────────────────

function ChannelCard({
  channel,
  onAction,
}: {
  channel: SuggestedChannel;
  onAction: (id: number, status: "watching" | "rejected") => void;
}) {
  const [busy, setBusy] = useState(false);
  const acted = channel.status === "watching" || channel.status === "rejected";

  async function handle(status: "watching" | "rejected") {
    setBusy(true);
    await onAction(channel.id, status);
    setBusy(false);
  }

  return (
    <div className="flex items-center justify-between px-4 py-3 border border-gray-100 rounded-lg bg-white hover:bg-gray-50 transition-colors">
      <div className="flex items-center gap-3">
        <span className="text-xl">{PLATFORM_ICONS[channel.platform_type] ?? "🌐"}</span>
        <div>
          <p className="text-sm font-medium text-gray-800">{channel.name}</p>
          <p className="text-xs text-gray-400">{PLATFORM_LABELS[channel.platform_type] ?? channel.platform_type}</p>
        </div>
      </div>

      {acted ? (
        <span
          className={`text-xs font-medium px-2.5 py-1 rounded-full ring-1 ring-inset ${
            channel.status === "watching"
              ? "bg-green-50 text-green-700 ring-green-600/20"
              : "bg-gray-100 text-gray-400 ring-gray-400/20"
          }`}
        >
          {channel.status === "watching" ? "Watching" : "Skipped"}
        </span>
      ) : (
        <div className="flex gap-2">
          <button
            onClick={() => handle("watching")}
            disabled={busy}
            className="text-xs bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white px-3 py-1.5 rounded-md font-medium transition-colors"
          >
            Watch
          </button>
          <button
            onClick={() => handle("rejected")}
            disabled={busy}
            className="text-xs border border-gray-200 hover:bg-gray-100 disabled:opacity-50 text-gray-500 px-3 py-1.5 rounded-md font-medium transition-colors"
          >
            Skip
          </button>
        </div>
      )}
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function BusinessForm() {
  const navigate = useNavigate();
  const [title, setTitle] = useState("");
  const [userText, setUserText] = useState("");
  const [targetLocations, setTargetLocations] = useState<string[]>([]);
  const [locationInput, setLocationInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResponse | null>(null);
  const [channels, setChannels] = useState<SuggestedChannel[]>([]);

  // Existing strategy edit state
  const [existingStrategies, setExistingStrategies] = useState<StrategyTitle[]>([]);
  const [editStrategy, setEditStrategy] = useState<Strategy | null>(null);
  const [editKeywords, setEditKeywords] = useState<string[]>([]);
  const [editBuyer, setEditBuyer] = useState<string[]>([]);
  const [editExclude, setEditExclude] = useState<string[]>([]);
  const [editThreshold, setEditThreshold] = useState(0.7);
  const [editSaving, setEditSaving] = useState(false);
  const [editStatus, setEditStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [showNewForm, setShowNewForm] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [deleting, setDeleting] = useState(false);

  // Suggested channels for the currently-selected strategy
  const [editSuggestedChannels, setEditSuggestedChannels] = useState<SuggestedChannel[]>([]);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const loadSuggestedChannels = useCallback(async (strategyId: number) => {
    setSuggestionsLoading(true);
    try {
      const data = await api.get<SuggestedChannel[]>(
        `/suggested-channels?strategy_id=${strategyId}&status=pending`,
        auth.accessToken()
      );
      setEditSuggestedChannels(data);
    } catch {
      setEditSuggestedChannels([]);
    } finally {
      setSuggestionsLoading(false);
    }
  }, []);

  const loadStrategy = useCallback(async (id: number) => {
    const s = await api.get<Strategy>(`/business/${id}`, auth.accessToken());
    setEditStrategy(s);
    setEditKeywords(s.keywords ?? []);
    setEditBuyer(s.buyer_phrases ?? []);
    setEditExclude(s.exclude_keywords ?? []);
    setEditThreshold(s.intent_threshold ?? 0.7);
    setDeleteConfirm(false);
    setEditStatus(null);
    loadSuggestedChannels(id);
  }, [loadSuggestedChannels]);

  useEffect(() => {
    api.get<StrategyTitle[]>("/business/titles", auth.accessToken())
      .then((list) => {
        setExistingStrategies(list);
        if (list.length > 0) loadStrategy(list[0].id);
      })
      .catch(() => {});
  }, [loadStrategy]);

  async function handleSaveEdit(e: FormEvent) {
    e.preventDefault();
    if (!editStrategy) return;
    setEditSaving(true);
    setEditStatus(null);
    try {
      const updated = await api.patch<Strategy>(
        `/business/${editStrategy.id}`,
        { keywords: editKeywords, buyer_phrases: editBuyer, exclude_keywords: editExclude, intent_threshold: editThreshold },
        auth.accessToken()
      );
      setEditStrategy(updated);
      setEditStatus({ type: "success", message: "Strategy updated — next sync will use these settings." });
    } catch (err) {
      setEditStatus({ type: "error", message: err instanceof Error ? err.message : "Failed to save" });
    } finally {
      setEditSaving(false);
    }
  }

  async function handleDeleteStrategy() {
    if (!editStrategy) return;
    setDeleting(true);
    setEditStatus(null);
    try {
      await api.delete(`/business/${editStrategy.id}`, auth.accessToken());
      const updated = existingStrategies.filter((s) => s.id !== editStrategy.id);
      setExistingStrategies(updated);
      setDeleteConfirm(false);
      if (updated.length > 0) {
        loadStrategy(updated[0].id);
      } else {
        setEditStrategy(null);
        setShowNewForm(true);
      }
    } catch (err) {
      setEditStatus({ type: "error", message: err instanceof Error ? err.message : "Failed to delete strategy" });
      setDeleteConfirm(false);
    } finally {
      setDeleting(false);
    }
  }

  async function handleRefreshSuggestions() {
    if (!editStrategy) return;
    setRefreshing(true);
    try {
      await api.post(
        `/suggested-channels/refresh?strategy_id=${editStrategy.id}`,
        {},
        auth.accessToken()
      );
      await loadSuggestedChannels(editStrategy.id);
    } catch (err) {
      setEditStatus({ type: "error", message: err instanceof Error ? err.message : "Failed to refresh suggestions" });
    } finally {
      setRefreshing(false);
    }
  }

  async function handleEditChannelAction(id: number, status: "watching" | "rejected") {
    try {
      await api.patch(`/suggested-channels/${id}`, { status }, auth.accessToken());
      // Remove from the pending list immediately — it's no longer pending
      setEditSuggestedChannels((prev) => prev.filter((c) => c.id !== id));
    } catch {
      // leave the card in place so the user can retry
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.post<AnalyzeResponse>(
        "/business/strategy",
        { title: title.trim() || null, user_text: userText, target_locations: targetLocations },
        auth.accessToken()
      );
      setResult(data);
      setChannels(data.channels);
      // Refresh strategy list
      const list = await api.get<StrategyTitle[]>("/business/titles", auth.accessToken());
      setExistingStrategies(list);
      setShowNewForm(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleChannelAction(id: number, status: "watching" | "rejected") {
    try {
      await api.patch(`/suggested-channels/${id}`, { status }, auth.accessToken());
      setChannels((prev) => prev.map((c) => (c.id === id ? { ...c, status } : c)));
    } catch {
      // status stays unchanged if the call fails — user can retry
    }
  }

  const watchingCount = channels.filter((c) => c.status === "watching").length;

  return (
    <div className="flex flex-col h-screen">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-8">
          <div className="max-w-2xl mx-auto">

            {/* Header */}
            <div className="mb-6">
              <h2 className="text-xl font-semibold text-gray-900">Business Strategy</h2>
              <p className="text-sm text-gray-500 mt-0.5">
                Describe your business and Claude will extract your strategy and suggest the best channels to monitor.
              </p>
            </div>

            {/* Existing strategy selector */}
            {existingStrategies.length > 1 && (
              <div className="bg-white border border-gray-200 rounded-xl p-4 mb-0 flex items-center gap-3">
                <span className="text-sm text-gray-500 shrink-0">Active strategy:</span>
                <select
                  value={editStrategy?.id ?? ""}
                  onChange={(e) => loadStrategy(Number(e.target.value))}
                  className="flex-1 border border-gray-300 rounded-md px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                >
                  {existingStrategies.map((s) => (
                    <option key={s.id} value={s.id}>{s.title ?? `Strategy #${s.id}`}</option>
                  ))}
                </select>
              </div>
            )}

            {/* Edit panel for existing strategy */}
            {editStrategy && !result && !showNewForm && (
              <div className="bg-white border border-gray-200 rounded-xl p-6">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">
                      {editStrategy.title ?? "Strategy"} — Fine-tune signals
                    </h3>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Adjust keywords and buyer phrases to improve lead quality.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowNewForm(true)}
                    className="text-xs text-indigo-600 hover:underline"
                  >
                    + New strategy
                  </button>
                </div>

                {editStatus && <div className="mb-4"><Alert type={editStatus.type} message={editStatus.message} /></div>}

                <form onSubmit={handleSaveEdit} className="flex flex-col gap-5">

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-0.5">PROBLEM SOLVED</p>
                      <p className="text-sm text-gray-700 leading-relaxed">{editStrategy.main_problem}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-0.5">IDEAL CUSTOMER</p>
                      <p className="text-sm text-gray-700 leading-relaxed">{editStrategy.ideal_customer}</p>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                      Keywords
                    </label>
                    <p className="text-xs text-gray-400 mb-2">Words we scan for. Press Enter or comma to add.</p>
                    <TagInput
                      tags={editKeywords}
                      onChange={setEditKeywords}
                      placeholder="Add keyword…"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                      Buyer phrases
                    </label>
                    <p className="text-xs text-gray-400 mb-2">Phrases that strongly signal purchase intent.</p>
                    <TagInput
                      tags={editBuyer}
                      onChange={setEditBuyer}
                      placeholder="Add phrase…"
                      colorClass="bg-amber-50 text-amber-700 border-amber-100"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">
                      Exclude keywords
                    </label>
                    <p className="text-xs text-gray-400 mb-2">
                      Posts containing these words will be skipped — removes noise from irrelevant topics.
                    </p>
                    <TagInput
                      tags={editExclude}
                      onChange={setEditExclude}
                      placeholder="Add exclusion…"
                      colorClass="bg-red-50 text-red-600 border-red-100"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                        Intent threshold
                      </label>
                      <span className="text-sm font-semibold text-indigo-600">
                        {Math.round(editThreshold * 100)}%
                      </span>
                    </div>
                    <p className="text-xs text-gray-400 mb-2">
                      Only save leads with an intent score at or above this level.
                    </p>
                    <input
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      value={editThreshold}
                      onChange={(e) => setEditThreshold(parseFloat(e.target.value))}
                      className="w-full accent-indigo-600"
                    />
                    <div className="flex justify-between text-xs text-gray-400 mt-0.5">
                      <span>0% — all leads</span>
                      <span>100% — perfect match only</span>
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={editSaving}
                    className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-medium py-2 rounded-md text-sm transition-colors"
                  >
                    {editSaving ? "Saving…" : "Save strategy settings"}
                  </button>

                  <div className="flex items-center justify-center pt-1 border-t border-gray-100">
                    {deleteConfirm ? (
                      <div className="flex items-center gap-3">
                        <span className="text-xs text-gray-500">Delete this strategy and all its leads?</span>
                        <button
                          type="button"
                          onClick={handleDeleteStrategy}
                          disabled={deleting}
                          className="text-xs font-medium text-red-600 hover:text-red-700 disabled:opacity-50"
                        >
                          {deleting ? "Deleting…" : "Yes, delete"}
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleteConfirm(false)}
                          className="text-xs text-gray-400 hover:text-gray-600"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setDeleteConfirm(true)}
                        className="text-xs text-red-500 hover:text-red-700 transition-colors"
                      >
                        Delete strategy
                      </button>
                    )}
                  </div>
                </form>
              </div>
            )}

            {/* Suggested channels for existing strategy */}
            {editStrategy && !result && !showNewForm && (
              <div className="bg-white border border-gray-200 rounded-xl p-6 mt-4">
                <div className="flex items-center justify-between mb-4">
                  <div>
                    <h3 className="text-sm font-semibold text-gray-900">Suggested channels</h3>
                    <p className="text-xs text-gray-400 mt-0.5">
                      Pending suggestions for this strategy. Hit Refresh to get a fresh AI batch.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleRefreshSuggestions}
                    disabled={refreshing}
                    className="flex items-center gap-1.5 text-xs font-medium text-indigo-600 hover:text-indigo-700 disabled:opacity-50 border border-indigo-200 hover:border-indigo-400 px-3 py-1.5 rounded-md transition-colors"
                  >
                    {refreshing ? (
                      <>
                        <svg className="w-3.5 h-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3V4a8 8 0 00-8 8z" />
                        </svg>
                        Refreshing…
                      </>
                    ) : (
                      <>
                        <svg className="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor">
                          <path fillRule="evenodd" d="M4 2a1 1 0 011 1v2.101a7.002 7.002 0 0111.601 2.566 1 1 0 11-1.885.666A5.002 5.002 0 005.999 7H9a1 1 0 010 2H4a1 1 0 01-1-1V3a1 1 0 011-1zm.008 9.057a1 1 0 011.276.61A5.002 5.002 0 0014.001 13H11a1 1 0 110-2h5a1 1 0 011 1v5a1 1 0 11-2 0v-2.101a7.002 7.002 0 01-11.601-2.566 1 1 0 01.61-1.276z" clipRule="evenodd" />
                        </svg>
                        Refresh suggestions
                      </>
                    )}
                  </button>
                </div>

                {suggestionsLoading ? (
                  <div className="flex items-center gap-2 text-sm text-gray-400 py-4 justify-center">
                    <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3V4a8 8 0 00-8 8z" />
                    </svg>
                    Loading suggestions…
                  </div>
                ) : editSuggestedChannels.length === 0 ? (
                  <div className="text-center py-6">
                    <p className="text-sm text-gray-400">No pending suggestions.</p>
                    <p className="text-xs text-gray-300 mt-1">Click "Refresh suggestions" to generate a new batch with AI.</p>
                  </div>
                ) : (
                  <div className="flex flex-col gap-2">
                    {editSuggestedChannels.map((ch) => (
                      <ChannelCard key={ch.id} channel={ch} onAction={handleEditChannelAction} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Input form — hidden once results arrive */}
            {!result && (showNewForm || !editStrategy) && (
              <form
                onSubmit={handleSubmit}
                className="bg-white border border-gray-200 rounded-xl p-6 flex flex-col gap-4"
              >
                {showNewForm && (
                  <div className="flex items-center gap-3 -mt-1 mb-1">
                    <button
                      type="button"
                      onClick={() => setShowNewForm(false)}
                      className="text-xs text-gray-400 hover:text-gray-600"
                    >
                      ← Back
                    </button>
                    <span className="text-sm font-medium text-gray-700">Create new strategy</span>
                  </div>
                )}
                {error && <Alert type="error" message={error} />}

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Business name / title <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <p className="text-xs text-gray-400 mb-2">
                    Give this analysis a name so you can filter channels and leads by it later (e.g. "Acme Corp", "SaaS Product Launch").
                  </p>
                  <input
                    type="text"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    maxLength={255}
                    placeholder="e.g. Acme Corp, Q4 Campaign, My SaaS Product…"
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Describe your business <span className="text-red-500">*</span>
                  </label>
                  <p className="text-xs text-gray-400 mb-2">
                    Write freely — who you help, what problem you solve, your ideal customer, keywords, etc.
                    Claude will structure it for you.
                  </p>
                  <textarea
                    required
                    rows={7}
                    value={userText}
                    onChange={(e) => setUserText(e.target.value)}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                    placeholder={
                      "e.g. We help B2B SaaS companies reduce churn by identifying at-risk customers " +
                      "using product usage signals. Our ideal customers are customer success managers " +
                      "at SaaS companies with 50–500 seats. Keywords: churn, customer success, " +
                      "product analytics, SaaS retention."
                    }
                  />
                </div>

                {/* Target locations */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Target locations <span className="text-gray-400 font-normal">(optional)</span>
                  </label>
                  <p className="text-xs text-gray-400 mb-2">
                    Only show leads from these countries, states, or regions. Leave empty to show leads from everywhere.
                  </p>
                  <div className="flex flex-wrap gap-1.5 mb-2">
                    {targetLocations.map((loc) => (
                      <span
                        key={loc}
                        className="inline-flex items-center gap-1 px-2.5 py-1 bg-indigo-50 text-indigo-700 text-xs rounded-full border border-indigo-200"
                      >
                        {loc}
                        <button
                          type="button"
                          onClick={() => setTargetLocations((prev) => prev.filter((l) => l !== loc))}
                          className="text-indigo-400 hover:text-indigo-700 leading-none"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                  </div>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={locationInput}
                      onChange={(e) => setLocationInput(e.target.value)}
                      onKeyDown={(e) => {
                        if ((e.key === "Enter" || e.key === ",") && locationInput.trim()) {
                          e.preventDefault();
                          const loc = locationInput.trim().replace(/,$/, "");
                          if (loc && !targetLocations.includes(loc)) {
                            setTargetLocations((prev) => [...prev, loc]);
                          }
                          setLocationInput("");
                        }
                      }}
                      placeholder="e.g. India, California, Germany — press Enter to add"
                      className="flex-1 border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        const loc = locationInput.trim();
                        if (loc && !targetLocations.includes(loc)) {
                          setTargetLocations((prev) => [...prev, loc]);
                        }
                        setLocationInput("");
                      }}
                      disabled={!locationInput.trim()}
                      className="px-3 py-2 text-sm border border-gray-300 rounded-md text-gray-600 hover:bg-gray-50 disabled:opacity-40"
                    >
                      Add
                    </button>
                  </div>
                </div>

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={loading || userText.trim().length < 20}
                    className="bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white font-medium px-5 py-2 rounded-md text-sm transition-colors flex items-center gap-2"
                  >
                    {loading && (
                      <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4l3-3-3-3V4a8 8 0 00-8 8z" />
                      </svg>
                    )}
                    {loading ? "Analyzing…" : "Analyze with AI"}
                  </button>
                </div>
              </form>
            )}{/* end new-form */}

            {/* Results */}
            {result && (
              <div className="flex flex-col gap-6">

                {/* Strategy summary */}
                <div className="bg-white border border-gray-200 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Strategy extracted</h3>
                      {result.strategy.title && (
                        <p className="text-xs text-indigo-600 font-medium mt-0.5">{result.strategy.title}</p>
                      )}
                    </div>
                    <button
                      onClick={() => { setResult(null); setChannels([]); setUserText(""); setTitle(""); }}
                      className="text-xs text-indigo-600 hover:underline"
                    >
                      Analyze again
                    </button>
                  </div>
                  <div className="flex flex-col gap-3 text-sm">
                    {result.strategy.target_locations?.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-gray-500 mb-0.5">TARGET LOCATIONS</p>
                        <div className="flex flex-wrap gap-1.5">
                          {result.strategy.target_locations.map((loc: string) => (
                            <span key={loc} className="px-2 py-0.5 bg-blue-50 text-blue-700 text-xs rounded-full border border-blue-100">
                              {loc}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-0.5">PROBLEM SOLVED</p>
                      <p className="text-gray-800">{result.strategy.main_problem}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-0.5">IDEAL CUSTOMER</p>
                      <p className="text-gray-800">{result.strategy.ideal_customer}</p>
                    </div>
                    <div>
                      <p className="text-xs font-medium text-gray-500 mb-1">KEYWORDS</p>
                      <div className="flex flex-wrap gap-1.5">
                        {result.strategy.keywords.map((kw) => (
                          <span key={kw} className="px-2 py-0.5 bg-indigo-50 text-indigo-700 text-xs rounded-full border border-indigo-100">
                            {kw}
                          </span>
                        ))}
                      </div>
                    </div>
                    {result.strategy.buyer_phrases?.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-gray-500 mb-1">BUYER PHRASES</p>
                        <div className="flex flex-wrap gap-1.5">
                          {result.strategy.buyer_phrases.map((bp) => (
                            <span key={bp} className="px-2 py-0.5 bg-amber-50 text-amber-700 text-xs rounded-full border border-amber-100">
                              {bp}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Suggested channels */}
                <div className="bg-white border border-gray-200 rounded-xl p-6">
                  <div className="flex items-center justify-between mb-4">
                    <div>
                      <h3 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">Suggested channels</h3>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Watch channels you want the AI to monitor for leads.
                      </p>
                    </div>
                    {watchingCount > 0 && (
                      <span className="text-xs bg-green-50 text-green-700 ring-1 ring-green-600/20 px-2.5 py-1 rounded-full font-medium">
                        {watchingCount} watching
                      </span>
                    )}
                  </div>

                  {channels.length === 0 ? (
                    <p className="text-sm text-gray-400">No channels suggested.</p>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {channels.map((ch) => (
                        <ChannelCard key={ch.id} channel={ch} onAction={handleChannelAction} />
                      ))}
                    </div>
                  )}
                </div>

                {/* Actions */}
                <div className="flex justify-end gap-3">
                  <button
                    onClick={() => navigate("/dashboard/channels")}
                    className="text-sm border border-gray-200 hover:bg-gray-100 text-gray-600 px-4 py-2 rounded-md font-medium transition-colors"
                  >
                    View all channels
                  </button>
                  <button
                    onClick={() => navigate("/dashboard/leads")}
                    className="text-sm bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-md font-medium transition-colors"
                  >
                    Go to Leads →
                  </button>
                </div>
              </div>
            )}

          </div>
        </main>
      </div>
    </div>
  );
}
