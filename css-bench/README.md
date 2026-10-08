# CSS processing benchmark

This offline track measures Obscura's lightweight CSS computation and explicit
fetch-and-discard mode. It combines deterministic synthetic scaling inputs with
4.77 MB of pinned production CSS from Bootstrap, Bulma's documentation site,
Primer, and PatternFly.

The production artifacts are MIT-licensed, committed with their license files,
and locked by byte size and SHA-256 in `vendor.lock.json`. They never update
implicitly:

```sh
python3 css-bench/update_vendor.py            # verify the checkout
python3 css-bench/update_vendor.py --refresh  # explicitly fetch pinned bytes
```

Run the benchmark against a release binary on an otherwise idle host:

```sh
OBSCURA_BIN=/path/to/obscura python3 css-bench/run.py
OBSCURA_BIN=/path/to/obscura BASELINE_BIN=/path/to/old-obscura \
  python3 css-bench/run.py --json > results/css-bench.json
```

The runner serves everything from loopback, checks computed styles and CSSOM,
then reports cold-process median/p95 latency, CSS-over-empty latency, and peak
RSS. It uses `/usr/bin/time -l` on macOS and GNU `time -v` on Linux. Correctness
is gating; timing is reported rather than treated as a portable CI threshold.

Historical synthetic reference from the optimization experiment (10 MiB): the
retained-body path took 55.37 ms and 91.58 MiB peak RSS, while fetch-and-discard
took 21.99 ms and 34.45 MiB. These figures are context, not a cross-host gate.
