# obscura-benchmark

Conformance and performance benchmarks for [Obscura](https://github.com/h4ckf0r0day/obscura),
a headless browser engine written in Rust.

It runs the [Web Platform Tests](https://web-platform-tests.org/) against Obscura by driving its
CLI, and times `obscura fetch` / `obscura scrape`. Work in progress. Setup notes, usage, and
results will be filled in here once the suite has been run on the benchmark host.

## Layout

- `crates/wpt-runner` runs WPT against Obscura (one `obscura fetch` per test).
- `crates/triage` groups failures into deduplicated root causes.
- `crates/perf-bench` times `obscura fetch` and `obscura scrape`.
- `wpt-overlay/resources/testharnessreport.js` is the custom WPT report script.
- `scripts/` holds the setup and run wrappers.

Build with `cargo build --release` from the repo root.
