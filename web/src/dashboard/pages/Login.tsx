// Sign-in page. Collects email + password, calls useAuth().login, and on success
// routes into the dashboard. ApiError messages surface inline.

import { useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import { ApiError } from "../api2";

const PASSWORD_MIN = 8;

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);

    if (password.length < PASSWORD_MIN) {
      setError(`Password must be at least ${PASSWORD_MIN} characters.`);
      return;
    }

    setSubmitting(true);
    try {
      await login(email.trim(), password);
      navigate("/app");
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const fieldClass =
    "w-full px-4 py-2.5 text-sm bg-background border border-border rounded-lg outline-none focus:border-ring focus:ring-2 focus:ring-ring/25 transition-colors placeholder:text-muted-foreground/50";

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 py-16">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Sign in
        </h1>
        <p className="mt-2 mb-8 text-sm text-muted-foreground leading-relaxed">
          Welcome back. Sign in to your Simulation Labs dashboard.
        </p>

        <form className="flex flex-col gap-5" onSubmit={onSubmit} noValidate>
          <label className="flex flex-col gap-2">
            <span className="text-xs text-muted-foreground">Email</span>
            <input
              className={fieldClass}
              type="email"
              name="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              autoComplete="email"
              autoFocus
              required
            />
          </label>

          <label className="flex flex-col gap-2">
            <span className="text-xs text-muted-foreground">Password</span>
            <input
              className={fieldClass}
              type="password"
              name="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete="current-password"
              minLength={PASSWORD_MIN}
              required
            />
          </label>

          {error && (
            <p className="text-sm text-fail" role="alert">
              {error}
            </p>
          )}

          <button
            type="submit"
            className="w-full py-2.5 rounded-lg bg-primary text-primary-foreground text-sm font-medium hover:opacity-90 transition-opacity disabled:opacity-40"
            disabled={submitting}
          >
            {submitting ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="mt-6 text-sm text-muted-foreground">
          Don&apos;t have an account?{" "}
          <Link
            to="/signup"
            className="text-foreground underline underline-offset-2 hover:opacity-80 transition-opacity"
          >
            Sign up
          </Link>
        </p>
      </div>
    </div>
  );
}
