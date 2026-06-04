#!/usr/bin/env python3
"""Obscura obstacle course runner.

Serves obstacle-course/ over a local HTTP origin, drives `obscura fetch` against
each fixture, and reports per-stage correctness (does the JS-rendered DOM match
the expected value) plus latency (warmup + timed runs, min/median).

obscura blocks private/loopback IPs by default, so fetches pass
--allow-private-network (same as the WPT runner).

Usage:
  OBSCURA_BIN=/path/to/obscura python3 run.py [--json] [--port N] [--runs N] [--warmup N]
"""
import argparse, json, os, socket, statistics, subprocess, sys, threading, time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def fetch(obscura_bin, url, check, wait_secs, timeout_secs):
    """Run one `obscura fetch`, returning (wall_ms, decoded_result_or_None)."""
    t0 = time.time()
    try:
        proc = subprocess.run(
            [obscura_bin, "fetch", url, "--allow-private-network", "--quiet",
             "--timeout", str(timeout_secs), "--wait", str(wait_secs), "--eval", check],
            capture_output=True, text=True, timeout=timeout_secs + 15,
        )
    except subprocess.TimeoutExpired:
        return (time.time() - t0) * 1000.0, None
    wall = (time.time() - t0) * 1000.0
    out = proc.stdout.strip()
    try:
        return wall, json.loads(out)  # check wraps result in JSON.stringify(...)
    except Exception:
        return wall, out or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--runs", type=int)
    ap.add_argument("--warmup", type=int)
    ap.add_argument("--filter", help="only run stages whose name contains this")
    args = ap.parse_args()

    obscura_bin = os.environ.get("OBSCURA_BIN", "obscura")
    manifest = json.load(open(os.path.join(HERE, "manifest.json")))
    runs = args.runs if args.runs is not None else manifest.get("runs", 5)
    warmup = args.warmup if args.warmup is not None else manifest.get("warmup", 1)
    wait_secs = manifest.get("wait_secs", 3)
    timeout_secs = manifest.get("timeout_secs", 20)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=HERE, **k)
        def log_message(self, *a, **k):
            pass  # silence per-request access logs

    port = args.port or free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    stages = manifest["stages"]
    if args.filter:
        stages = [s for s in stages if args.filter in s["name"]]

    results = []
    if not args.json:
        print(f"obstacle course: {len(stages)} stages, {runs} runs (warmup {warmup}), "
              f"wait {wait_secs}s, bin {obscura_bin}\n")
        print(f"{'stage':<16}{'result':<8}{'min ms':>9}{'median ms':>11}   detail")
        print("-" * 72)

    ok_count = 0
    for st in stages:
        url = f"{base}/{st['file']}"
        for _ in range(warmup):
            fetch(obscura_bin, url, st["check"], wait_secs, timeout_secs)
        times, last = [], None
        for _ in range(runs):
            wall, res = fetch(obscura_bin, url, st["check"], wait_secs, timeout_secs)
            times.append(wall)
            last = res
        passed = (last == st["expect"])
        ok_count += 1 if passed else 0
        rec = {
            "name": st["name"], "pass": passed, "expect": st["expect"], "got": last,
            "min_ms": round(min(times), 1), "median_ms": round(statistics.median(times), 1),
            "desc": st.get("desc", ""),
        }
        results.append(rec)
        if not args.json:
            tag = "PASS" if passed else "FAIL"
            detail = st["desc"] if passed else f"expected {st['expect']!r}, got {last!r}"
            print(f"{st['name']:<16}{tag:<8}{rec['min_ms']:>9}{rec['median_ms']:>11}   {detail}")

    server.shutdown()
    summary = {"stages": len(stages), "passed": ok_count, "results": results}
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("-" * 72)
        print(f"correctness: {ok_count}/{len(stages)} stages passed")
    sys.exit(0 if ok_count == len(stages) else 1)


if __name__ == "__main__":
    main()
