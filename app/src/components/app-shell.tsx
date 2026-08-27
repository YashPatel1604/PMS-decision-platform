"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, type AuthUser } from "@/lib/api";

type NavLink = {
  href: string;
  label: string;
  badgeKey?: "watchlists" | "approvals";
};

type NavGroup = {
  label: string;
  links: NavLink[];
};

const dashboardLink: NavLink = { href: "/", label: "Dashboard" };

const navGroups: NavGroup[] = [
  {
    label: "Portfolio",
    links: [
      { href: "/holdings", label: "Holdings" },
      { href: "/episodes", label: "Episodes" },
      { href: "/watchlists", label: "Watchlists", badgeKey: "watchlists" },
    ],
  },
  {
    label: "Market",
    links: [
      { href: "/block-deals", label: "Block Deals" },
      { href: "/bulk-deals", label: "Bulk Deals" },
      { href: "/sast", label: "SAST" },
      { href: "/insider-trading", label: "Insider Trading" },
    ],
  },
  {
    label: "Client",
    links: [
      { href: "/strategy/pivot-point", label: "Pivot Point" },
      { href: "/strategy/charts", label: "Charts" },
      { href: "/strategy/client-portfolio", label: "Client Portfolio" },
      { href: "/strategy/sca-llp", label: "SCA LLP" },
      { href: "/strategy/approvals", label: "Approvals", badgeKey: "approvals" },
    ],
  },
  {
    label: "Strategy",
    links: [{ href: "/strategy/continuous-loss", label: "1-Year Loss" }],
  },
  {
    label: "Admin",
    links: [
      { href: "/masters", label: "Masters" },
      { href: "/data", label: "Data" },
    ],
  },
];

function pathMatches(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      aria-hidden
      className={`h-3.5 w-3.5 shrink-0 text-stone-400 transition-transform ${open ? "rotate-180" : ""}`}
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 10.94l3.71-3.71a.75.75 0 1 1 1.06 1.06l-4.24 4.24a.75.75 0 0 1-1.06 0L5.21 8.29a.75.75 0 0 1 .02-1.08Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function NavDropdown({
  group,
  open,
  onToggle,
  onClose,
  unacknowledgedAlerts,
  pendingApprovals,
}: {
  group: NavGroup;
  open: boolean;
  onToggle: () => void;
  onClose: () => void;
  unacknowledgedAlerts: number;
  pendingApprovals: number;
}) {
  const pathname = usePathname();
  const menuId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const groupActive = group.links.some((link) => pathMatches(pathname, link.href));
  const groupBadge = group.links.reduce((sum, link) => {
    if (link.badgeKey === "watchlists" && unacknowledgedAlerts > 0) {
      return sum + unacknowledgedAlerts;
    }
    if (link.badgeKey === "approvals" && pendingApprovals > 0) {
      return sum + pendingApprovals;
    }
    return sum;
  }, 0);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) onClose();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, onClose]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="menu"
        aria-controls={menuId}
        onClick={onToggle}
        className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm font-medium transition hover:bg-stone-100 hover:text-stone-900 ${
          groupActive || open ? "bg-stone-100 text-stone-900" : "text-stone-600"
        }`}
      >
        {group.label}
        {groupBadge > 0 ? (
          <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
            {groupBadge > 99 ? "99+" : groupBadge}
          </span>
        ) : null}
        <Chevron open={open} />
      </button>
      {open ? (
        <div
          id={menuId}
          role="menu"
          className="absolute left-0 z-50 mt-1 min-w-[11rem] rounded-lg border border-stone-200 bg-white py-1 shadow-lg"
        >
          {group.links.map((link) => {
            const active = pathMatches(pathname, link.href);
            return (
              <Link
                key={link.href}
                href={link.href}
                role="menuitem"
                onClick={onClose}
                className={`flex items-center justify-between gap-3 px-3 py-2 text-sm transition hover:bg-stone-50 ${
                  active ? "bg-emerald-50 font-semibold text-emerald-900" : "text-stone-700"
                }`}
              >
                <span>{link.label}</span>
                {link.badgeKey === "watchlists" && unacknowledgedAlerts > 0 ? (
                  <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                    {unacknowledgedAlerts > 99 ? "99+" : unacknowledgedAlerts}
                  </span>
                ) : null}
                {link.badgeKey === "approvals" && pendingApprovals > 0 ? (
                  <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-white">
                    {pendingApprovals > 99 ? "99+" : pendingApprovals}
                  </span>
                ) : null}
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

export function AppShell({
  children,
  user,
  onLogout,
}: {
  children: React.ReactNode;
  user?: AuthUser | null;
  onLogout?: () => void;
}) {
  const pathname = usePathname();
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [openGroup, setOpenGroup] = useState<string | null>(null);

  const alertsSummaryQuery = useQuery({
    queryKey: ["watchlist-alerts-summary"],
    queryFn: () => api.getWatchlistAlertsSummary(),
    refetchInterval: 5 * 60 * 1000,
    enabled: user?.role !== "client",
  });

  const approvalsSummaryQuery = useQuery({
    queryKey: ["change-requests-summary"],
    queryFn: () => api.getChangeRequestsSummary(),
    refetchInterval: 15_000,
    enabled: user?.role === "admin",
    retry: false,
  });

  const unacknowledgedAlerts = alertsSummaryQuery.data?.unacknowledged ?? 0;
  const pendingApprovals = approvalsSummaryQuery.data?.pending_submitted ?? 0;
  const visibleGroups =
    user?.role === "client"
      ? navGroups.filter((group) => group.label === "Client" || group.label === "Market")
      : navGroups;
  const showChrome = user?.role !== "client";

  useEffect(() => {
    setOpenGroup(null);
  }, [pathname]);

  const refreshMutation = useMutation({
    mutationFn: () => api.refreshFromOnedrive(),
    onSuccess: (result) => {
      void queryClient.invalidateQueries();
      if (result.ok && result.reimport) {
        const extra = (result.notes ?? []).filter(Boolean).join(" · ");
        setMessage(
          `Synced ${result.sync.snapshot_count} snapshots · ${result.reimport.episodes} episodes` +
            (extra ? ` · ${extra}` : ""),
        );
      } else {
        setMessage(result.error ?? "Refresh finished with errors");
      }
    },
    onError: (err: Error) => setMessage(err.message),
  });

  return (
    <div className="min-h-screen bg-stone-50 text-stone-900">
      <header className="border-b border-stone-200 bg-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-6 py-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-700">
              PMS Decision Platform
            </p>
            <h1 className="text-lg font-semibold">Historical Decision Lab</h1>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <nav className="flex flex-wrap items-center gap-1">
              {showChrome ? (
              <Link
                href={dashboardLink.href}
                className={`rounded-lg px-2.5 py-1.5 text-sm font-medium transition hover:bg-stone-100 hover:text-stone-900 ${
                  pathMatches(pathname, dashboardLink.href)
                    ? "bg-stone-100 text-stone-900"
                    : "text-stone-600"
                }`}
              >
                {dashboardLink.label}
              </Link>
              ) : null}
              {visibleGroups.map((group) => (
                <NavDropdown
                  key={group.label}
                  group={group}
                  open={openGroup === group.label}
                  onToggle={() =>
                    setOpenGroup((current) => (current === group.label ? null : group.label))
                  }
                  onClose={() => setOpenGroup(null)}
                  unacknowledgedAlerts={unacknowledgedAlerts}
                  pendingApprovals={pendingApprovals}
                />
              ))}
            </nav>
            {showChrome ? (
            <button
              type="button"
              disabled={refreshMutation.isPending}
              onClick={() => {
                setMessage(null);
                refreshMutation.mutate();
              }}
              title="Sync Research/OneDrive into data/raw and reimport"
              className="rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm font-semibold text-stone-800 hover:bg-stone-50 disabled:cursor-not-allowed disabled:text-stone-400"
            >
              {refreshMutation.isPending ? "Refreshing…" : "Refresh data"}
            </button>
            ) : null}
            {user ? (
              <div className="flex items-center gap-2 border-l border-stone-200 pl-2">
                <span className="text-sm text-stone-600">{user.display_name}</span>
                {onLogout ? (
                  <button
                    type="button"
                    onClick={() => onLogout()}
                    className="rounded-lg px-3 py-2 text-sm font-medium text-stone-600 hover:bg-stone-100"
                  >
                    Log out
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>
        {message ? (
          <div className="border-t border-stone-100 bg-stone-50 px-6 py-2 text-xs text-stone-600">
            {message} · details on the Data page
          </div>
        ) : null}
      </header>
      <main className="mx-auto max-w-7xl px-6 py-8">{children}</main>
    </div>
  );
}
