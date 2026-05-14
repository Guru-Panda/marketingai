import { useEffect, useState, FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, auth } from "../api/client";
import Navbar from "../components/Navbar";
import Sidebar from "../components/Sidebar";
import Alert from "../components/Alert";

interface UserProfile {
  id: number;
  email: string;
  company_name: string | null;
  employee_count: string | null;
  is_verified: boolean;
  created_at: string;
}

const employeeOptions = [
  { value: "5-50", label: "5 – 50 employees" },
  { value: "51-500", label: "51 – 500 employees" },
];

function initials(email: string) {
  return email.slice(0, 2).toUpperCase();
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
}

export default function Profile() {
  const navigate = useNavigate();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [form, setForm] = useState({ company_name: "", employee_count: "" });
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get<UserProfile>("/users/me", auth.accessToken()).then((data) => {
      setProfile(data);
      setForm({
        company_name: data.company_name ?? "",
        employee_count: data.employee_count ?? "",
      });
    }).catch(() => {
      navigate("/auth/login");
    });
  }, [navigate]);

  async function handleSave(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setStatus(null);
    try {
      const updated = await api.patch<UserProfile>("/users/me", {
        company_name: form.company_name || null,
        employee_count: form.employee_count || null,
      }, auth.accessToken());
      setProfile(updated);
      setStatus({ type: "success", message: "Profile updated." });
    } catch (err) {
      setStatus({ type: "error", message: err instanceof Error ? err.message : "Failed to save" });
    } finally {
      setSaving(false);
    }
  }

  function handleSignOut() {
    auth.clear();
    navigate("/auth/login");
  }

  if (!profile) {
    return (
      <div className="flex flex-col h-screen">
        <Navbar />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <main className="flex-1 flex items-center justify-center text-sm text-gray-400">Loading…</main>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      <Navbar />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto bg-gray-50 p-8">
          <div className="max-w-xl mx-auto">

            {/* Avatar + identity */}
            <div className="flex items-center gap-5 mb-8">
              <div className="w-16 h-16 rounded-full bg-indigo-600 flex items-center justify-center text-white text-xl font-bold shrink-0">
                {initials(profile.email)}
              </div>
              <div>
                <h1 className="text-xl font-semibold text-gray-900">{profile.email}</h1>
                <p className="text-sm text-gray-400 mt-0.5">Member since {formatDate(profile.created_at)}</p>
              </div>
            </div>

            {/* Edit form */}
            <div className="bg-white border border-gray-200 rounded-xl p-6 mb-4">
              <h2 className="text-sm font-semibold text-gray-700 mb-4">Account details</h2>

              {status && <div className="mb-4"><Alert type={status.type} message={status.message} /></div>}

              <form onSubmit={handleSave} className="flex flex-col gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                  <input
                    type="email"
                    disabled
                    value={profile.email}
                    className="w-full border border-gray-200 rounded-md px-3 py-2 text-sm bg-gray-50 text-gray-400 cursor-not-allowed"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Company name</label>
                  <input
                    type="text"
                    value={form.company_name}
                    onChange={(e) => setForm((f) => ({ ...f, company_name: e.target.value }))}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    placeholder="Acme Inc."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Team size</label>
                  <select
                    value={form.employee_count}
                    onChange={(e) => setForm((f) => ({ ...f, employee_count: e.target.value }))}
                    className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 bg-white"
                  >
                    <option value="">Select…</option>
                    {employeeOptions.map((o) => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                  </select>
                </div>

                <button
                  type="submit"
                  disabled={saving}
                  className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-medium py-2 rounded-md text-sm transition-colors"
                >
                  {saving ? "Saving…" : "Save changes"}
                </button>
              </form>
            </div>

            {/* Sign out */}
            <div className="bg-white border border-gray-200 rounded-xl p-6">
              <h2 className="text-sm font-semibold text-gray-700 mb-1">Session</h2>
              <p className="text-sm text-gray-400 mb-4">You are signed in as <span className="text-gray-600">{profile.email}</span>.</p>
              <button
                onClick={handleSignOut}
                className="w-full border border-red-200 text-red-500 hover:bg-red-50 font-medium py-2 rounded-md text-sm transition-colors"
              >
                Sign out
              </button>
            </div>

          </div>
        </main>
      </div>
    </div>
  );
}
