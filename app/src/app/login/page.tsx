"use client";

import { type FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError, api } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await api.login(email.trim(), password);
      await queryClient.invalidateQueries({ queryKey: ["auth-me"] });
      router.replace("/");
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.status === 401 ? "Invalid email or password" : err.message);
      } else {
        setError("Login failed");
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-stone-100 via-emerald-50/40 to-stone-100 px-4">
      <div className="w-full max-w-md">
        <p className="mb-2 text-center text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
          PMS Decision Platform
        </p>
        <h1 className="mb-8 text-center text-2xl font-semibold text-stone-900">Sign in</h1>
        <form
          onSubmit={onSubmit}
          className="space-y-4 rounded-2xl border border-stone-200 bg-white p-6 shadow-sm"
        >
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-stone-700">Email</span>
            <input
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-stone-900 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
            />
          </label>
          <label className="block text-sm">
            <span className="mb-1 block font-medium text-stone-700">Password</span>
            <input
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-stone-300 px-3 py-2 text-stone-900 outline-none focus:border-emerald-600 focus:ring-1 focus:ring-emerald-600"
            />
          </label>
          {error ? <p className="text-sm text-red-600">{error}</p> : null}
          <button
            type="submit"
            disabled={pending}
            className="w-full rounded-lg bg-emerald-700 px-3 py-2.5 text-sm font-semibold text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="mt-4 text-center text-xs text-stone-500">
          Invite-only accounts. Ask an admin if you need access.
        </p>
      </div>
    </div>
  );
}
