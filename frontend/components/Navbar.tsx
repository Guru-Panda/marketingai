import { Link } from "react-router-dom";

export default function Navbar() {
  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
      <Link to="/dashboard/leads" className="text-lg font-semibold text-indigo-600 tracking-tight">
        MarketingAI
      </Link>
      <Link
        to="/dashboard/profile"
        className="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center hover:bg-indigo-700 transition-colors"
        title="Your profile"
      >
        <svg className="w-4 h-4 text-white" viewBox="0 0 20 20" fill="currentColor">
          <path d="M10 10a4 4 0 100-8 4 4 0 000 8z" />
          <path d="M2 18a8 8 0 0116 0H2z" />
        </svg>
      </Link>
    </header>
  );
}
