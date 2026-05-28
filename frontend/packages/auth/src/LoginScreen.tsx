/**
 * LoginScreen — the unauth'd state. Uses brand-runtime tokens automatically.
 * Phase 1: bootstrap admin email/password form.
 */
import { useState, type FormEvent } from "react";
import { useAuth } from "./AuthProvider";

interface Props {
  brandName?: string;
  brandLogoUrl?: string;
}

export function LoginScreen({ brandName = "Insights Navigator", brandLogoUrl }: Props) {
  const { login, status, error } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    void login({ email, password });
  }

  const submitting = status === "loading";

  return (
    <div className="min-h-screen bg-ink-900 text-ink-100 grid place-items-center p-6">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm border border-ink-700/60 rounded-lg p-6 bg-ink-800/40 space-y-4"
      >
        <div className="flex items-center gap-2 mb-2">
          {brandLogoUrl ? (
            <img src={brandLogoUrl} alt={brandName} className="h-7 w-7" />
          ) : (
            <div className="h-7 w-7 rounded-md bg-accent/15 ring-1 ring-accent/30 grid place-items-center text-accent">
              ✦
            </div>
          )}
          <div>
            <div className="text-sm font-semibold">{brandName}</div>
            <div className="text-[11px] text-ink-300">Sign in</div>
          </div>
        </div>

        <label className="block">
          <span className="text-[11px] uppercase tracking-wider text-ink-300">Email</span>
          <input
            type="email"
            required
            autoFocus
            autoComplete="email"
            className="mt-1 w-full bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </label>

        <label className="block">
          <span className="text-[11px] uppercase tracking-wider text-ink-300">Password</span>
          <input
            type="password"
            required
            autoComplete="current-password"
            className="mt-1 w-full bg-ink-900 border border-ink-700/60 rounded px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-accent"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </label>

        {error && (
          <div className="text-[12px] text-red-400 border border-red-900/60 bg-red-950/40 rounded px-2 py-1">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-accent text-accent-foreground font-semibold py-2 rounded hover:opacity-90 disabled:opacity-50 transition-opacity"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>

        <div className="text-[11px] text-ink-300 text-center pt-1">
          Bootstrap admin only · Firebase Auth ships in Phase 1.5
        </div>
      </form>
    </div>
  );
}
