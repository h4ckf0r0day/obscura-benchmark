//! Result aggregation and output formatting.
//!
//! testharness.js status codes:
//!   harness: 0 OK, 1 ERROR, 2 TIMEOUT, 3 PRECONDITION_FAILED
//!   subtest: 0 PASS, 1 FAIL, 2 TIMEOUT, 3 NOTRUN, 4 PRECONDITION_FAILED
//! Plus two runner-side codes: -1 no result before timeout, -2 runner error.
//!
//! Every `FileResult` also carries the console output and uncaught exceptions
//! captured during the run. The `--json` output is the input contract for the
//! `triage` bug catcher, so keep the shape stable.

use serde_json::{json, Value};
use std::time::Duration;

use crate::manifest::TestCase;

pub struct Subtest {
    pub name: String,
    pub status: i64,
    pub message: Option<String>,
    pub stack: Option<String>,
}

pub struct FileResult {
    pub path: String,
    pub url: String,
    pub harness_status: i64,
    pub harness_message: Option<String>,
    pub error: Option<String>,
    pub subtests: Vec<Subtest>,
    /// Console output captured during the run (console.* and Log entries).
    pub console: Vec<String>,
    /// Uncaught exceptions captured during the run (Runtime.exceptionThrown).
    pub exceptions: Vec<String>,
    pub duration_ms: u64,
}

impl FileResult {
    pub fn from_payload(tc: &TestCase, p: Value) -> Self {
        let harness_status = p.pointer("/harness/status").and_then(Value::as_i64).unwrap_or(1);
        let harness_message = p
            .pointer("/harness/message")
            .and_then(Value::as_str)
            .map(str::to_string);
        let subtests = p
            .get("tests")
            .and_then(Value::as_array)
            .map(|arr| {
                arr.iter()
                    .map(|t| Subtest {
                        name: t.get("name").and_then(Value::as_str).unwrap_or("").to_string(),
                        status: t.get("status").and_then(Value::as_i64).unwrap_or(1),
                        message: t.get("message").and_then(Value::as_str).map(str::to_string),
                        stack: t.get("stack").and_then(Value::as_str).map(str::to_string),
                    })
                    .collect()
            })
            .unwrap_or_default();
        FileResult {
            path: tc.path.clone(),
            url: tc.url.clone(),
            harness_status,
            harness_message,
            error: None,
            subtests,
            console: Vec::new(),
            exceptions: Vec::new(),
            duration_ms: 0,
        }
    }

    pub fn timeout(tc: &TestCase) -> Self {
        Self::stub(tc, -1, "no result before timeout")
    }

    pub fn runner_error(tc: &TestCase, msg: String) -> Self {
        let mut r = Self::stub(tc, -2, "");
        r.error = Some(msg);
        r
    }

    fn stub(tc: &TestCase, harness_status: i64, err: &str) -> Self {
        FileResult {
            path: tc.path.clone(),
            url: tc.url.clone(),
            harness_status,
            harness_message: None,
            error: if err.is_empty() { None } else { Some(err.to_string()) },
            subtests: Vec::new(),
            console: Vec::new(),
            exceptions: Vec::new(),
            duration_ms: 0,
        }
    }

    pub fn pass(&self) -> usize {
        self.subtests.iter().filter(|t| t.status == 0).count()
    }
    pub fn total(&self) -> usize {
        self.subtests.len()
    }
    /// A file is "ok" when the harness completed cleanly and every subtest passed.
    pub fn ok(&self) -> bool {
        self.harness_status == 0 && self.subtests.iter().all(|t| t.status == 0)
    }

    fn tag(&self) -> &'static str {
        match self.harness_status {
            0 => {
                if self.ok() {
                    "OK  "
                } else {
                    "FAIL"
                }
            }
            -1 => "TMO ",
            -2 => "ERR ",
            1 => "HERR",
            2 => "HTMO",
            3 => "PREC",
            _ => "????",
        }
    }

    pub fn line(&self) -> String {
        format!("{} {:>4}/{:<4} {}", self.tag(), self.pass(), self.total(), self.path)
    }

    fn to_json(&self) -> Value {
        json!({
            "path": self.path,
            "url": self.url,
            "harness_status": self.harness_status,
            "harness_message": self.harness_message,
            "ok": self.ok(),
            "pass": self.pass(),
            "total": self.total(),
            "duration_ms": self.duration_ms,
            "error": self.error,
            "console": self.console,
            "exceptions": self.exceptions,
            "subtests": self.subtests.iter().map(|t| json!({
                "name": t.name,
                "status": t.status,
                "message": t.message,
                "stack": t.stack,
            })).collect::<Vec<_>>(),
        })
    }
}

pub struct Summary {
    pub files: usize,
    pub files_ok: usize,
    pub files_error: usize,
    pub subtest_pass: usize,
    pub subtest_fail: usize,
    pub subtest_total: usize,
}

pub fn summarize(results: &[FileResult]) -> Summary {
    let mut s = Summary {
        files: results.len(),
        files_ok: 0,
        files_error: 0,
        subtest_pass: 0,
        subtest_fail: 0,
        subtest_total: 0,
    };
    for r in results {
        if r.ok() {
            s.files_ok += 1;
        }
        if r.harness_status != 0 {
            s.files_error += 1;
        }
        s.subtest_pass += r.pass();
        s.subtest_total += r.total();
        s.subtest_fail += r.total() - r.pass();
    }
    s
}

pub fn print_results(results: &[FileResult], elapsed: Duration, as_json: bool) {
    let s = summarize(results);
    if as_json {
        let out = json!({
            "elapsed_ms": elapsed.as_millis() as u64,
            "summary": {
                "files": s.files,
                "files_ok": s.files_ok,
                "files_error": s.files_error,
                "subtest_pass": s.subtest_pass,
                "subtest_fail": s.subtest_fail,
                "subtest_total": s.subtest_total,
            },
            "results": results.iter().map(FileResult::to_json).collect::<Vec<_>>(),
        });
        println!("{}", serde_json::to_string_pretty(&out).unwrap());
        return;
    }

    let pct = |n: usize, d: usize| if d == 0 { 100.0 } else { n as f64 * 100.0 / d as f64 };
    eprintln!("------------------------------------------------------------");
    eprintln!(
        "files:    {}/{} ok ({:.1}%), {} with harness errors",
        s.files_ok,
        s.files,
        pct(s.files_ok, s.files),
        s.files_error
    );
    eprintln!(
        "subtests: {}/{} pass ({:.1}%), {} fail",
        s.subtest_pass,
        s.subtest_total,
        pct(s.subtest_pass, s.subtest_total),
        s.subtest_fail
    );
    eprintln!("elapsed:  {:.1}s", elapsed.as_secs_f64());
}
