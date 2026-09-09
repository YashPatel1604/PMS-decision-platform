# PMS Decision Intelligence Platform

A private, local-first decision-support system for analyzing a 2012–2026 Indian PMS model portfolio, reconstructing historical investment decisions, identifying avoidable mistakes, and improving future sell discipline, portfolio construction, and research efficiency.

---

## 1. Project purpose

This project is not a trading bot and must never place orders.

Its purpose is to help a portfolio manager:

- Reconstruct the complete historical model portfolio
- Analyze every investment episode from entry to exit
- Identify delayed exits, premature exits, sizing mistakes, and opportunity-cost mistakes
- Distinguish temporary underperformance from genuine thesis deterioration
- Generate deterministic and explainable Hold / Review / Reduce / Exit Candidate recommendations
- Improve future portfolio construction
- Search internal research and public company documents
- Preserve a complete audit trail of every recommendation and human decision

The primary business objective is:

> Improve absolute long-term portfolio returns by identifying deteriorating investments earlier without systematically selling future winners too soon.

---

## 2. Scope

### In scope

- One Indian PMS model portfolio
- Historical data from 2012 through 2026
- Indian listed equities
- Small-cap and mid-cap fundamental investing
- Long-only strategy
- Approximately 12–20 holdings at a time
- Typical holding period of 4–5 years
- Low portfolio churn
- Maximum 10% position size at initial purchase
- Maximum 20% exposure to one sector
- No leverage
- No derivatives
- Minimum market capitalization of approximately ₹4,000 crore at the decision date
- Internal use by two users
- Decision support only

### Out of scope for the first version

- Trade execution
- Broker order placement
- Client-level account calculations
- Multi-tenant architecture
- Public or client-facing reports
- Black-box buy/sell predictions
- Fully autonomous investment decisions
- High-frequency or intraday strategies
- Derivatives analytics
- International securities
- Replacing the firm’s official PMS accounting system

---

## 3. Product principles

### 3.1 Deterministic financial calculations

All portfolio quantities, returns, weights, cash flows, costs, signals, and recommendations must be calculated in conventional code.

LLMs may summarize and retrieve evidence, but they must not:

- Invent missing values
- Modify financial statements
- Calculate official portfolio returns
- Decide position weights without a deterministic optimizer
- Override hard constraints
- Produce unexplained recommendations

### 3.2 Explainability

Every recommendation must include:

- Recommendation timestamp
- Security
- Action: Hold, Review, Reduce, Exit Candidate, or Insufficient Data
- Rules triggered
- Evidence used
- Source publication dates
- Data quality status
- Counter-evidence
- Confidence level
- Rule version
- Human decision
- Reason for accepting or rejecting the recommendation

### 3.3 Point-in-time historical analysis

Historical simulations may only use information publicly available on the simulated decision date.

For every financial or qualitative data point, retain:

- Financial period end
- Publication date
- Source
- Retrieval date
- Restatement status

Postmortems may use hindsight, but hindsight analysis must remain clearly separated from point-in-time simulations.

### 3.4 No silent corrections

The system must never silently fix or overwrite source data.

Every correction must be:

- Explicit
- Traceable
- Reproducible
- Versioned
- Auditable

---

## 4. Current data assets

The project begins with the following finalized inputs.

### 4.1 Transaction master

Expected filename:

```text
MASTER_TRANSACTIONS_V1.xlsx
```

Contains:

- Complete transaction history from 2012–2026
- Buy and sell events
- Bonuses
- Splits
- Rights
- Demergers
- Quantity totals for each security
- Source workbook and worksheet references
- Review items where trade prices are unavailable

Required transaction fields:

| Field | Required | Description |
|---|---:|---|
| Security / portfolio name | Yes | Historical name used in source workbook |
| Date | Yes | Transaction or corporate-action date |
| Event type | Yes | Buy, Sell, Bonus, Split, Rights, Demerger, Merger, Conversion |
| Quantity | Yes | Positive for additions, negative for reductions |
| Price | No | May be unavailable for some historical liquid/corporate-action rows |
| Amount | No | Formula or source amount |
| Source notes | Yes | Source workbook, sheet, and note |
| Profit/loss label | No | Historical manual classification |
| Outperformed portfolio | No | Historical manual classification |

### 4.2 Security master

Expected filename:

```text
SECURITY_MASTER_V1.xlsx
```

Contains 75 investable securities and excludes LiquidCase as an equity security.

Required fields:

| Field | Description |
|---|---|
| Security ID | Permanent internal identifier |
| Portfolio name | Name used in transaction workbook |
| Canonical company name | Standard company name |
| Current NSE symbol | Current listed symbol |
| Historical NSE symbol | Earlier symbol where relevant |
| BSE code | Official BSE scrip code |
| ISIN | Official ISIN |
| Status | Active, merged, delisted, inactive, or review |
| Corporate/name history | Rename, merger, demerger, or delisting notes |
| Sector | Portfolio sector classification |
| Industry | Portfolio industry classification |
| Verification status | Identifier validation status |

### 4.3 Historical portfolio snapshots

Annual workbooks:

```text
Portfolio_2012.xlsx
Portfolio_2013.xlsx
...
Portfolio_2026.xlsx
```

These files are historical source records and should not be edited by application code.

### 4.4 Liquid holdings

LiquidCase or equivalent liquid balances are:

- Not equity securities
- Not investment episodes
- Not included in company-level winner/loser analysis
- Included in total portfolio value
- Included in cash allocation analysis
- Included in opportunity-cost and deployment analysis

### 4.5 Manual Sell Since workbook

A manually maintained “Sell Since” workbook currently records historical exit outcomes, profit/loss labels, and post-exit comparisons.

The software must replace that workbook with a reproducible, versioned, and test-covered analysis generated from transactions, episodes, adjusted prices, dividends, and benchmark TRI series. Manual Sell Since classifications may be retained as historical reference labels, but they must not be the system’s source of truth for episode performance.

---

## 5. Repository structure

Create the repository with the following structure:

```text
pms-decision-platform/
├── README.md
├── AGENTS.md
├── .gitignore
├── .env.example
├── pyproject.toml
├── docker-compose.yml
├── Makefile
│
├── data/
│   ├── raw/
│   │   ├── transactions/
│   │   ├── security_master/
│   │   ├── portfolio_snapshots/
│   │   └── research/
│   ├── processed/
│   ├── external/
│   │   ├── prices/
│   │   ├── benchmarks/
│   │   ├── fundamentals/
│   │   └── filings/
│   └── exports/
│
├── src/
│   └── pms_platform/
│       ├── __init__.py
│       ├── config.py
│       │
│       ├── ingestion/
│       │   ├── transactions.py
│       │   ├── securities.py
│       │   ├── snapshots.py
│       │   └── validators.py
│       │
│       ├── models/
│       │   ├── security.py
│       │   ├── transaction.py
│       │   ├── corporate_action.py
│       │   ├── snapshot.py
│       │   ├── episode.py
│       │   ├── decision_event.py
│       │   └── recommendation.py
│       │
│       ├── portfolio/
│       │   ├── position_engine.py
│       │   ├── cash_engine.py
│       │   ├── reconciliation.py
│       │   └── valuation.py
│       │
│       ├── episodes/
│       │   ├── builder.py
│       │   └── decision_events.py
│       │
│       ├── market_data/
│       │   ├── prices.py
│       │   ├── benchmarks.py
│       │   └── corporate_actions.py
│       │
│       ├── analytics/
│       │   ├── performance.py
│       │   ├── drawdowns.py
│       │   ├── attribution.py
│       │   ├── post_exit.py
│       │   └── opportunity_cost.py
│       │
│       ├── signals/
│       │   ├── underperformance.py
│       │   ├── fundamentals.py
│       │   ├── governance.py
│       │   ├── cycle.py
│       │   └── recommendations.py
│       │
│       ├── documents/
│       │   ├── ingestion.py
│       │   ├── extraction.py
│       │   └── search.py
│       │
│       ├── api/
│       │   ├── main.py
│       │   └── routes/
│       │
│       └── cli.py
│
├── app/
│   ├── package.json
│   ├── next.config.js
│   └── src/
│
├── database/
│   ├── migrations/
│   └── seeds/
│
├── notebooks/
│   ├── 01_data_audit.ipynb
│   ├── 02_episode_analysis.ipynb
│   └── 03_sell_rule_research.ipynb
│
├── scripts/
│   ├── ingest_all.py
│   ├── reconcile.py
│   ├── build_episodes.py
│   └── export_reports.py
│
└── tests/
    ├── fixtures/
    ├── test_ingestion.py
    ├── test_reconciliation.py
    ├── test_positions.py
    ├── test_episodes.py
    └── test_corporate_actions.py
```

---

## 6. Recommended technology stack

### Backend

- Python 3.12
- FastAPI
- PostgreSQL
- SQLAlchemy 2.x
- Alembic
- Pydantic
- Polars
- pandas only where library compatibility requires it
- NumPy
- SciPy
- CVXPY
- Pytest
- Ruff
- MyPy
- pre-commit

### Frontend

- Next.js
- TypeScript
- React
- Tailwind CSS
- Apache ECharts or Plotly
- TanStack Query

### Infrastructure

- Docker
- Docker Compose
- Local-first deployment
- GitHub private repository
- OneDrive for raw files, reports, and backups
- Sibling OneDrive `Research/` folder is the authoritative read-only knowledge base (portfolio snapshots, research workbooks); open `PMS-Decision-Platform.code-workspace` to index it in Cursor
- PostgreSQL database stored outside OneDrive
- Optional Tailscale for private remote access

### Document intelligence

- PyMuPDF
- PostgreSQL full-text search
- pgvector only where semantic retrieval materially improves search
- Local embeddings or approved private API
- Page-level citations for every research answer

---

## 7a. Research knowledge base (OneDrive)

Portfolio truth lives in the sibling folder:

`/Users/yash/Library/CloudStorage/OneDrive-Personal/Research`

Especially `Research/Portfolio/` (yearly `Portfolio_*.xlsx`, transactions, sell-since, benchmarks).

Rules:

1. Treat Research as **read-only**. Never edit it from the app or agents unless explicitly asked.
2. Prefer Research over `02_Final_Master/` and `data/raw/` when the same workbook exists (newest mtime wins for versioned masters).
3. Open [`PMS-Decision-Platform.code-workspace`](../PMS-Decision-Platform.code-workspace) so Cursor indexes both the app and Research.
4. Keep needed Research trees **Always keep on this device** in OneDrive so imports and agents do not hit cloud-only placeholders.
5. Set `RESEARCH_DIR` in `.env` only if the auto-detected path is wrong. `scripts/sync_raw_from_onedrive.sh` copies from Research into `data/raw` (still never writes back).

---

## 7. Local development prerequisites

Install:

1. Git
2. Python 3.12
3. uv
4. Docker Desktop
5. Node.js 22 LTS
6. pnpm
7. VS Code or another editor
8. Claude Code and/or Codex CLI
9. GitHub CLI, optional
10. PostgreSQL client tools, optional

Verify:

```bash
git --version
python3 --version
uv --version
docker --version
node --version
pnpm --version
```

---

## 8. Repository setup

### 8.1 Create the repository

```bash
mkdir pms-decision-platform
cd pms-decision-platform
git init
```

### 8.2 Create a Python project

```bash
uv init --package
uv python pin 3.12
```

### 8.3 Install initial backend dependencies

```bash
uv add fastapi uvicorn sqlalchemy alembic psycopg[binary] pydantic-settings polars openpyxl numpy scipy cvxpy
uv add --dev pytest pytest-cov ruff mypy pre-commit
```

### 8.4 Create the frontend

```bash
pnpm create next-app app
```

Recommended answers:

```text
TypeScript: Yes
ESLint: Yes
Tailwind CSS: Yes
src directory: Yes
App Router: Yes
Turbopack: Yes
Import alias: @/*
```

### 8.5 Initialize pre-commit

```bash
uv run pre-commit install
```

### 8.6 Create the first commit

```bash
git add .
git commit -m "Initialize PMS decision intelligence platform"
```

---

## 9. Environment configuration

Create `.env.example`:

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg://pms:pms@localhost:5432/pms
RAW_DATA_DIR=./data/raw
PROCESSED_DATA_DIR=./data/processed
EXTERNAL_DATA_DIR=./data/external
EXPORT_DIR=./data/exports
LOG_LEVEL=INFO
```

Never commit `.env`.

---

## 10. Docker Compose

The first `docker-compose.yml` should include:

- PostgreSQL
- Optional pgAdmin
- Backend API
- Frontend only after the backend foundation is stable

Minimum PostgreSQL service:

```yaml
services:
  postgres:
    image: postgres:17
    environment:
      POSTGRES_DB: pms
      POSTGRES_USER: pms
      POSTGRES_PASSWORD: pms
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

Start it:

```bash
docker compose up -d postgres
```

---

## 11. Core database tables

### 11.1 securities

```text
security_id
portfolio_name
canonical_name
current_nse_symbol
historical_nse_symbol
bse_code
isin
status
sector
industry
corporate_history
verification_status
```

### 11.2 transactions

```text
transaction_id
security_id
event_date
event_type
quantity
price
amount
source_file
source_sheet
source_row
source_note
import_batch_id
```

### 11.3 liquid_transactions

Separate from equity transactions:

```text
liquid_transaction_id
event_date
quantity
price
amount
source_file
source_sheet
source_note
```

### 11.4 corporate_actions

```text
corporate_action_id
security_id
action_type
effective_date
record_date
ratio_numerator
ratio_denominator
quantity_adjustment
source
```

### 11.5 portfolio_snapshots

```text
snapshot_id
snapshot_date
security_id
quantity
price
market_value
portfolio_weight
source_file
source_sheet
```

### 11.6 investment_episodes

```text
episode_id
security_id
episode_number
entry_date
exit_date
status
initial_quantity
total_buy_quantity
total_sell_quantity
corporate_action_quantity
max_quantity
final_quantity
number_of_buys
number_of_sells
```

### 11.7 decision_events

```text
decision_event_id
episode_id
security_id
event_date
decision_type
quantity_change
position_before
position_after
price
source_transaction_id
```

Decision types:

```text
INITIATE
ADD
REDUCE
EXIT
CORPORATE_ACTION
```

### 11.8 Episode performance and sell-analysis tables

Recommended datasets or tables for Historical Sell and Episode Analytics:

```text
episode_cash_flows
episode_performance
portfolio_period_performance
benchmark_period_performance
post_exit_performance
sell_assessments
```

Example fields for `episode_performance`:

```text
episode_id
security_id
entry_date
exit_date
holding_days
total_invested
total_sale_proceeds
dividends_received
total_profit_loss
total_return_pct
stock_xirr
portfolio_return_pct
portfolio_annualized_return
smallcap_return_pct
smallcap_annualized_return
excess_vs_portfolio
excess_vs_smallcap
max_drawdown
max_unrealized_gain
days_below_cost
days_underperforming_benchmark
calculation_version
data_quality_status
```

Example fields for `post_exit_performance`:

```text
episode_id
exit_date
comparison_date
security_return_after_exit
portfolio_return_after_exit
smallcap_return_after_exit
excess_vs_portfolio_after_exit
excess_vs_smallcap_after_exit
maximum_gain_after_exit
maximum_loss_after_exit
exit_assessment
assessment_reason
data_quality_status
```

---

## 12. Data contracts

### 12.1 Quantity sign rules

```text
Buy       positive
Sell      negative
Bonus     positive adjustment
Split     positive adjustment equal to new quantity minus old quantity
Rights    positive
Demerger  positive for the received security
```

### 12.2 Episode rules

An episode begins when:

```text
running quantity changes from 0 to greater than 0
```

An episode ends when:

```text
running quantity changes from greater than 0 to 0
```

A later purchase starts a new episode.

Corporate actions:

- Remain within the existing episode
- Do not count as investment decisions
- Do not increase the number of buys

### 12.3 Error conditions

The importer must reject or flag:

- Unknown security
- Duplicate transaction
- Invalid date
- Missing quantity
- Invalid event type
- Sell causing negative running holdings
- Corporate action outside an active episode
- Final quantity inconsistent with master total
- Snapshot quantity mismatch
- Security identifier collision
- Duplicate ISIN
- Duplicate BSE code assigned to different active securities

---

## 13. First development milestone

### Milestone 1: deterministic ingestion and episode generation

The software must:

1. Import the Security Master
2. Import the Transaction Master
3. Separate LiquidCase from equity securities
4. Store securities and transactions in PostgreSQL
5. Validate all transaction rows
6. Calculate running holdings
7. Build investment episodes
8. Build decision events
9. Export results to Excel or CSV
10. Produce identical results on every run

### Acceptance criteria

- All 75 securities load successfully
- Every transaction maps to one Security ID
- No equity transaction maps to LiquidCase
- No unexplained negative quantity exists
- Every closed episode ends at zero
- Every open episode ends at the master total
- Corporate actions do not count as buys
- Re-running ingestion produces no duplicate records
- All tests pass
- Every imported row retains source lineage

---

## 14. Second development milestone

### Milestone 2: portfolio reconstruction

The software must reconstruct holdings on any date:

```python
portfolio_on(date="2019-06-30")
```

Output:

```text
security_id
quantity
cost_basis
market_price
market_value
portfolio_weight
```

Before external price data is connected, the engine should at least reproduce quantities.

### Acceptance criteria

- Quantity reconstruction matches historical snapshots
- Split, bonus, rights, and demerger events are handled correctly
- Liquid holdings are shown separately
- No future transaction affects an earlier date
- Snapshot mismatches generate an exception report

---

## 15. Historical Sell and Episode Analytics

This section defines the software requirement for historical investment episode performance, sell analysis, and benchmark comparison.

It sits after investment-episode generation and portfolio reconstruction, and before frontend or decision-support application development.

The system must replace the manually maintained “Sell Since” workbook with a reproducible, software-generated analysis. Every closed investment episode must produce owned-period performance, post-exit performance, and an explainable exit assessment from deterministic calculations covered by tests.

Prerequisite data for this work, in order:

1. Transaction ingestion
2. Corporate-action reconciliation
3. Investment episode generation
4. Portfolio reconstruction
5. Historical adjusted price ingestion
6. Benchmark TRI ingestion

### 15.1 Ownership-period metrics for every closed episode

For every closed investment episode, calculate:

- Episode ID
- Security ID
- Company name
- First buy date
- Final sell date
- Holding period
- Total invested capital
- Total sale proceeds
- Dividends received, when available
- Total profit or loss in rupees
- Total return percentage
- XIRR using exact dated cash flows
- Portfolio value at entry
- Portfolio value at exit
- Portfolio return during the same ownership period
- Portfolio annualized return during the same ownership period
- Small-cap benchmark level at entry
- Small-cap benchmark level at exit
- Small-cap benchmark total return
- Small-cap benchmark annualized return
- Excess return versus the portfolio
- Excess return versus the small-cap benchmark
- Maximum drawdown while held
- Maximum unrealized gain while held
- Time spent below cost
- Time spent underperforming the benchmark

### 15.2 Post-exit analysis

Require a separate post-exit analysis for the period from the final sell date to the latest available date.

For every closed episode, calculate:

- Security or successor-security return after exit
- Portfolio return after exit
- Small-cap benchmark return after exit
- Excess return of the sold security versus the portfolio
- Excess return of the sold security versus the benchmark
- Maximum gain after exit
- Maximum loss after exit
- Whether the exit avoided further losses
- Whether the exit was potentially premature
- An explainable exit assessment such as:
  - Good exit
  - Loss avoided
  - Neutral exit
  - Premature exit
  - Insufficient data

### 15.3 Methodology

1. Use XIRR, not simple CAGR, when an episode contains multiple buys, additions, partial sells, rights subscriptions, or other dated cash flows.
2. Treat buys and paid rights subscriptions as negative cash flows.
3. Treat sells and dividends as positive cash flows.
4. Splits and bonus issues change quantity but create no cash flow and must not be included directly in XIRR.
5. Mergers, demergers, and conversions must preserve economic continuity through the successor security.
6. Use adjusted price series and total-return indices wherever available.
7. Do not use future information in historical point-in-time analysis.
8. Preserve the exact source and publication date of benchmark and market data.
9. Clearly separate “performance during ownership” from “performance after exit.”
10. Do not calculate portfolio performance by simply comparing portfolio values if external inflows, outflows, or capital additions exist. Use a time-weighted return or cash-flow-adjusted methodology.
11. Store both absolute rupee profit/loss and annualized return because they answer different questions.
12. All calculations must be deterministic and covered by tests.

### 15.4 Benchmarks

- Primary small-cap benchmark: `Nifty Smallcap 250 TRI`
- Broad-market comparison: `Nifty 500 TRI`
- Optional mid-cap comparison: `Nifty Midcap 150 TRI`
- The system may choose a security-specific primary benchmark based on the company’s point-in-time market-cap classification.
- Benchmark methodology and any index-history stitching must be documented and versioned.
- Price-only indices must not be substituted for TRI data without clearly flagging the limitation.

### 15.5 Database and output model

Store or export at least these datasets:

```text
episode_cash_flows
episode_performance
portfolio_period_performance
benchmark_period_performance
post_exit_performance
sell_assessments
```

`episode_performance` and `post_exit_performance` should include the example fields defined in §11.8.

### 15.6 Acceptance criteria

- Every closed episode has complete dated cash flows.
- Stock XIRR reproduces independently calculated fixture results.
- Corporate actions without cash consideration do not affect XIRR.
- Paid rights issues are included as cash outflows.
- Portfolio and benchmark comparisons use exactly the same start and end dates.
- The system handles non-trading dates using a documented rule.
- Successor securities are used for mergers and conversions.
- No episode is marked “premature exit” solely because the stock later increased.
- Exit assessments must include both supporting and opposing evidence.
- Missing prices, dividends, benchmark values, or successor mappings generate an `Insufficient Data` result rather than invented values.
- The generated report can reproduce and replace the current Sell Since workbook.
- All calculations have unit tests.

---

## 16. Third development milestone

### Milestone 3: daily market data and benchmark ingestion

Add the historical market data required for episode performance and sell analysis:

- Daily prices
- Adjusted prices
- Volume
- Dividends, when available
- Corporate-action factors
- Benchmark TRI series

This milestone must complete historical adjusted price ingestion and benchmark TRI ingestion before Milestone 4 calculations are treated as production-ready.

Calculate or enable the inputs required for:

- Absolute return
- CAGR
- Benchmark-relative return
- Maximum drawdown
- Maximum unrealized gain
- Time underwater
- Time underperforming
- Post-exit returns
- Opportunity cost

Detailed ownership-period, post-exit, XIRR, and Sell Since–replacement requirements are specified in §15 and delivered in Milestone 4.

---

## 17. Milestone 4: Episode Performance and Sell Analysis

Deliver reproducible historical investment episode performance, sell analysis, and benchmark comparison that replaces the manual Sell Since workbook.

Deliverables:

- Stock XIRR and absolute profit/loss
- Portfolio-period comparison
- Small-cap TRI comparison
- Post-exit performance
- Exit-quality assessment
- CSV and Excel report exports
- API endpoints for episode performance and sell analysis

Acceptance criteria are those listed in §15.6, plus:

- Every closed episode can be exported with ownership-period and post-exit metrics
- Calculation version and data-quality status are stored on every result row
- Re-running the analysis on unchanged inputs produces identical outputs

---

## 18. Testing requirements

Every financial function requires unit tests.

Minimum test cases:

- One buy and full exit
- Multiple buys and partial sells
- Complete exit and later re-entry
- Bonus issue
- Split adjustment
- Rights issue
- Demerger
- Missing price
- Same-day multiple transactions
- Attempted oversell
- Liquid holding transaction
- Historical name change
- Merged/delisted security
- Episode XIRR with multiple dated cash flows
- Split/bonus excluded from XIRR cash flows
- Paid rights included as cash outflow
- Portfolio and benchmark period aligned to the same start and end dates
- Post-exit assessment with insufficient data
- Premature-exit assessment that requires more than later price appreciation alone

Use small, explicit fixtures where expected quantities and XIRR results can be calculated independently.

---

## 19. Coding standards

- Python functions require type annotations
- Public functions require docstrings
- No business logic inside API routes
- No notebook-only production logic
- No hard-coded file paths
- No silent exception swallowing
- No mutable global portfolio state
- No floating-point equality checks for money
- Use `Decimal` for monetary accounting where exactness matters
- Use explicit timezone-aware timestamps where timestamps are stored
- All database changes require Alembic migrations
- All imports must be idempotent
- Every data import receives an import batch ID
- Every generated recommendation stores its rule version

---

## 20. Agent instructions

Before asking Claude Code or Codex to implement anything, create `AGENTS.md` with these rules:

```markdown
# Agent Instructions

1. Read README.md before changing code.
2. Never modify files under data/raw.
3. Never guess missing financial values.
4. Preserve source lineage for every imported row.
5. Treat LiquidCase as liquid holdings, not an equity security.
6. Corporate actions change quantity but are not investment decisions.
7. Do not build frontend features before ingestion, validation, reconciliation, and episode tests pass.
8. Use deterministic code for financial calculations.
9. Add or update tests with every business-logic change.
10. Do not silently correct source data.
11. Keep imports idempotent.
12. Run formatting, linting, type checking, and tests before finishing.
13. Summarize files changed, assumptions made, and unresolved issues.
14. Stop and flag ambiguity when a change could alter historical holdings or returns.
```

---

## 21. Before using Claude Code or Codex

Complete this checklist:

### Files

- [ ] Final transaction file copied to `data/raw/transactions/MASTER_TRANSACTIONS_V1.xlsx`
- [ ] Final security master copied to `data/raw/security_master/SECURITY_MASTER_V1.xlsx`
- [ ] Historical portfolio files available under Research/Portfolio (or synced to `data/raw/portfolio_snapshots/`)
- [ ] `PMS-Decision-Platform.code-workspace` opened so Research is indexed
- [ ] Raw files confirmed read-only or backed up
- [ ] LiquidCase confirmed excluded from Security Master
- [ ] Final E2E split adjustment confirmed
- [ ] BSE code and ISIN fields completed

### Development environment

- [ ] Git repository initialized
- [ ] Private GitHub repository created
- [ ] Python 3.12 installed
- [ ] uv installed
- [ ] Docker installed
- [ ] Node.js and pnpm installed
- [ ] PostgreSQL container starts successfully
- [ ] `.env` created from `.env.example`
- [ ] Initial dependencies installed
- [ ] First commit created

### Documentation

- [ ] README.md saved
- [ ] AGENTS.md saved
- [ ] Data dictionary confirmed
- [ ] Episode rules confirmed
- [ ] Liquid holding treatment confirmed
- [ ] Acceptance criteria confirmed

Only after this checklist is complete should an agent begin implementation.

---

## 22. First prompt for Claude Code or Codex

Use this as the first implementation prompt:

```text
Read README.md and AGENTS.md completely before making changes.

Implement Milestone 1 only: deterministic ingestion, validation, PostgreSQL persistence, investment episode generation, and decision event generation.

Inputs:
- data/raw/transactions/MASTER_TRANSACTIONS_V1.xlsx
- data/raw/security_master/SECURITY_MASTER_V1.xlsx

Requirements:
1. Create SQLAlchemy models and Alembic migrations for securities, import_batches, transactions, investment_episodes, decision_events, and liquid_transactions.
2. Build idempotent Excel importers.
3. Map every transaction to Security ID using the Security Master.
4. Treat LiquidCase as liquid holdings and never as an equity security.
5. Preserve source file, sheet, row, and source note.
6. Enforce quantity sign and event-type rules from README.md.
7. Generate running quantities per security.
8. Generate investment episodes deterministically.
9. Generate INITIATE, ADD, REDUCE, EXIT, and CORPORATE_ACTION decision events.
10. Add tests for normal buys/sells, partial exits, re-entry, split, bonus, rights, demerger, missing price, and oversell.
11. Add a CLI command that imports the files and exports:
   - investment_episodes.csv
   - decision_events.csv
   - validation_report.csv
12. Do not build frontend code.
13. Do not modify any file under data/raw.
14. Run Ruff, MyPy, and Pytest before finishing.

Before coding, inspect the actual workbook structures and report any discrepancies between the files and README assumptions. If a discrepancy could affect quantities or episode boundaries, stop and document it instead of guessing.
```

---

## 23. Recommended agent workflow

Use small prompts and review every milestone.

Recommended sequence:

1. Scaffold backend and tooling
2. Implement database models
3. Inspect workbook schemas
4. Implement Security Master importer
5. Implement transaction importer
6. Implement validation
7. Implement running quantity engine
8. Implement episode engine
9. Implement decision events
10. Add CLI exports
11. Run tests
12. Review outputs manually
13. Commit Milestone 1
14. Begin Milestone 2
15. Complete Milestone 3 market-data and TRI ingestion
16. Implement Milestone 4 episode performance and sell analysis
17. Only then begin frontend application development

Do not ask an agent to build the complete system in one prompt.

---

## 24. Definition of ready for application development

The project is ready for frontend application development only when:

- Milestone 1 tests pass
- Historical quantities reconcile
- Episode outputs are reviewed
- Milestone 2 portfolio reconstruction works
- Price data is integrated
- Benchmark TRI data is integrated
- Core analytics are reproducible
- Milestone 4 episode performance and sell analysis can replace the manual Sell Since workbook for closed episodes

Until then, the “software” is the data and analytical engine, not the user interface.

---

## 25. Long-term roadmap

### Phase A — Data foundation

- Security Master
- Transactions
- Corporate actions
- Liquid holdings
- Historical snapshots
- Reconciliation

### Phase B — Portfolio intelligence

- Investment episodes
- Decision events
- Portfolio reconstruction
- Historical adjusted prices
- Benchmark TRI ingestion
- Episode performance and sell analysis
- Performance
- Attribution
- Drawdowns
- Post-exit analysis

### Phase C — Point-in-time research data

- Fundamentals
- Ownership
- Valuation
- Filings
- Transcripts
- News

### Phase D — Sell-discipline research

- Underperformance signals
- Fundamental deterioration
- Cycle indicators
- Governance indicators
- Opportunity cost
- False-exit analysis
- Walk-forward backtesting

### Phase E — Decision-support application

- Portfolio dashboard
- Attention queue
- Company page
- Historical decision lab
- Optimizer
- Research search
- Reports
- Recommendation audit trail

---

## 26. Cloud staging — deferred (nice later)

Not required for Samir/Julesh to start using the hosted staging app. Track and do after cutover smoke tests and secret rotation.

| Item | Notes |
|------|--------|
| Mac auto-upload watcher | Watch `DailyEditFiles` and upload on save. Manual **Upload + Reimport** in the UI is enough for v1. |
| Pivot filename polish | Server already materializes as `PivotPoints.xlsx`. Optional: rename the source workbook so uploads don’t carry the long “Backup 17.07…” name. |
| Commit `scripts/sync_daily_edit_canonical.sh` | Local helper that copies the newest Client/Charts/SCA/Pivot matches into the four canonical DailyEdit names. Optional to keep in git. |
| Keep `RESET_FILES/` out of git | Approved one-shot workbooks for resets. Do not commit large `.xlsx` into the repo; leave the folder gitignored or local-only. |

Related cutover docs: `docs/centralization/DEPLOYMENT_RUNBOOK.md`, `deploy/railway/README.md`.

---

## 27. Final rule

Do not optimize the interface before validating the investment logic.

The correct sequence is:

```text
Raw data
→ deterministic ingestion
→ validation
→ reconciliation
→ investment episodes
→ portfolio reconstruction
→ historical adjusted prices
→ benchmark TRI ingestion
→ episode performance and sell analysis
→ analytics
→ sell-rule research
→ decision-support API
→ frontend
```
