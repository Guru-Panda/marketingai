import { useEffect, useState } from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";
import { api, auth } from "../api/client";

interface StrategyTitle {
  id: number;
  title: string | null;
}

const ACTIVE_STRATEGY_KEY = "active_strategy_id";

export function getActiveStrategyId(): number | undefined {
  const v = localStorage.getItem(ACTIVE_STRATEGY_KEY);
  return v ? Number(v) : undefined;
}

const links = [
  {
    to: "/dashboard/business",
    label: "Strategy",
    icon: (
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
      </svg>
    ),
  },
  {
    to: "/dashboard/channels",
    label: "Monitor",
    icon: (
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
        <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
  {
    to: "/dashboard/leads",
    label: "Leads",
    icon: (
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
  },
  {
    to: "/dashboard/analytics",
    label: "Analytics",
    icon: (
      <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
        <path strokeLinecap="round" strokeLinejoin="round"
          d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
  },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const email = localStorage.getItem("user_email") ?? "";
  const initials = email ? email[0].toUpperCase() : "U";

  const [strategies, setStrategies] = useState<StrategyTitle[]>([]);
  const [activeId, setActiveId] = useState<number | undefined>(getActiveStrategyId);

  useEffect(() => {
    api.get<StrategyTitle[]>("/business/titles", auth.accessToken())
      .then(setStrategies)
      .catch(() => {});
  }, []);

  function selectStrategy(id: number) {
    localStorage.setItem(ACTIVE_STRATEGY_KEY, String(id));
    setActiveId(id);
    // Navigate to leads with the selected strategy context
    navigate("/dashboard/leads");
    // Dispatch storage event so LeadsTable can react
    window.dispatchEvent(new Event("active_strategy_changed"));
  }

  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col py-4 shrink-0">
      <nav className="flex flex-col gap-1 px-3">
        {links.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-2.5 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`
            }
          >
            {icon}
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Strategy switcher */}
      {strategies.length > 0 && (
        <div className="px-3 mt-4">
          <div className="flex items-center justify-between px-1 mb-1.5">
            <span className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Strategies</span>
            <Link
              to="/dashboard/business"
              className="text-xs text-indigo-500 hover:text-indigo-700 font-medium"
              title="New strategy"
            >
              +
            </Link>
          </div>
          <div className="flex flex-col gap-0.5">
            {strategies.map((s) => {
              const isActive = activeId === s.id;
              return (
                <button
                  key={s.id}
                  onClick={() => selectStrategy(s.id)}
                  className={`w-full text-left flex items-center gap-2 px-3 py-1.5 rounded-md text-xs transition-colors ${
                    isActive
                      ? "bg-indigo-50 text-indigo-700 font-medium"
                      : "text-gray-500 hover:bg-gray-100 hover:text-gray-700"
                  }`}
                >
                  <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${isActive ? "bg-indigo-500" : "bg-gray-300"}`} />
                  <span className="truncate">{s.title ?? `Strategy #${s.id}`}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Spacer */}
      <div className="flex-1" />

      {/* User footer */}
      <div className="px-3 pt-3 border-t border-gray-100 mt-2">
        <Link
          to="/dashboard/profile"
          className="flex items-center gap-2.5 px-3 py-2 rounded-md hover:bg-gray-100 transition-colors"
        >
          <div className="w-6 h-6 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xs font-bold shrink-0">
            {initials}
          </div>
          <span className="text-xs text-gray-500 truncate">{email || "Profile"}</span>
        </Link>
      </div>
    </aside>
  );
}
