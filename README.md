# obscura-benchmark

Conformance, capability, and performance benchmarks for
[Obscura](https://github.com/h4ckf0r0day/obscura), a headless browser engine
written in Rust for web scraping and AI agent automation. Obscura runs real
JavaScript on a V8 runtime and builds a live DOM, but has no rendering, layout,
or paint pipeline. These benchmarks measure the part that matters for scraping
and automation: does it load the page, run the scripts correctly, and expose the
resulting DOM, and how fast and how cheaply does it do that.

## Benchmark tracks

| track | question it answers | where |
| ----- | ------------------- | ----- |
| WPT conformance | how much of the web platform does Obscura implement correctly | `crates/wpt-runner`, `crates/triage` |
| Obstacle course | does it handle the modern web (React/SPA/async/web APIs), and how fast | `obstacle-course/` |
| vs headless Chrome | how does its speed and memory compare to the standard headless engine | `compare/` |
| Real-world corpus | does it render real public pages, including SPAs | `realworld/` |
| Perf bench | per-page `fetch` / `scrape` latency on a small URL set | `crates/perf-bench` |
| Reliability | does it crash, panic, or hang on a large corpus of real pages | `reliability/` |

## Results

Latest full pass: 2026-06-04, on a 10-core host. Conformance numbers are from
the `feat/wpt-conformance-4` build; rerun the suites to refresh.

### Web Platform Tests (conformance)

Subtest pass rate by tier (a tier is a capability scope, defined in
`crates/triage/src/tiers.list`, not a cherry-picked subset). A subtest is one
assertion; a single test file holds many, so subtest pass rate is the standard
conformance measure:

| tier | subtests passing | role |
| ---- | ---------------- | ---- |
| Core | 321,042 / 393,513 (**81.6%**) | the DOM/HTML/URL/fetch scraping contract |
| Relevant | 513,559 / 599,962 (**85.6%**) | Core plus broader JS-observable correctness |
| Full | 583,813 / 929,308 (62.8%) | the whole suite, for transparency |

Core subtest pass rate over time:

| date | obscura state | Core subtests |
| ---- | ------------- | ------------- |
| 2026-06-03 | baseline | 8.0% |
| 2026-06-04 | round 2 | 15.4% |
| 2026-06-04 | + charset/URL encoding | 72.7% |
| 2026-06-04 | + IDL reflection, attr folding, storage | **81.6%** |

The "Full" tier includes large subtrees Obscura intentionally does not implement
(layout, rendering, media, hardware), so it is reported only for transparency.
The Core and Relevant tiers are the headline because they exclude those by
capability, not by outcome. See `crates/triage/src/tiers.list` for the exact
rules. For cross-engine context, the same WPT areas for Chrome/Firefox/Safari
are published on [wpt.fyi](https://wpt.fyi/).

### Obstacle course (capability + speed)

33 / 33 stages pass, median ~32 ms per stage (cold `obscura fetch`, including
process startup). Covers client-side React/Preact/Vue, SSR hydration, ES modules
and dynamic import, IntersectionObserver/MutationObserver, `fetch` + pushState
SPAs, the URL/TextDecoder/FileAPI/Range/Selection/custom-element/dialog web-API
surface, the `--dump` extraction modes, charset decoding, cookies, and stealth
fingerprint consistency.

### vs headless Chrome (speed + memory)

Cold process per page, both fully rendering the same client-side app (verified:
obscura serializes the post-JavaScript DOM, e.g. 100 React `<li>` elements that
are not in the shipped HTML):

| page | obscura | headless Chrome | obscura advantage |
| ---- | ------- | --------------- | ----------------- |
| react | 88 ms, 30 MB | 1097 ms, 185 MB | 12x faster, 6x less memory |
| preact | 59 ms, 29 MB | 1032 ms, 186 MB | 18x faster, 6x less memory |
| vue | 97 ms, 32 MB | 1144 ms, 184 MB | 12x faster, 6x less memory |

Across all 33 obstacle-course fixtures the median is ~23x faster and ~7x less
memory (obscura ~27 MB vs Chrome ~185 MB per process). The framework rows above
are the heaviest-render, most conservative cases; lighter pages widen the gap
because Chrome pays the same fixed startup regardless of the page.

Throughput and memory as concurrency rises (24 React-app loads, idle host):

| engine | 1 worker | 4 workers | 8 workers |
| ------ | -------- | --------- | --------- |
| obscura | 11 pg/s, 29 MB | **39 pg/s, 113 MB** | 21 pg/s, 132 MB |
| headless Chrome | 1.1 pg/s, 1.1 GB | 2.7 pg/s, 4.2 GB | 2.8 pg/s, **7.1 GB** |

Obscura sustains far higher throughput at a fraction of the memory. Chrome pays
a large fixed startup (process + browser stack) on every page; under concurrency
its RAM climbs into the gigabytes while Obscura stays in the low hundreds of MB.
This is the scraping path only; Obscura does no rendering, and production Chrome
would reuse one browser across tabs (the cold-process numbers are Chrome's worst
case).

### Real-world corpus (vs headless Chrome)

24 live public pages, fetched with obscura and headless Chrome side by side:

| engine | rendered | median latency | median peak RSS |
| ------ | -------- | -------------- | --------------- |
| obscura | 22 / 24 (91.7%) | 2.0 s | **35.6 MB** |
| headless Chrome | 22 / 24 (91.7%) | 1.5 s | 191.8 MB |

Same render-success rate, including the client-rendered SPAs (react.dev,
vuejs.org, svelte.dev, angular.dev, remix.run). Obscura uses ~5x less memory on
every page. Latency is mixed: obscura is much faster on content pages (example.com
63 ms vs 940 ms, Wikipedia 180 ms vs 1.5 s) and slower on heavy client-rendered
SPAs (angular.dev 15 s vs 3 s), where its settle wait dominates. Obscura rendered
github.com where Chrome timed out; Chrome rendered solidjs.com where obscura did
not. The live web drifts, so these are a snapshot; see `realworld/sites.txt`.

### Reliability (crash / hang sweep)

Conformance and speed do not matter if the engine crashes or hangs on a live
page. A 1500-URL corpus (a one-level crawl from the real-world seed list) is
rendered through obscura, classifying each outcome from the exit code and stderr:

| outcome | count |
| ------- | ----- |
| rendered | 1438 / 1500 (95.9%) |
| thin / blocked | 58 |
| bounded hang (deadline) | 4 |
| **crash (signal)** | **0** |
| **panic** | **0** |

Zero crashes and zero panics across 1500 diverse pages. Any page that does not
finish in its budget is terminated deterministically (a V8 termination watchdog
plus a process-level hard deadline), so no page can wedge a worker. The four
bounded hangs are heavy SPAs that exceed the tight per-page budget under 12-way
concurrency; each renders normally when run on its own. Run it with
`OBSCURA_BIN=<bin> python3 reliability/sweep.py`.

## 1. WPT conformance

`crates/wpt-runner` drives Obscura's CLI: it serves the Web Platform Tests over
the standard WPT server and runs one `obscura fetch` per test, reading the
results that `wpt-overlay/resources/testharnessreport.js` leaves in the page.
`crates/triage` then groups failures into deduplicated root causes and computes
the per-tier pass rates.

```sh
# one-time setup: clone WPT, install the report overlay, build the manifest
scripts/setup-wpt.sh
# then add the WPT hostnames once (needs sudo), as printed by setup-wpt.sh:
#   ( cd wpt && ./wpt make-hosts-file ) | sudo tee -a /etc/hosts

# run a full pass (writes results/wpt-<stamp>.json and results/triage.md)
OBSCURA_BIN=/path/to/obscura scripts/run-wpt.sh --concurrency 32 --wait-secs 15

# a subset, by path filter
OBSCURA_BIN=/path/to/obscura scripts/run-wpt.sh dom/ url/ encoding/
```

A full pass is ~30k files and takes a few hours. Use a concurrency that does not
oversubscribe the host: oversubscription makes per-test timeouts fire, which
silently drops results and depresses the pass rate. The output is
`results/triage.md` (the tier table plus the top error signatures by spec area).

## 2. Obstacle course

A curated set of small self-contained modern-web pages that a no-DOM-engine
browser cannot handle. Each fixture runs its JavaScript and asserts a
deterministic result; the runner also times each page. See
`obstacle-course/README.md` for the full stage list.

```sh
OBSCURA_BIN=/path/to/obscura scripts/run-obstacle-course.sh
OBSCURA_BIN=/path/to/obscura scripts/run-obstacle-course.sh --filter react --runs 10
```

It exits non-zero if any stage's result does not match, so it doubles as a
correctness regression check.

## 3. Head-to-head vs Chrome

`compare/` runs Obscura and headless Chrome as cold processes over the same
pages and reports latency, peak memory, and throughput under concurrency. See
`compare/README.md`.

```sh
OBSCURA_BIN=/path/to/obscura CHROME_BIN=google-chrome scripts/run-compare.sh
```

Run it on an idle host; CPU contention skews throughput (memory is unaffected).

## 4. Real-world corpus

`realworld/` fetches a list of live public pages and reports render-success rate,
latency, and memory. See `realworld/README.md`.

```sh
OBSCURA_BIN=/path/to/obscura scripts/run-realworld.sh
```

## 5. Perf bench

`crates/perf-bench` times `obscura fetch` / `obscura scrape` on a small default
URL set (override by passing URLs).

```sh
OBSCURA_BIN=/path/to/obscura scripts/run-bench.sh
OBSCURA_BIN=/path/to/obscura scripts/run-bench.sh https://example.com https://news.ycombinator.com
```

## Repo layout

```
crates/
  wpt-runner/      runs WPT against obscura (one `obscura fetch` per test)
  triage/          groups WPT failures into root causes; tiers.list defines the tiers
  perf-bench/      times `obscura fetch` / `obscura scrape`
obstacle-course/   modern-web capability + speed fixtures (+ run.py, manifest.json)
compare/           obscura vs headless Chrome: head-to-head.py, scale.py
realworld/         live-page render-success corpus: sites.txt, run.py
wpt-overlay/       the custom WPT report script installed into the WPT checkout
scripts/           setup and run wrappers
results/           generated run artifacts (gitignored)
wpt/               the WPT checkout (gitignored; created by setup-wpt.sh)
```

## Setup and requirements

- Rust toolchain (`cargo build --release` builds the runner, triage, and perf-bench).
- An Obscura binary, passed via `OBSCURA_BIN`.
- Python 3 for the obstacle-course, compare, and realworld runners.
  `compare/scale.py` uses `psutil` for memory sampling (`pip install psutil`),
  and the compare/realworld harnesses read peak RSS from GNU `time -v`.
- For the head-to-head, a Chrome or Chromium build (`CHROME_BIN`).
- For WPT, the one-time `scripts/setup-wpt.sh` (clones WPT, builds the manifest,
  installs the report overlay) plus the WPT hostnames in `/etc/hosts`.

`results/` and the `wpt/` checkout are gitignored; run artifacts are regenerated
by the scripts.
