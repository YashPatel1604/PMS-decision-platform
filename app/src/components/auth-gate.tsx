"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { AppShell } from "@/components/app-shell";
import { ApiError, api, type AuthUser } from "@/lib/api";

type AuthState = {
  authDisabled: boolean;
  user: AuthUser | null;
};

const CLIENT_PATHS = [
  "/strategy/pivot-point",
  "/strategy/charts",
  "/strategy/client-portfolio",
  "/strategy/sca-llp",
  "/strategy/sheets",
  "/block-deals",
  "/bulk-deals",
  "/sast",
  "/insider-trading",
];

function clientHome(role: string | undefined): string {
  return role === "client" ? "/strategy/pivot-point" : "/";
}

function isClientOnlyPath(pathname: string): boolean {
  return CLIENT_PATHS.some((path) => pathname === path || pathname.startsWith(`${path}/`));
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const isLogin = pathname === "/login";

  const meQuery = useQuery({
    queryKey: ["auth-me"],
    queryFn: async (): Promise<AuthState> => {
      try {
        const me = await api.getMe();
        return { authDisabled: me.auth_disabled, user: me.user };
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) {
          return { authDisabled: false, user: null };
        }
        throw err;
      }
    },
    retry: false,
    staleTime: 60_000,
  });

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* still clear local session view */
    }
    await queryClient.invalidateQueries({ queryKey: ["auth-me"] });
    router.replace("/login");
  }, [queryClient, router]);

  useEffect(() => {
    if (!meQuery.isSuccess) return;
    const { authDisabled, user } = meQuery.data;
    if (authDisabled) return;
    if (!user && !isLogin) {
      router.replace("/login");
    }
    if (user && isLogin) {
      router.replace(clientHome(user.role));
    }
    if (user?.role === "client" && !isLogin && !isClientOnlyPath(pathname)) {
      router.replace("/strategy/pivot-point");
    }
  }, [meQuery.isSuccess, meQuery.data, isLogin, pathname, router]);

  if (meQuery.isLoading) {
    // Login page can render while session check runs (avoids blank forever on slow API).
    if (isLogin) {
      return <>{children}</>;
    }
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50 text-sm text-stone-500">
        Checking session…
      </div>
    );
  }

  if (meQuery.isError) {
    if (isLogin) {
      return <>{children}</>;
    }
    return (
      <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-stone-50 px-6 text-center text-sm text-stone-600">
        <p>
          Cannot reach API via{" "}
          <code className="mx-1 rounded bg-stone-200 px-1">
            {process.env.NEXT_PUBLIC_API_URL ?? "/backend"}
          </code>
          . Is Docker <code className="mx-1 rounded bg-stone-200 px-1">api</code> running?
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded-lg bg-emerald-700 px-3 py-1.5 text-xs font-medium text-white"
            onClick={() => void meQuery.refetch()}
          >
            Retry
          </button>
          <button
            type="button"
            className="rounded-lg border border-stone-300 bg-white px-3 py-1.5 text-xs font-medium text-stone-800"
            onClick={() => router.replace("/login")}
          >
            Go to login
          </button>
        </div>
      </div>
    );
  }

  const { authDisabled, user } = meQuery.data ?? {
    authDisabled: true,
    user: null,
  };

  if (!authDisabled && !user) {
    if (isLogin) {
      return <>{children}</>;
    }
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50 text-sm text-stone-500">
        Redirecting to login…
      </div>
    );
  }

  if (isLogin) {
    return <>{children}</>;
  }

  return (
    <AppShell user={authDisabled ? null : user} onLogout={authDisabled ? undefined : logout}>
      {children}
    </AppShell>
  );
}
