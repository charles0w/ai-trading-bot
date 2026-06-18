---
name: alpaca-paper-setup
type: runbook
parent: ai-trading-bot
date: 2026-06-16
updated: 2026-06-16
tags:
  - ai-trading-bot
  - alpaca
  - paper
  - setup
---

# Alpaca paper account setup (for the swing-trader pivot)

> [!important] Two facts that change the steps
> 1. **Long calls/puts require options Level 2 on Alpaca, not Level 1.** Level 1 is only covered calls / cash-secured puts. (lambos's code comment saying "Level 1" is wrong — corrected in `trader_core`.) Source: [Alpaca — option levels](https://alpaca.markets/support/what-option-levels-or-tiers-do-you-provide).
> 2. **Paper options are auto-approved** — even multi-leg — so there's no waiting period or financial-disclosure gate like live trading. Source: [Alpaca options overview](https://docs.alpaca.markets/us/docs/options-trading-overview).

Goal: a **separate** Alpaca paper account (clean P&L attribution vs. lambos) with options **Level 2** enabled and API keys wired into `ai-trading-bot/.env`.

## Step 1 — Create / log into an account

- Go to **app.alpaca.markets** and sign up (or log in).
- For clean separation from the lambos paper account, **use a different email** so this is its own login and its own paper P&L. (Alpaca also supports multiple paper accounts under one login — either works; separate login is simplest to reason about.)

## Step 2 — Switch to the Paper environment

- In the dashboard, toggle the environment switch from **Live** to **Paper** (top of the left sidebar / account switcher). Everything below must be done while in **Paper**.

## Step 3 — Enable options Level 2

- Open **Account → Configuration → Options Trading** (a.k.a. "Enable options trading").
- Apply and select **Level 2** (Long Call / Long Put). On paper this is auto-approved.
- Confirm the account shows **Options: Level 2** before continuing.

## Step 4 — Generate paper API keys

- In the **Paper** dashboard home, find **API Keys → Generate New Key**.
- Copy the **Key ID** and the **Secret Key**. The secret is shown **once** — store it now.
- Paper base URL is `https://paper-api.alpaca.markets` (alpaca-py selects it automatically when `paper=True`).

## Step 5 — Wire keys into `ai-trading-bot/.env`

Create `ai-trading-bot/.env` (it's already git-ignored — never commit it):

```dotenv
# Alpaca PAPER — separate account from lambos
ALPACA_API_KEY=PK_your_paper_key_id
ALPACA_SECRET_KEY=your_paper_secret
ALPACA_PAPER=true
```

> [!warning] Secrets
> These are paper keys (no real money), but still treat them as secrets — don't paste them into chat, commit them, or share screenshots. Rotate from the dashboard if exposed.

## Step 6 — Install the SDK

```bash
cd ~/Desktop/ai-trading-bot
python3 -m venv .venv && source .venv/bin/activate
pip install alpaca-py
```

## Step 7 — Verify the connection (uses trader_core)

```python
# scripts/check_alpaca.py
import os
from datetime import date, timedelta
from dotenv import load_dotenv
from trader_core.broker.alpaca_client import AlpacaBroker

load_dotenv()
b = AlpacaBroker(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"], paper=True)
print("Options buying power:", b.buying_power_usd())

# resolve a near-dated SPY call to confirm options Level 2 + data work
expiry = date.today() + timedelta(days=35)
c = b.find_option_contract("SPY", expiry, 600.0, "call")
print("Resolved contract:", c)
```

`pip install python-dotenv` if needed. A non-zero buying power and a resolved (or gracefully `None`) contract means the account, level, and keys are good. If `find_option_contract` errors with a permissions message, options Level 2 isn't active yet (re-check Step 3).

## Step 8 — First paper trade (later, gated)

Once keys verify, the Phase-0 smoke from [[phase0-execution-reuse-2026-06-16]] runs against the real paper account: build a `TradeIntent` → resolve a contract → size → `execute_entry` (set `cfg.execution.dry_run = False`) → confirm the exit manager's TP/SL/max-hold fires. That's the Phase-0 gate in [[pivot-2026-06-16]].

> [!note] My boundary
> This is **paper** (simulated) money — fine for me to help run end-to-end. Going **live** later is your action: you generate live keys, flip `ALPACA_PAPER=false`, fund, and watch the first fills by hand. I won't place real-money orders on your behalf.

## See also
- [[phase0-execution-reuse-2026-06-16]] · [[pivot-2026-06-16]] · [[strategy-research-2026-06-16]]
- [Alpaca options overview](https://docs.alpaca.markets/us/docs/options-trading-overview) · [Option levels](https://alpaca.markets/support/what-option-levels-or-tiers-do-you-provide)
