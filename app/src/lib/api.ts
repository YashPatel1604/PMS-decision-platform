const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(text || response.statusText, response.status);
  }
  return response.json() as Promise<T>;
}

export type DashboardSummary = {
  total_episodes: number;
  ownership_ok: number;
  ownership_insufficient: number;
  post_exit_ok: number;
  post_exit_insufficient: number;
  assessment_counts: Record<string, number>;
};

export type EpisodePerformance = {
  episode_id: number;
  security_id: string;
  portfolio_name: string;
  entry_date: string;
  exit_date: string;
  holding_days: number;
  total_invested: number;
  total_profit_loss: number;
  total_return_pct: number | null;
  stock_xirr: number | null;
  portfolio_return_pct: number | null;
  smallcap_return_pct: number | null;
  excess_vs_smallcap: number | null;
  excess_vs_portfolio: number | null;
  max_drawdown: number | null;
  days_below_cost: number | null;
  days_underperforming_benchmark: number | null;
  exit_assessment: string | null;
  assessment_reason: string | null;
  data_quality_status: string;
};

export type PostExitPerformance = {
  episode_id: number;
  exit_date: string;
  comparison_date: string | null;
  security_return_after_exit: number | null;
  portfolio_return_after_exit: number | null;
  smallcap_return_after_exit: number | null;
  excess_vs_smallcap_after_exit: number | null;
  exit_assessment: string | null;
  assessment_reason: string | null;
  data_quality_status: string;
};

export type AnalysisRunResult = {
  ownership_ok: number;
  ownership_insufficient: number;
  post_exit_ok: number;
  post_exit_insufficient: number;
  cash_flow_rows: number;
};

export const api = {
  getSummary: () => request<DashboardSummary>("/dashboard/summary"),
  listEpisodes: () => request<EpisodePerformance[]>("/episodes/performance"),
  getEpisode: (id: number) => request<EpisodePerformance>(`/episodes/performance/${id}`),
  getPostExit: (id: number) => request<PostExitPerformance>(`/episodes/post-exit/${id}`),
  runAnalysis: () =>
    request<AnalysisRunResult>("/episodes/analyze", { method: "POST" }),
};
