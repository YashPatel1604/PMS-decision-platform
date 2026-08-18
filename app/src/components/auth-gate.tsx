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
      router.replace("/");
    }
  }, [meQuery.isSuccess, meQuery.data, isLogin, router]);

  if (meQuery.isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50 text-sm text-stone-500">
        Checking session…
      </div>
    );
  }

  if (meQuery.isError) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-stone-50 px-6 text-center text-sm text-stone-600">
        Cannot reach API. Is it running on{" "}
        <code className="mx-1 rounded bg-stone-200 px-1">
          {process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000"}
        </code>
        ?
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
