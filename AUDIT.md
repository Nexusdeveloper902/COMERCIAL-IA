# COMERCIAL-IA — Pre-Launch Audit & Recommendations

> Audit performed before leaving the pipeline running unattended on an Oracle
> Cloud instance. Findings are prioritized: **MUST FIX (before go-live)**,
> **SHOULD FIX (soon)**, **NICE TO HAVE (later)**.

---

## 1. What's solid (no action needed)

| Area | Status | Notes |
|------|--------|-------|
| Raw/normalized/rejected separation | ✅ | Raw never mutated; rejected kept w/ reason. |
| Resumability | ✅ | `PipelineState` tracks seen URLs + raw keys; survives crashes. |
| Incremental JSONL writes | ✅ | Line-buffered flush; partial files stay valid. |
| Identity dedup | ✅ | EAN/UPC > MPN+brand > brand+model; multi-seller offers merged. |
| Scraping safety | ✅ | robots.txt, rate limit, exp backoff, cache. No auth/CAPTCHA bypass. |
| Honesty of data | ✅ | Sample fixtures tagged `source_kind="sample"`; never presented as real. |
| Tests | ✅ | 42 passing (unit + e2e). |
| Unknown-spec preservation | ✅ | `specifications_extra` keeps unmapped specs verbatim. |

---

## 2. MUST FIX before go-live — RESOLVED ✅

### 2.1 No real source adapter — only `SampleSourceScraper` ✅ FIXED
Added `BestBuyScraper` (`src/commercial_ai/scrapers/bestbuy.py`) using Best Buy's
public [Products API](https://developer.bestbuy.com) — a legitimate, free,
developer-facing API returning real product data (price, specs, UPC,
manufacturer, model). No HTML scraping, no auth/CAPTCHA bypass. Registered in
`config/config.yaml` (commented out by default; enable by uncommenting
`- bestbuy` and providing `BBY_API_KEY`).

### 2.2 Raw JSONL unbounded growth / O(N²) re-reads ✅ FIXED
Raw output is now **date-sharded** (`data/raw/raw_YYYYMMDD.jsonl`). The
normalizer processes only **un-processed shards**, marking each done in
`data/.pipeline_state.json` (new `processed_shards` state). A crash resumes from
the next shard without re-processing old data.

### 2.3 `product_id` collision risk for generic brand+model ✅ FIXED
`fingerprint()` now rejects generic model strings (bare category nouns like
"Mouse"/"Teclado", and very short pure-letter tokens) via `_is_generic_model()`.
The brand+model path is only used when the model contains a digit or is
sufficiently specific. Covered by `test_fingerprint_rejects_generic_model`.

---

## 3. SHOULD FIX soon — mostly RESOLVED ✅

### 3.1 Normalize stage holds everything in RAM ⚠️ PARTIAL
`run_pipeline` still builds one `Deduplicator` and one `rejected` list in memory.
Fine for tens of thousands of records; problematic at hundreds of thousands.
For the intended school-project scale this is acceptable. Future: stream dedup
with an on-disk index (SQLite/duckdb) keyed by fingerprint.

### 3.2 No disk-space guard ✅ FIXED
`run_pipeline` now checks free disk space before processing and raises
`RuntimeError` if free space < `MIN_FREE_GB` (2 GB). The free GB is recorded in
each run-history entry and `last_run_stats.json`.

### 3.3 `last_run_stats.json` overwritten — no history ✅ FIXED
Run history now **appends** to `data/run_history.jsonl` (never overwritten) so
you can see trends and detect stalls. `last_run_stats.json` is kept as a quick
latest-snapshot for the `--status` command.

### 3.4 No alerting on failure ✅ FIXED
The systemd service now has `OnFailure=` pointing to a
`comercial-ai-pipeline-notify.service` unit that journals an error marker
(extendable to email/webhook). Check failures with:
`journalctl -t comercial-ai-notify -p err`.

### 3.5 User-Agent contact is a placeholder ⚠️ REMAINS
`config.yaml` still has `data-team@example.com`. Replace with a real contact
before scraping real sites at volume. Low priority for a school project using
the API (Best Buy's API doesn't rely on the User-Agent for politeness).

---

## 4. NICE TO HAVE (later)

- **Parquet dependency optional but recommended**: install `pandas`+`pyarrow`
  on the box (the bootstrap script tries `[derived]` extras; falls back to
  JSONL+CSV only if unavailable).
- **Schema versioning / migration path**: `schema_version: "1.0"` is set on
  products but there's no migration logic. Add before changing the schema.
- **Data retention policy**: define how long raw/rejected are kept (legal + disk).
- **Metrics export**: expose run stats to Prometheus for dashboards.
- **Interaction schema**: `data/interactions/` is reserved but empty; design it
  before the ML phase so collection can start early.

---

## 5. Oracle deployment recommendations

1. **Shape:** the Always-Free eligible `VM.Standard.A1.Flex` (Ampere ARM, up to
   4 OCPU / 24GB) is plenty for this I/O-bound workload. The venv + deps are
   arch-neutral (pure Python). If you pick ARM, no code changes needed.
2. **Disk:** 50GB block volume default is fine to start; grow the boot/boot-disk
   attachment if you plan to retain raw data long-term.
3. **Networking:** keep the instance in a private subnet + use a NAT gateway for
   outbound scraping. No inbound ports required (the pipeline only fetches).
4. **Firewall:** Oracle's VCN security list + iptables both default to deny
   inbound — leave it that way.
5. **Secrets:** don't bake any API keys into the image. If a real adapter needs
   a key, inject it via a systemd `EnvironmentFile=` owned by root (chmod 600),
   never into the repo or config.yaml.
6. **Backups:** the only stateful artifact is `data/.pipeline_state.json` + the
   raw/normalized JSONL. Snapshot the block volume daily.
7. **Monitoring:** `bootstrap_oracle.sh --status` shows timer + last run; pair
   with Oracle Cloud's built-in CPU/disk alarms.
8. **Updates:** enable unattended-upgrades for security patches on the OS; pin
   the project deps via the venv (don't let `pip` auto-upgrade).

---

## 6. Bootstrap script recap

`scripts/bootstrap_oracle.sh` is **rerunnable** and idempotent:
- installs system packages + creates a `cai` service user
- syncs the repo to `/opt/comercial-ia`, creates a venv, installs deps
- runs the test suite as a smoke gate before scheduling
- installs a **systemd timer** (every 6h by default; `CAI_POLL_INTERVAL_MIN` env override)
- wires a **failure notifier** (`OnFailure=` → `comercial-ai-pipeline-notify.service`)
- injects an optional **Best Buy API key** via a root-owned `EnvironmentFile=`
- sets up logrotate
- `--max-products N` / `-m N` caps how many NEW records each run collects
- `--no-timer` for manual-only, `--status` for a quick health check

```bash
# first install (cap each run at 2000 new products, default 6h timer)
sudo bash scripts/bootstrap_oracle.sh -m 2000

# rerun anytime to update code/deps (safe)
sudo bash scripts/bootstrap_oracle.sh -m 2000

# health check (timer status + last run stats)
sudo bash scripts/bootstrap_oracle.sh --status

# stop the auto-run
sudo systemctl disable --now comercial-ai-pipeline.timer
```

### Enabling the Best Buy API key on the Oracle box

The key is injected via a root-owned env file (never committed to the repo):

```bash
# create the env file (root-only readable)
sudo sh -c 'echo "BBY_API_KEY=your_real_api_key_here" > /opt/comercial-ia/.env.runtime'
sudo chmod 600 /opt/comercial-ia/.env.runtime
sudo chown root:root /opt/comercial-ia/.env.runtime

# enable the bestbuy source in config
sudo sed -i 's/^# - bestbuy/    - bestbuy/' /opt/comercial-ia/config/config.yaml

# trigger a manual run to verify
sudo systemctl start comercial-ai-pipeline.service
sudo tail -f /opt/comercial-ia/logs/pipeline.log
```

### Monitoring commands cheat-sheet

```bash
# last run snapshot
cat /opt/comercial-ia/data/last_run_stats.json

# full run history (one JSON per line)
cat /opt/comercial-ia/data/run_history.jsonl | python -m json.tool --json-lines

# recent pipeline logs
tail -100 /opt/comercial-ia/logs/pipeline.log

# error logs only
tail -100 /opt/comercial-ia/logs/pipeline.err.log

# failure notifier journal entries
journalctl -t comercial-ai-notify -p err --since "1 day ago"

# timer schedule
systemctl list-timers comercial-ai-pipeline.timer
```
