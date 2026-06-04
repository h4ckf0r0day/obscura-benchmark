# Obstacle course

A curated set of small, self-contained modern-web pages that exercise the
capabilities a real scraping/automation engine needs and that a no-DOM-engine
headless browser cannot handle: client-side React, SPA routing, async (`fetch`)
rendering, custom elements / shadow DOM, deferred (timer) content, and raw DOM
throughput.

It is the capability + speed counterpart to the WPT conformance suite: each
stage asserts that the JS-rendered DOM matches an expected value (correctness)
and records per-page latency (warmup + timed runs, min/median).

## Layout

- `fixtures/` — one self-contained HTML page per stage. Each runs its JS and
  sets `window.__obstacle` to a deterministic string the runner checks.
- `vendor/` — pinned third-party libs served locally (React 18 UMD), so runs are
  deterministic and offline.
- `data/` — same-origin resources fetched by fixtures.
- `manifest.json` — the stage list: file, the `--eval` check, the expected
  value, and run parameters (wait/timeout/runs/warmup).
- `run.py` — the runner: serves this directory over a local HTTP origin and
  drives `obscura fetch` against each stage.

## Running

```sh
OBSCURA_BIN=/path/to/obscura ../scripts/run-obstacle-course.sh
# or directly:
OBSCURA_BIN=/path/to/obscura python3 run.py            # table
OBSCURA_BIN=/path/to/obscura python3 run.py --json     # machine-readable
OBSCURA_BIN=/path/to/obscura python3 run.py --filter react --runs 10
```

obscura blocks private/loopback addresses by default, so the runner passes
`--allow-private-network` (the fixtures are served on `127.0.0.1`).

## Stages

Grouped by the obscura feature they exercise (every stage is also timed):

**baseline / perf**
| stage | exercises |
| ----- | --------- |
| static | baseline HTML parse + `querySelectorAll` |
| dom-build | vanilla-JS DOM throughput (build 5000 rows) |

**frameworks** — client-side rendering a no-DOM-engine browser can't do
| stage | exercises |
| ----- | --------- |
| react | React 18 client render (reads the resulting `<li>`s) |
| preact | Preact `h()`/`render()` |
| vue | Vue 3 `createApp`/`mount` |

**capability**
| stage | exercises |
| ----- | --------- |
| async-render | `fetch()` a same-origin JSON resource, then render |
| spa-router | `history.pushState` client-side routing |
| timers | `setTimeout` chain + microtask (event-loop settle) |

**web-api** — the JS/DOM surface obscura implements
| stage | exercises |
| ----- | --------- |
| web-component | custom element + shadow DOM render |
| url | WHATWG `URL` decomposition |
| textdecoder | `TextDecoder` legacy charset (Shift_JIS → あ) |
| fileapi | `Blob` + `FileReader.readAsText` |
| range | `Range` selectNodeContents + stringify |
| selection | `Selection.selectAllChildren` |
| custom-element | `customElements.define` + upgrade + `connectedCallback` |
| dialog | `HTMLDialogElement` showModal/close/returnValue |
| input-step | `<input type=number>` `valueAsNumber`/`stepUp` |

**extraction** — the `--dump` CLI modes
| stage | exercises |
| ----- | --------- |
| extract-article | `--dump text` readability (keeps article, strips nav/footer) |
| extract-markdown | `--dump markdown` (headings, lists, links, code) |
| extract-links | `--dump links` (anchor harvesting) |
| extract-html | `--dump html` (serializes the live, JS-mutated DOM) |

**scraping** — engine/stealth features
| stage | exercises |
| ----- | --------- |
| fingerprint | `navigator.userAgent`/`webdriver`/`platform`/timezone consistency |
| cookies | `document.cookie` round-trip through the cookie jar |
| charset-shiftjis | raw Shift_JIS bytes + `<meta charset>` decoded correctly |

## Adding a stage

1. Add `fixtures/<name>.html`; have it set `window.__obstacle` to a deterministic
   string once its work has settled.
2. Add an entry to `manifest.json` with the `check` expression
   (`JSON.stringify(String(window.__obstacle||''))`) and the `expect` value.

The runner exits non-zero if any stage's result does not match, so it doubles as
a regression check, not just a benchmark.
