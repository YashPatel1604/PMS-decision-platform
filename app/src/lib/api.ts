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
  flag_counts: Record<string, number>;
};

export type ExitInsightRow = {
  episode_id: number;
  security_id: string;
  portfolio_name: string;
  exit_date: string;
  comparison_date: string | null;
  holding_years: number;
  exit_price: number | null;
  peak_price: number | null;
  peak_price_date: string | null;
  ideal_exit_note: string | null;
  missed_upside_vs_peak_pct: number | null;
  total_return_pct: number | null;
  exit_outcome: string;
  first_below_cost_date: string | null;
  days_held_after_first_loss: number | null;
  calendar_days_held_after_first_loss: number | null;
  loss_hold_pattern: string | null;
  security_return_after_exit: number | null;
  portfolio_return_after_exit: number | null;
  smallcap_return_after_exit: number | null;
  excess_vs_portfolio_after_exit: number | null;
  excess_vs_smallcap_after_exit: number | null;
  current_price: number | null;
  current_price_date: string | null;
  current_vs_exit_pct: number | null;
  exit_assessment: string;
  assessment_flags: string[];
  ownership_signals: string[];
  post_exit_signals: string[];
  assessment_confidence: string | null;
  post_exit_horizons: PostExitHorizon[];
  portfolio_comparator_status: "PROVISIONAL";
  assessment_reason: string;
  post_exit_summary: string | null;
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
  exit_outcome: string;
  average_buy_price: number | null;
  average_sell_price: number | null;
  total_return_pct: number | null;
  stock_xirr: number | null;
  portfolio_return_pct: number | null;
  smallcap_return_pct: number | null;
  excess_vs_smallcap: number | null;
  excess_vs_portfolio: number | null;
  max_drawdown: number | null;
  peak_price_during_hold: number | null;
  peak_price_date: string | null;
  exit_adjusted_close: number | null;
  missed_upside_vs_peak_pct: number | null;
  days_below_cost: number | null;
  days_underperforming_benchmark: number | null;
  first_below_cost_date: string | null;
  days_held_after_first_loss: number | null;
  calendar_days_held_after_first_loss: number | null;
  loss_hold_pattern: string | null;
  comparison_date: string | null;
  security_return_after_exit: number | null;
  portfolio_return_after_exit: number | null;
  smallcap_return_after_exit: number | null;
  excess_vs_smallcap_after_exit: number | null;
  excess_vs_portfolio_after_exit: number | null;
  major_loss_window: MajorLossWindow | null;
  exit_assessment: string | null;
  ownership_signals: string[];
  post_exit_signals: string[];
  assessment_confidence: string | null;
  assessment_evidence: Record<string, string | number | null>;
  post_exit_horizons: PostExitHorizon[];
  portfolio_comparator_status: "PROVISIONAL";
  assessment_reason: string | null;
  data_quality_status: string;
};

export type PostExitHorizon = {
  horizon: string;
  target_date: string | null;
  comparison_date: string | null;
  days_after_exit?: number | null;
  security_return_pct: number | null;
  smallcap_return_pct: number | null;
  excess_vs_smallcap_pct: number | null;
  provisional_portfolio_return_pct: number | null;
  provisional_excess_vs_portfolio_pct?: number | null;
  data_quality_status: string;
};

export type MajorLossWindow = {
  start_date: string;
  end_date: string;
  calendar_days: number;
  trading_days: number | null;
  pattern: string;
  start_price: number | null;
  end_price: number | null;
  stock_return_pct: number | null;
  portfolio_return_pct: number | null;
  smallcap_return_pct: number | null;
  stock_vs_portfolio_pct: number | null;
  stock_vs_smallcap_pct: number | null;
  portfolio_vs_smallcap_pct: number | null;
  portfolio_methodology: string | null;
  reinvestment_after_loss: EqualWeightReinvestment | null;
  reinvestment_at_one_year_loss: EqualWeightReinvestment | null;
};

export type EqualWeightReinvestment = {
  start_date: string;
  end_date: string;
  stock_return_pct: number | null;
  equal_weight_other_holdings_return_pct: number | null;
  reinvestment_advantage_pct: number | null;
  value_if_stock_100: number | null;
  value_if_reinvested_100: number | null;
  included_holdings: number;
  excluded_missing_prices: number;
  methodology: string;
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

export type ContinuousLossStrategyEpisode = {
  episode_id: number;
  security_id: string;
  portfolio_name: string;
  entry_date: string;
  exit_date: string;
  status: string;
  initial_purchase_price: number | null;
  adjusted_initial_price_threshold: number | null;
  underwater_start_date: string | null;
  trigger_date: string | null;
  measurement_days: number | null;
  trigger_quantity: number | null;
  trigger_price: number | null;
  trigger_proceeds: number | null;
  common_end_date: string | null;
  stock_return_pct: number | null;
  diversified_return_pct: number | null;
  return_uplift_pct: number | null;
  stock_cagr_pct: number | null;
  diversified_cagr_pct: number | null;
  annualized_advantage_pp: number | null;
  stock_end_value: number | null;
  diversified_end_value: number | null;
  impact_rupees: number | null;
  impact_pct_of_trigger: number | null;
  trigger_portfolio_value: number | null;
  trigger_equity_value: number | null;
  trigger_liquid_value: number | null;
  portfolio_denominator_status: string | null;
  position_weight_pct: number | null;
  hold_portfolio_contribution_pct: number | null;
  diversified_portfolio_contribution_pct: number | null;
  portfolio_impact_pp: number | null;
  other_holdings_count: number;
  priced_holdings_count: number;
  missing_price_holdings_count: number;
  absolute_contribution_share_pct: number | null;
  leave_one_out_impact_rupees: number | null;
  leave_one_out_impact_pct: number | null;
  leave_one_out_stock_xirr: number | null;
  leave_one_out_diversified_xirr: number | null;
  leave_one_out_annualized_advantage_pp: number | null;
  leave_one_out_mean_portfolio_impact_pp: number | null;
  leave_one_out_median_portfolio_impact_pp: number | null;
  leave_one_out_mean_return_advantage_pp: number | null;
  leave_one_out_median_return_advantage_pp: number | null;
  removal_flips_result: boolean;
  note: string | null;
};

export type ContinuousLossStrategy = {
  methodology: string;
  closed_episodes: number;
  triggered_episodes: number;
  no_trigger_episodes: number;
  excluded_episodes: number;
  trigger_rate_pct: number;
  total_trigger_proceeds: number;
  common_end_date: string | null;
  stock_end_value: number;
  diversified_end_value: number;
  net_impact_rupees: number;
  stock_xirr: number | null;
  diversified_xirr: number | null;
  annualized_advantage_pp: number | null;
  terminal_value_uplift_pct: number | null;
  mean_portfolio_impact_pp: number | null;
  median_portfolio_impact_pp: number | null;
  largest_portfolio_impact_pp: number | null;
  equal_capital_start_value: number;
  hold_equal_capital_end_value: number;
  diversified_equal_capital_end_value: number;
  equal_capital_net_difference: number;
  mean_return_advantage_pp: number | null;
  median_return_advantage_pp: number | null;
  positive_effect_sum_pp: number;
  negative_effect_sum_pp: number;
  stock_return_pct: number | null;
  diversified_return_pct: number | null;
  return_uplift_pct: number | null;
  positive_episodes: number;
  negative_episodes: number;
  positive_episode_rate_pct: number | null;
  top_episode_contribution_pct: number | null;
  top_three_contribution_pct: number | null;
  contribution_hhi: number | null;
  conclusion: string;
  conclusion_text: string;
  episodes: ContinuousLossStrategyEpisode[];
};

export const api = {
  getSummary: () => request<DashboardSummary>("/dashboard/summary"),
  getExitInsights: () => request<ExitInsightRow[]>("/dashboard/exit-insights"),
  listEpisodes: () => request<EpisodePerformance[]>("/episodes/performance"),
  getEpisode: (id: number) => request<EpisodePerformance>(`/episodes/performance/${id}`),
  getPostExit: (id: number) => request<PostExitPerformance>(`/episodes/post-exit/${id}`),
  getContinuousLossStrategy: () =>
    request<ContinuousLossStrategy>("/backtests/one-year-continuous-loss"),
  runAnalysis: () =>
    request<AnalysisRunResult>("/episodes/analyze", { method: "POST" }),
};
