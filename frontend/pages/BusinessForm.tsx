import { FormEvent, useState } from "react";
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
  target_locations: string[];
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

            {/* Input form — hidden once results arrive */}
            {!result && (
              <form
                onSubmit={handleSubmit}
                className="bg-white border border-gray-200 rounded-xl p-6 flex flex-col gap-4"
              >
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
            )}

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
