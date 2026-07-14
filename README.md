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
- PostgreSQL database stored outside OneDrive
- Optional Tailscale for private remote access

### Document intelligence

- PyMuPDF
- PostgreSQL full-text search
- pgvector only where semantic retrieval materially improves search
- Local embeddings or approved private API
- Page-level citations for every research answer

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

## 15. Third development milestone

### Milestone 3: daily market data and episode analytics

Add:

- Daily prices
- Adjusted prices
- Volume
- Benchmarks
- Corporate-action factors

Calculate:

- Absolute return
- CAGR
- Benchmark-relative return
- Maximum drawdown
- Maximum unrealized gain
- Time underwater
- Time underperforming
- Post-exit returns
- Opportunity cost

---

## 16. Testing requirements

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

Use small, explicit fixtures where expected quantities can be calculated manually.

---

## 17. Coding standards

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

## 18. Agent instructions

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

## 19. Before using Claude Code or Codex

Complete this checklist:

### Files

- [ ] Final transaction file copied to `data/raw/transactions/MASTER_TRANSACTIONS_V1.xlsx`
- [ ] Final security master copied to `data/raw/security_master/SECURITY_MASTER_V1.xlsx`
- [ ] Historical portfolio files copied to `data/raw/portfolio_snapshots/`
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

## 20. First prompt for Claude Code or Codex

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

## 21. Recommended agent workflow

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

Do not ask an agent to build the complete system in one prompt.

---

## 22. Definition of ready for application development

The project is ready for frontend application development only when:

- Milestone 1 tests pass
- Historical quantities reconcile
- Episode outputs are reviewed
- Milestone 2 portfolio reconstruction works
- Price data is integrated
- Core analytics are reproducible

Until then, the “software” is the data and analytical engine, not the user interface.

---

## 23. Long-term roadmap

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

## 24. Final rule

Do not optimize the interface before validating the investment logic.

The correct sequence is:

```text
Raw data
→ deterministic ingestion
→ validation
→ reconciliation
→ investment episodes
→ portfolio reconstruction
→ market data
→ analytics
→ sell-rule research
→ decision-support API
→ frontend
```
