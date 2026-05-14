import { NavLink } from "react-router-dom";

const links = [
  { to: "/dashboard/leads", label: "Leads" },
  { to: "/dashboard/channels", label: "Channels" },
  { to: "/dashboard/business", label: "Business Strategy" },
];

export default function Sidebar() {
  return (
    <aside className="w-56 bg-gray-50 border-r border-gray-200 flex flex-col py-4 shrink-0">
      <nav className="flex flex-col gap-1 px-3">
        {links.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? "bg-indigo-100 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
              }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
