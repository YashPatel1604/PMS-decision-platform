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
  average_winner_pp: number | null;
  average_loser_pp: number | null;
  payoff_ratio: number | null;
  profit_factor: number | null;
  positive_effect_sum_pp: number;
  negative_effect_sum_pp: number;
  historical_capital_weighted_uplift_pct: number | null;
  stock_return_pct: number | null;
  diversified_return_pct: number | null;
  return_uplift_pct: number | null;
  positive_episodes: number;
  negative_episodes: number;
  tie_episodes: number;
  positive_episode_rate_pct: number | null;
  tie_episode_rate_pct: number | null;
  top_episode_contribution_pct: number | null;
  top_three_contribution_pct: number | null;
  contribution_hhi: number | null;
  conclusion: string;
  conclusion_text: string;
  loo_min_mean_return_advantage_pp: number | null;
  loo_max_mean_return_advantage_pp: number | null;
  loo_positive_fraction_pct: number | null;
  episodes: ContinuousLossStrategyEpisode[];
};

export type HoldingBenchmark = {
  code: string;
  total_return_pct: number | null;
  excess_vs_stock_pp: number | null;
  start_level: number | null;
  end_level: number | null;
  data_status: string;
};

export type OpenHolding = {
  episode_id: number;
  security_id: string;
  portfolio_name: string;
  entry_date: string;
  as_of_date: string;
  period_start_date: string;
  quantity: number;
  average_buy_price: number | null;
  first_buy_price: number | null;
  from_price: number | null;
  from_price_date: string | null;
  as_of_price: number | null;
  as_of_price_date: string | null;
  market_value: number | null;
  cost_basis_value: number | null;
  unrealized_pnl: number | null;
  unrealized_pnl_pct: number | null;
  stock_return_pct: number | null;
  portfolio_return_pct: number | null;
  excess_vs_portfolio_pp: number | null;
  bse_return_pct: number | null;
  excess_vs_bse_pp: number | null;
  holding_days: number;
  period_days: number;
  position_weight_pct: number | null;
  underwater: boolean;
  days_below_first_buy: number | null;
  sector: string | null;
  industry: string | null;
  benchmarks: HoldingBenchmark[];
  data_quality_status: string;
  notes: string[];
};

export type LiveQuoteRefresh = {
  requested: number;
  fetched: number;
  upserted: number;
  missing_symbol: number;
  failed: number;
  as_of_date: string;
  notes: string[];
  source: string;
  prefer_bse: boolean;
  tickers?: string[];
};

export type OpenHoldings = {
  as_of_date: string;
  from_date: string | null;
  open_count: number;
  equity_market_value: number | null;
  equity_market_value_from: number | null;
  reconstructed_equity_market_value?: number | null;
  reconstructed_equity_market_value_from?: number | null;
  portfolio_value_source?: string | null;
  portfolio_value_from_source?: string | null;
  portfolio_value_observation_date?: string | null;
  portfolio_value_from_observation_date?: string | null;
  portfolio_value_check_delta?: number | null;
  portfolio_value_from_check_delta?: number | null;
  portfolio_return_pct: number | null;
  mean_excess_vs_primary_pp: number | null;
  mean_excess_vs_portfolio_pp: number | null;
  primary_benchmark_code: string;
  benchmark_codes: string[];
  holdings: OpenHolding[];
  live_refresh: LiveQuoteRefresh | null;
};

export type IndustryCompare = {
  security_id: string;
  industry: string | null;
  peer_count: number;
  used_count: number;
  total_return_pct: number | null;
  peers: {
    security_id: string;
    portfolio_name: string;
    total_return_pct: number | null;
    data_status: string;
  }[];
  notes: string[];
};

export type YahooSearchHit = {
  symbol: string;
  name: string;
  exchange: string;
  yahoo_ticker: string;
};

export type BlockDeal = {
  deal_date: string | null;
  bse_code: string;
  scrip_name: string;
  client_name: string;
  deal_type: string;
  quantity: number;
  price: number;
  value: number;
  is_arbitrage: boolean;
  portfolio_name: string | null;
  in_portfolio: boolean;
  is_open: boolean;
  market_cap_cr: number | null;
};

export type TodayBlockDeals = {
  as_of_date: string;
  fetched_at: string;
  deal_count: number;
  arbitrage_deal_count: number;
  non_arbitrage_deal_count: number;
  available_dates: string[];
  deals: BlockDeal[];
};

export type BulkDeal = BlockDeal;
export type TodayBulkDeals = TodayBlockDeals;

export type CorporateDisclosure = {
  kind: "sast" | "insider" | string;
  disclosure_date: string | null;
  bse_code: string;
  company_name: string;
  person_name: string;
  category: string;
  transaction_type: string;
  quantity: number | null;
  value: number | null;
  pct_pre: number | null;
  pct_post: number | null;
  mode: string;
  regulation: string;
  isin: string | null;
  market_cap_cr: number | null;
  portfolio_name: string | null;
  in_portfolio: boolean;
  is_open: boolean;
};

export type TodayCorporateDisclosures = {
  kind: string;
  as_of_date: string;
  fetched_at: string;
  row_count: number;
  available_dates: string[];
  rows: CorporateDisclosure[];
};

export type PeerCompare = {
  ticker: string;
  start_date: string;
  end_date: string;
  start_price: number;
  end_price: number;
  total_return_pct: number;
};

export type CompareSeries = {
  episode_id: number;
  security_id: string;
  start_date: string;
  end_date: string;
  points: {
    trade_date: string;
    stock: number | null;
    bse_smallcap: number | null;
    portfolio: number | null;
    industry_ew: number | null;
    peer: number | null;
    peers?: Record<string, number | null>;
  }[];
  industry_return_pct: number | null;
  peer_return_pct: number | null;
  peer_ticker: string | null;
  peer_series?: { ticker: string; total_return_pct: number | null }[];
  notes: string[];
};

export type UploadIssue = {
  severity: string;
  code: string;
  message: string;
  security_id: string | null;
  source_key: string | null;
  event_date: string | null;
};

export type UploadBatch = {
  batch_id: number;
  kind: string;
  status: string;
  source_file: string;
  source_checksum: string;
  issues: UploadIssue[];
  error_count: number;
  warning_count: number;
  review_count: number;
  row_counts: Record<string, number>;
  episode_summary: Record<string, number> | null;
  can_commit: boolean;
  notes: string | null;
};

export type UploadKind = "transactions" | "security_master" | "portfolio_snapshots";

export type MasterKind = "security" | "transactions" | "sell_since";

export type MasterWorkbook = {
  kind: MasterKind;
  label: string;
  path: string;
  exists: boolean;
  default_sheet: string;
  mtime: string | null;
  size_bytes: number | null;
  raw_sync_path: string | null;
};

export type MasterPreview = {
  kind: MasterKind;
  path: string;
  sheet: string;
  sheets: string[];
  columns: string[];
  rows: Record<string, string | number | null>[];
  offset: number;
  limit: number;
  total_rows: number;
  matched_rows: number;
};

export type ProposedMasterEdit = {
  action: string;
  kind: MasterKind;
  line_number: number;
  raw_line: string;
  fields: Record<string, unknown>;
  summary: string;
  warnings: string[];
};

export type MasterParseResult = {
  edits: ProposedMasterEdit[];
  errors: string[];
  can_apply: boolean;
};

export type MasterApplyResult = {
  applied: number;
  backups: string[];
  written_paths: string[];
  synced_raw: string[];
  import_notes: string[];
  errors: string[];
  episode_count: number | null;
};

export type OnedriveRefreshResult = {
  ok: boolean;
  error: string | null;
  sync: {
    copied: string[];
    snapshot_count: number;
    research_dir: string | null;
    notes: string[];
  };
  reimport: {
    securities_inserted: number;
    equity_txns_inserted: number;
    liquid_txns_inserted: number;
    episodes: number;
    decision_events: number;
    snapshots_inserted: number;
    snapshots_unresolved: number;
    validation_errors: number;
    notes: string[];
  } | null;
  market_data: {
    source_dir: string;
    used_seed_fallback: boolean;
    missing_files: string[];
    prices_inserted: number;
    prices_skipped: number;
    prices_unresolved: number;
    prices_invalid: number;
    dividends_inserted: number;
    dividends_skipped: number;
    dividends_unresolved: number;
    dividends_invalid: number;
    benchmarks_inserted: number;
    benchmarks_skipped: number;
    benchmarks_invalid: number;
    successors_inserted: number;
    successors_skipped: number;
    successors_invalid: number;
    notes: string[];
  } | null;
  analysis: {
    ownership_ok: number;
    ownership_insufficient: number;
    post_exit_ok: number;
    post_exit_insufficient: number;
    cash_flow_rows: number;
  } | null;
};

export const api = {
  getSummary: () => request<DashboardSummary>("/dashboard/summary"),
  getExitInsights: () => request<ExitInsightRow[]>("/dashboard/exit-insights"),
  listEpisodes: () => request<EpisodePerformance[]>("/episodes/performance"),
  getEpisode: (id: number) => request<EpisodePerformance>(`/episodes/performance/${id}`),
  getPostExit: (id: number) => request<PostExitPerformance>(`/episodes/post-exit/${id}`),
  getContinuousLossStrategy: () =>
    request<ContinuousLossStrategy>("/backtests/one-year-continuous-loss"),
  getOpenHoldings: (
    asOf?: string | null,
    benchmarks?: string,
    refreshLive = false,
    fromDate?: string | null,
  ) => {
    const params = new URLSearchParams();
    if (asOf) params.set("as_of", asOf);
    if (fromDate) params.set("from_date", fromDate);
    if (benchmarks) params.set("benchmarks", benchmarks);
    params.set("refresh_live", "false");
    void refreshLive;
    const query = params.toString();
    return request<OpenHoldings>(`/holdings/open?${query}`);
  },
  refreshLiveQuotes: (preferBse = true) =>
    request<LiveQuoteRefresh>(
      `/market-data/live-quotes/refresh?prefer_bse=${preferBse ? "true" : "false"}`,
      { method: "POST" },
    ),
  getOpenHolding: (id: number, asOf?: string, fromDate?: string | null) => {
    const params = new URLSearchParams();
    if (asOf) params.set("as_of", asOf);
    if (fromDate) params.set("from_date", fromDate);
    const query = params.toString();
    return request<OpenHolding>(`/holdings/open/${id}${query ? `?${query}` : ""}`);
  },
  getIndustryCompare: (id: number, asOf?: string, fromDate?: string | null) => {
    const params = new URLSearchParams();
    if (asOf) params.set("as_of", asOf);
    if (fromDate) params.set("from_date", fromDate);
    const query = params.toString();
    return request<IndustryCompare>(
      `/holdings/open/${id}/industry-compare${query ? `?${query}` : ""}`,
    );
  },
  getCompareSeries: (
    id: number,
    asOf?: string,
    fromDate?: string | null,
    peerTickers?: string[] | null,
  ) => {
    const params = new URLSearchParams();
    if (asOf) params.set("as_of", asOf);
    if (fromDate) params.set("from_date", fromDate);
    for (const ticker of peerTickers ?? []) {
      if (ticker.trim()) params.append("peer_tickers", ticker.trim());
    }
    const query = params.toString();
    return request<CompareSeries>(
      `/holdings/open/${id}/compare-series${query ? `?${query}` : ""}`,
    );
  },
  searchYahoo: (q: string) =>
    request<YahooSearchHit[]>(`/market-data/yahoo/search?q=${encodeURIComponent(q)}`),
  getTodayBlockDeals: (date?: string | null, month?: string | null) => {
    const params = new URLSearchParams();
    if (date) params.set("date", date);
    if (month) params.set("month", month);
    const query = params.toString();
    return request<TodayBlockDeals>(
      `/market-data/block-deals/today${query ? `?${query}` : ""}`,
    );
  },
  getTodayBulkDeals: (date?: string | null, month?: string | null) => {
    const params = new URLSearchParams();
    if (date) params.set("date", date);
    if (month) params.set("month", month);
    const query = params.toString();
    return request<TodayBulkDeals>(
      `/market-data/bulk-deals/today${query ? `?${query}` : ""}`,
    );
  },
  getTodaySastDisclosures: (date?: string | null, month?: string | null) => {
    const params = new URLSearchParams();
    if (date) params.set("date", date);
    if (month) params.set("month", month);
    const query = params.toString();
    return request<TodayCorporateDisclosures>(
      `/market-data/sast/today${query ? `?${query}` : ""}`,
    );
  },
  getTodayInsiderTrading: (date?: string | null, month?: string | null) => {
    const params = new URLSearchParams();
    if (date) params.set("date", date);
    if (month) params.set("month", month);
    const query = params.toString();
    return request<TodayCorporateDisclosures>(
      `/market-data/insider-trading/today${query ? `?${query}` : ""}`,
    );
  },
  comparePeer: (ticker: string, asOf?: string, fromDate?: string | null) => {
    const params = new URLSearchParams();
    params.set("ticker", ticker);
    if (asOf) params.set("as_of", asOf);
    if (fromDate) params.set("from_date", fromDate);
    return request<PeerCompare>(`/holdings/compare/peer?${params.toString()}`);
  },
  uploadExcel: async (kind: UploadKind, file: File) => {
    const body = new FormData();
    body.append("kind", kind);
    body.append("file", file);
    const response = await fetch(`${API_BASE}/imports/upload`, {
      method: "POST",
      body,
      cache: "no-store",
    });
    if (!response.ok) {
      const text = await response.text();
      throw new ApiError(text || response.statusText, response.status);
    }
    return response.json() as Promise<UploadBatch>;
  },
  validateUpload: (batchId: number) =>
    request<UploadBatch>(`/imports/${batchId}/validate`, { method: "POST" }),
  commitUpload: (batchId: number) =>
    request<UploadBatch>(`/imports/${batchId}/commit`, { method: "POST" }),
  refreshFromOnedrive: () =>
    request<OnedriveRefreshResult>("/imports/refresh-from-onedrive", { method: "POST" }),
  getUploadBatch: (batchId: number) => request<UploadBatch>(`/imports/${batchId}`),
  listMasters: () => request<MasterWorkbook[]>("/masters"),
  getMasterPreview: (
    kind: MasterKind,
    opts?: { sheet?: string; offset?: number; limit?: number; q?: string },
  ) => {
    const params = new URLSearchParams();
    if (opts?.sheet) params.set("sheet", opts.sheet);
    if (opts?.offset != null) params.set("offset", String(opts.offset));
    if (opts?.limit != null) params.set("limit", String(opts.limit));
    if (opts?.q) params.set("q", opts.q);
    const query = params.toString();
    return request<MasterPreview>(`/masters/${kind}/preview${query ? `?${query}` : ""}`);
  },
  masterDownloadUrl: (kind: MasterKind) =>
    `${API_BASE}/masters/${kind}/download`,
  parseMasterPrompt: (prompt: string, kind?: MasterKind | null) =>
    request<MasterParseResult>("/masters/parse", {
      method: "POST",
      body: JSON.stringify({ prompt, kind: kind ?? null }),
    }),
  applyMasterEdits: (edits: ProposedMasterEdit[], reimport = true) =>
    request<MasterApplyResult>("/masters/apply", {
      method: "POST",
      body: JSON.stringify({ edits, reimport }),
    }),
  runAnalysis: () =>
    request<AnalysisRunResult>("/episodes/analyze", { method: "POST" }),
};
