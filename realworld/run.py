#!/usr/bin/env python3
"""Real-world render-success benchmark.

Fetches each URL in sites.txt with obscura, runs its JavaScript to settle, and
reports whether obscura produced a usable rendered document (HTTP ok, a non
trivial serialized DOM, and a readable <title>), plus per-page latency and peak
memory. This measures "does obscura handle the real web", not synthetic fixtures.

A page counts as rendered when obscura exits cleanly with a document larger than
a small floor and a non-empty <title>. SPAs in the list only pass if their
client-side JavaScript actually ran (their shipped HTML is near-empty).

The live web drifts and some sites rate-limit or block automation, so the
success rate and timings are a snapshot, not a fixed score.

Usage:
  OBSCURA_BIN=/path/to/obscura python3 run.py [--wait S] [--sites FILE] [--json]
"""
import argparse, json, os, re, statistics, subprocess, time

HERE = os.path.dirname(os.path.abspath(__file__))
OBSCURA = os.environ.get("OBSCURA_BIN", "obscura")
GNU_TIME = "/usr/bin/time"
_RSS = re.compile(r"Maximum resident set size \(kbytes\): (\d+)")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)
MIN_DOC = 512  # bytes of serialized DOM below which we treat the page as not rendered


def load_sites(path):
    out = []
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    return out


def fetch(url, wait):
    cmd = [GNU_TIME, "-v", OBSCURA, "fetch", url, "--quiet", "--timeout", "30",
           "--wait", str(int(round(wait))), "--dump", "html"]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return {"ok": False, "ms": 60000, "rss_mb": None, "title": "", "bytes": 0, "why": "timeout"}
    ms = (time.time() - t0) * 1000.0
    m = _RSS.search(p.stderr); rss = (int(m.group(1)) / 1024.0) if m else None
    html = p.stdout
    tm = _TITLE.search(html); title = re.sub(r"\s+", " ", tm.group(1)).strip()[:60] if tm else ""
    ok = p.returncode == 0 and len(html) >= MIN_DOC and bool(title)
    why = "" if ok else ("exit %d" % p.returncode if p.returncode else ("empty" if len(html) < MIN_DOC else "no title"))
    return {"ok": ok, "ms": ms, "rss_mb": rss, "title": title, "bytes": len(html), "why": why}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wait", type=float, default=4.0)
    ap.add_argument("--sites", default=os.path.join(HERE, "sites.txt"))
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    sites = load_sites(args.sites)
    rows = []
    if not args.json:
        print(f"real-world render-success  |  {len(sites)} pages, obscura fetch --dump html, wait {args.wait}s")
        print(f"  obscura: {OBSCURA}\n")
        print(f"{'result':<8}{'ms':>7}{'RSS MB':>8}{'KB':>7}  {'url':<42}{'title / why'}")
        print("-" * 100)
    for url in sites:
        r = fetch(url, args.wait)
        rows.append({"url": url, **r})
        if not args.json:
            tag = "OK" if r["ok"] else "FAIL"
            detail = r["title"] if r["ok"] else r["why"]
            print(f"{tag:<8}{r['ms']:>7.0f}{(r['rss_mb'] or 0):>8.0f}{r['bytes'] / 1024:>7.0f}  {url[:42]:<42}{detail}")

    ok = [r for r in rows if r["ok"]]
    lat = [r["ms"] for r in ok]
    rss = [r["rss_mb"] for r in ok if r["rss_mb"]]
    summary = {
        "pages": len(rows),
        "rendered_ok": len(ok),
        "success_rate": round(100 * len(ok) / max(len(rows), 1), 1),
        "median_latency_ms": round(statistics.median(lat), 1) if lat else None,
        "median_rss_mb": round(statistics.median(rss), 1) if rss else None,
        "results": rows,
    }
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("-" * 100)
        print(f"rendered {summary['rendered_ok']}/{summary['pages']} pages "
              f"({summary['success_rate']}%)  |  median {summary['median_latency_ms']}ms, "
              f"{summary['median_rss_mb']}MB peak RSS")


if __name__ == "__main__":
    main()
