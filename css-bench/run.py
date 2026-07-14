#!/usr/bin/env python3
"""Offline correctness, latency, and peak-RSS benchmark for Obscura CSS modes."""

import argparse
import json
import os
import platform
import re
import socket
import statistics
import subprocess
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORPUS = json.loads((HERE / "corpus.json").read_text())["cases"]
SYNTHETIC = [
    {"name": "synthetic-160k", "bytes": 10 * 16 * 1024},
    {"name": "synthetic-1920k", "bytes": 30 * 64 * 1024},
    {"name": "synthetic-10m", "bytes": 40 * 256 * 1024},
]
EVAL = """JSON.stringify((() => { const el=document.getElementById('probe'); let s=getComputedStyle(el); const link=document.getElementById('sheet'); const harness=document.getElementById('harness'); const result={display:s.display,custom:s.getPropertyValue('--bench-custom'),media:s.getPropertyValue('--bench-media'),sheets:document.styleSheets.length,rules:link&&link.sheet?link.sheet.cssRules.length:0,linked:!!link&&link.sheet===document.styleSheets[1],inlineNull:!harness||harness.sheet===null,dynamic:''}; if(result.rules>=49000){result.dynamic='limit';}else if(harness&&harness.sheet){try{const index=harness.sheet.insertRule('#probe { --bench-dynamic: applied }',0);result.dynamic=getComputedStyle(el).getPropertyValue('--bench-dynamic');harness.sheet.deleteRule(index);}catch(error){result.dynamic='error:'+error.name;}} return result; })())"""


def free_port():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def synthetic_css(size):
    lines, n, current_size = [], 0, 0
    while current_size < size:
        line = f".r{n}{{--v{n}:{n};display:block;color:red}}\n"
        lines.append(line)
        current_size += len(line)
        n += 1
    return "".join(lines).encode()[:size]


def fixture_html(case):
    asset = case.get("asset", f"synthetic/{case['name']}.css")
    tag = case.get("element", "div")
    classes = case.get("classes", "r0")
    return f"<!doctype html><style id='harness'>:root{{--bench-custom:locked}}@media(min-width:1000px){{#probe{{--bench-media:wide}}}}</style><link id='sheet' rel='stylesheet' href='/asset/{asset}'><{tag} id='probe' class='{classes}'>probe</{tag}>".encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/empty":
            self.respond(b"<!doctype html><div id='probe'></div>", "text/html")
            return
        if parsed.path.startswith("/case/"):
            name = parsed.path.rsplit("/", 1)[-1]
            case = next((c for c in CORPUS + SYNTHETIC if c["name"] == name), None)
            if not case:
                self.send_error(404)
                return
            self.respond(fixture_html(case), "text/html")
            return
        if parsed.path.startswith("/asset/vendor/"):
            path = (HERE / parsed.path.removeprefix("/asset/")).resolve()
            if HERE not in path.parents or not path.exists():
                self.send_error(404)
                return
            self.respond(path.read_bytes(), "text/css")
            return
        if parsed.path.startswith("/asset/synthetic/"):
            name = parsed.path.rsplit("/", 1)[-1].removesuffix(".css")
            case = next((c for c in SYNTHETIC if c["name"] == name), None)
            if not case:
                self.send_error(404)
                return
            self.respond(synthetic_css(case["bytes"]), "text/css")
            return
        self.send_error(404)

    def respond(self, body, content_type):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def time_command(command, timeout):
    if platform.system() == "Darwin":
        timed = ["/usr/bin/time", "-l"] + command
        rss_re = re.compile(r"\s*(\d+)\s+maximum resident set size")
        divisor = 1024 * 1024
    else:
        timed = ["/usr/bin/time", "-v"] + command
        rss_re = re.compile(r"Maximum resident set size \(kbytes\):\s*(\d+)")
        divisor = 1024
    started = time.perf_counter()
    try:
        proc = subprocess.run(timed, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"wall_ms": None, "rss_mb": None, "stdout": "", "ok": False, "error": "timeout"}
    wall_ms = (time.perf_counter() - started) * 1000
    match = rss_re.search(proc.stderr)
    rss_mb = int(match.group(1)) / divisor if match else None
    return {"wall_ms": wall_ms, "rss_mb": rss_mb, "stdout": proc.stdout.strip(), "ok": proc.returncode == 0, "error": proc.stderr[-500:]}


def command(binary, url, mode, baseline=False):
    prefix = [binary] if baseline else [binary, "--css-mode", mode]
    return prefix + ["fetch", url, "--allow-private-network", "--quiet", "--timeout", "30", "--wait", "0", "--eval", EVAL]


def percentile95(values):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(0.95 * len(ordered)))]


def validate(case, mode, sample):
    if not sample["ok"]:
        return False, sample["error"]
    try:
        value = json.loads(sample["stdout"])
        if isinstance(value, str):
            value = json.loads(value)
    except Exception as error:
        return False, f"invalid JSON: {error}: {sample['stdout'][:120]}"
    if not isinstance(value, dict):
        return False, f"evaluation returned {value!r}"
    if mode == "drop":
        ok = value.get("sheets") == 0 and value.get("linked") is False and value.get("inlineNull") is True
        return ok, value
    if case["name"] == "empty":
        return value.get("sheets") == 0, value
    ok = value.get("sheets") == 2 and value.get("linked") is True
    if case.get("expect_display"):
        ok = ok and value.get("display") == case["expect_display"]
    if case.get("rules") is not None:
        ok = ok and value.get("rules") == case["rules"]
    ok = ok and value.get("custom") == "locked"
    ok = ok and value.get("media") == "wide"
    if case.get("asset"):
        ok = ok and value.get("dynamic") == "applied"
    return ok, value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--filter")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    obscura = os.environ.get("OBSCURA_BIN", "obscura")
    baseline = os.environ.get("BASELINE_BIN")
    cases = [{"name": "empty", "bytes": 0}] + CORPUS + SYNTHETIC
    if args.filter:
        cases = [case for case in cases if args.filter in case["name"]]

    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    modes = ["compute", "drop"] + (["baseline"] if baseline else [])
    samples = {(case["name"], mode): [] for case in cases for mode in modes}
    checks = {}
    try:
        for case in cases:
            url = f"http://127.0.0.1:{port}/" + ("empty" if case["name"] == "empty" else f"case/{case['name']}")
            for mode in modes:
                binary = baseline if mode == "baseline" else obscura
                for _ in range(args.warmup):
                    time_command(command(binary, url, mode, mode == "baseline"), args.timeout)
            for index in range(args.runs):
                order = modes if index % 2 == 0 else list(reversed(modes))
                for mode in order:
                    binary = baseline if mode == "baseline" else obscura
                    sample = time_command(command(binary, url, mode, mode == "baseline"), args.timeout)
                    samples[(case["name"], mode)].append(sample)
            for mode in modes:
                checks[(case["name"], mode)] = validate(case, "compute" if mode == "baseline" else mode, samples[(case["name"], mode)][-1])
    finally:
        server.shutdown()

    rows = []
    empty_medians = {}
    for mode in modes:
        valid = [s["wall_ms"] for s in samples.get(("empty", mode), []) if s["wall_ms"] is not None]
        empty_medians[mode] = statistics.median(valid) if valid else None
    for case in cases:
        for mode in modes:
            data = samples[(case["name"], mode)]
            walls = [s["wall_ms"] for s in data if s["wall_ms"] is not None]
            rss = [s["rss_mb"] for s in data if s["rss_mb"] is not None]
            median = statistics.median(walls) if walls else None
            passed, detail = checks[(case["name"], mode)]
            response_bytes = len(b"<!doctype html><div id='probe'></div>") if case["name"] == "empty" else case["bytes"] + len(fixture_html(case))
            rows.append({
                "case": case["name"], "mode": mode, "bytes": case["bytes"], "pass": passed,
                "response_bytes": response_bytes,
                "median_ms": round(median, 2) if median is not None else None,
                "p95_ms": round(percentile95(walls), 2) if walls else None,
                "css_delta_ms": round(median - empty_medians[mode], 2) if median is not None and empty_medians[mode] is not None else None,
                "peak_rss_mb": round(max(rss), 2) if rss else None,
                "detail": detail,
            })
    by_case_mode = {(row["case"], row["mode"]): row for row in rows}
    performance_checks = []
    for case in cases:
        if case["bytes"] < 1024 * 1024:
            continue
        compute = by_case_mode.get((case["name"], "compute"))
        drop = by_case_mode.get((case["name"], "drop"))
        if compute and drop:
            performance_checks.append({
                "case": case["name"],
                "pass": drop["median_ms"] < compute["median_ms"] and drop["peak_rss_mb"] < compute["peak_rss_mb"],
            })
    empty_regression = None
    if baseline and ("empty", "compute") in by_case_mode and ("empty", "baseline") in by_case_mode:
        current = by_case_mode[("empty", "compute")]["median_ms"]
        previous = by_case_mode[("empty", "baseline")]["median_ms"]
        empty_regression = {"pass": current <= previous * 1.10, "current_ms": current, "baseline_ms": previous}
    result = {"runs": args.runs, "warmup": args.warmup, "binary": obscura, "baseline": baseline,
              "performance_checks": performance_checks, "empty_regression": empty_regression, "results": rows}
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"css bench: {args.runs} runs, {args.warmup} warmups | {obscura}")
        print(f"{'case':<20}{'mode':<10}{'ok':<5}{'median':>10}{'css delta':>12}{'p95':>10}{'peak MB':>10}{'resp MB':>10}")
        print("-" * 87)
        for row in rows:
            print(f"{row['case']:<20}{row['mode']:<10}{('yes' if row['pass'] else 'NO'):<5}{row['median_ms'] or 0:>9.2f} {row['css_delta_ms'] or 0:>10.2f} {row['p95_ms'] or 0:>9.2f} {row['peak_rss_mb'] or 0:>9.2f} {row['response_bytes'] / 1024 / 1024:>9.2f}")
        failures = [row for row in rows if not row["pass"]]
        if failures:
            print("\ncorrectness failures:")
            for row in failures:
                print(f"  {row['case']} {row['mode']}: {row['detail']}")
    accepted = all(row["pass"] for row in rows) and all(check["pass"] for check in performance_checks)
    if empty_regression is not None:
        accepted = accepted and empty_regression["pass"]
    sys.exit(0 if accepted else 1)


if __name__ == "__main__":
    main()
