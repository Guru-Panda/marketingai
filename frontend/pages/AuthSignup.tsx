import { useState, FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, auth } from "../api/client";
import Alert from "../components/Alert";

type Step = "email" | "otp" | "details";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
}

const employeeOptions = [
  { value: "5-50", label: "5 – 50 employees" },
  { value: "51-500", label: "51 – 500 employees" },
];

export default function AuthSignup() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>("email");
  const [email, setEmail] = useState("");
  const [otpCode, setOtpCode] = useState("");
  const [verifiedToken, setVerifiedToken] = useState("");
  const [details, setDetails] = useState({ password: "", company_name: "", employee_count: "" });
  const [status, setStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const [loading, setLoading] = useState(false);

  function setDetail(field: string, value: string) {
    setDetails((d) => ({ ...d, [field]: value }));
  }

  async function handleSendOtp(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setStatus(null);
    try {
      const res = await api.post<{ detail: string; otp_hint?: string }>("/auth/send-otp", { email });
      const hint = res.otp_hint ? ` (code: ${res.otp_hint})` : "";
      setStatus({ type: "success", message: `Verification code sent — check your inbox.${hint}` });
      setStep("otp");
    } catch (err) {
      setStatus({ type: "error", message: err instanceof Error ? err.message : "Failed to send code" });
    } finally {
      setLoading(false);
    }
  }

  async function handleVerifyOtp(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setStatus(null);
    try {
      const res = await api.post<{ verified_token: string }>("/auth/verify-otp", { email, otp_code: otpCode });
      setVerifiedToken(res.verified_token);
      setStatus(null);
      setStep("details");
    } catch (err) {
      setStatus({ type: "error", message: err instanceof Error ? err.message : "Invalid code" });
    } finally {
      setLoading(false);
    }
  }

  async function handleCompleteSignup(e: FormEvent) {
    e.preventDefault();
    setLoading(true);
    setStatus(null);
    try {
      await api.post("/auth/complete-signup", {
        verified_token: verifiedToken,
        password: details.password,
        company_name: details.company_name || undefined,
        employee_count: details.employee_count || undefined,
      });
      const tokens = await api.post<TokenResponse>("/auth/login", {
        email,
        password: details.password,
      });
      auth.save(tokens.access_token, tokens.refresh_token, email);
      navigate("/dashboard/business");
    } catch (err) {
      setStatus({ type: "error", message: err instanceof Error ? err.message : "Signup failed" });
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-md bg-white rounded-xl shadow-sm border border-gray-200 p-8">

        {/* Step indicator */}
        <div className="flex items-center gap-2 mb-6">
          {(["email", "otp", "details"] as Step[]).map((s, i) => (
            <div key={s} className="flex items-center gap-2">
              <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold
                ${step === s ? "bg-indigo-600 text-white" :
                  (["email", "otp", "details"].indexOf(step) > i ? "bg-indigo-100 text-indigo-600" : "bg-gray-100 text-gray-400")}`}>
                {i + 1}
              </div>
              {i < 2 && <div className={`flex-1 h-px w-8 ${["email", "otp", "details"].indexOf(step) > i ? "bg-indigo-300" : "bg-gray-200"}`} />}
            </div>
          ))}
        </div>

        {status && <div className="mb-4"><Alert type={status.type} message={status.message} /></div>}

        {/* Step 1: Email */}
        {step === "email" && (
          <>
            <h1 className="text-2xl font-bold text-gray-900 mb-1">Create account</h1>
            <p className="text-sm text-gray-500 mb-6">We'll send a verification code to your email.</p>
            <form onSubmit={handleSendOtp} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="you@company.com"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="mt-2 w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-medium py-2 rounded-md text-sm transition-colors"
              >
                {loading ? "Sending…" : "Send verification code"}
              </button>
            </form>
          </>
        )}

        {/* Step 2: OTP */}
        {step === "otp" && (
          <>
            <h1 className="text-2xl font-bold text-gray-900 mb-1">Check your inbox</h1>
            <p className="text-sm text-gray-500 mb-6">
              Enter the 6-digit code sent to <span className="font-medium text-gray-700">{email}</span>.
            </p>
            <form onSubmit={handleVerifyOtp} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Verification code</label>
                <input
                  type="text"
                  required
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value.replace(/\D/g, ""))}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500 tracking-widest text-center text-lg"
                  placeholder="000000"
                />
              </div>
              <button
                type="submit"
                disabled={loading || otpCode.length !== 6}
                className="mt-2 w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-medium py-2 rounded-md text-sm transition-colors"
              >
                {loading ? "Verifying…" : "Verify code"}
              </button>
              <button
                type="button"
                onClick={() => { setStep("email"); setStatus(null); setOtpCode(""); }}
                className="text-sm text-indigo-600 hover:underline text-center"
              >
                Use a different email
              </button>
            </form>
          </>
        )}

        {/* Step 3: Details */}
        {step === "details" && (
          <>
            <h1 className="text-2xl font-bold text-gray-900 mb-1">Set up your account</h1>
            <p className="text-sm text-gray-500 mb-6">Almost there — just a few more details.</p>
            <form onSubmit={handleCompleteSignup} className="flex flex-col gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                  type="password"
                  required
                  minLength={8}
                  value={details.password}
                  onChange={(e) => setDetail("password", e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Min. 8 characters"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Company name</label>
                <input
                  type="text"
                  value={details.company_name}
                  onChange={(e) => setDetail("company_name", e.target.value)}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  placeholder="Acme Inc."
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Team size</label>
                <select
                  value={details.employee_count}
                  onChange={(e) => setDetail("employee_count", e.target.value)}
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
                disabled={loading}
                className="mt-2 w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white font-medium py-2 rounded-md text-sm transition-colors"
              >
                {loading ? "Creating account…" : "Create account"}
              </button>
            </form>
          </>
        )}

        <p className="mt-5 text-center text-sm text-gray-500">
          Already have an account?{" "}
          <Link to="/auth/login" className="text-indigo-600 hover:underline font-medium">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
