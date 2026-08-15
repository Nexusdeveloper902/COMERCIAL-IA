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

## 2. MUST FIX before go-live

### 2.1 No real source adapter — only `SampleSourceScraper`
**Severity: blocking for actual data collection.**
`config/config.yaml` only lists `sample`. The pipeline will run forever producing
the same 6 sample records. Before "leaving the baby running", you need at least
one **real** `BaseScraper` subclass for a public source you're permitted to use
(e.g. a retailer JSON API, a public product catalog API, or an Open Data source).
Until then, the Oracle box is collecting nothing new.

**Action:** implement one real adapter and add its name to `pipeline.sources`.

### 2.2 Raw JSONL is appended, not rotated — unbounded growth
`collect_raw` opens `raw_latest.jsonl` in append mode (`"a"`). On a long-running
box this file grows forever and the normalize stage re-reads the **entire** file
every run (`read_jsonl(raw_path)` iterates all lines). At scale this becomes O(N²)
across runs and slow.

**Action (this PR):** the bootstrap script rotates logs, but raw JSONL should be
sharded by date. Recommended follow-up: write to `data/raw/raw_YYYYMMDD.jsonl`
and have the normalizer process only the latest shard (or track processed-line
offsets in state). Flagged here; not blocking for small volumes.

### 2.3 `product_id` collision risk when brand+model is the only key
When no EAN/UPC/MPN exists, the fingerprint is `brand+model`. Two genuinely
different products with the same brand+model string (e.g. "Logitech Mouse") would
wrongly merge. Currently mitigated because model is often the MPN, but for real
scrapes with weak model extraction this will silently over-merge.

**Action:** tighten `_model_from_title` heuristics or require MPN for dedup when
brand+model looks generic. Low risk for now, flagged for the first real adapter.

---

## 3. SHOULD FIX soon

### 3.1 Normalize stage holds everything in RAM
`run_pipeline` builds one `Deduplicator` and one `rejected` list in memory. Fine
for thousands of records; problematic at hundreds of thousands. For the intended
"leave it running" scale, consider streaming dedup with an on-disk index
(SQLite/duckdb) keyed by fingerprint.

### 3.2 No disk-space guard
Nothing checks free disk before writing. A runaway scrape could fill the volume
and crash the box. The bootstrap script could add a pre-run `df` check.

### 3.3 `last_run_stats.json` overwritten each run — no history
I added a stats file for monitoring, but it's overwritten. For unattended ops you
want a run history (append a line to `data/run_history.jsonl`) so you can see
trends and detect stalls.

### 3.4 No alerting on failure
The systemd service is `Type=oneshot`; if it fails, nothing notifies you. At
minimum configure `OnFailure=` to a notify unit, or ship logs to a sink.

### 3.5 User-Agent contact is a placeholder
`config.yaml` has `data-team@example.com`. Replace with a real contact before
scraping real sites (politeness + some sites require it).

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
- sets up logrotate
- `--max-products N` / `-m N` caps how many NEW records each run collects
- `--no-timer` for manual-only, `--status` for a quick health check

```bash
# first install (cap each run at 2000 new products, default 6h timer)
sudo bash scripts/bootstrap_oracle.sh -m 2000

# rerun anytime to update code/deps (safe)
sudo bash scripts/bootstrap_oracle.sh -m 2000

# health check
sudo bash scripts/bootstrap_oracle.sh --status

# stop the auto-run
sudo systemctl disable --now comercial-ai-pipeline.timer
```
