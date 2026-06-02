//! Enumerate testharness tests from a WPT `MANIFEST.json`.
//!
//! The manifest stores tests under `items.testharness` as a nested directory
//! tree of JSON objects. A leaf is a JSON array shaped like
//! `[hash, [url_or_null, options], ...]` where each `[url, options]` pair is a
//! runnable variant. A null url means "use the file path as the url".

use anyhow::{Context, Result};
use serde_json::Value;
use std::fs;
use std::path::Path;

#[derive(Clone)]
pub struct TestCase {
    /// File path inside the manifest, e.g. `dom/nodes/Node-childNodes.html`.
    pub path: String,
    /// Fully qualified URL to navigate to.
    pub url: String,
}

pub struct UrlBuilder {
    pub host: String,
    pub http_port: u16,
    pub https_port: u16,
}

impl UrlBuilder {
    fn build(&self, url_path: &str, file_path: &str) -> String {
        // WPT marks tests that must run over TLS with `.https.` (and a few
        // related markers) in the file name. Everything else runs over http.
        let https = file_path.contains(".https.") || file_path.contains(".serviceworker.");
        let path = if url_path.starts_with('/') {
            url_path.to_string()
        } else {
            format!("/{url_path}")
        };
        if https {
            format!("https://{}:{}{}", self.host, self.https_port, path)
        } else {
            format!("http://{}:{}{}", self.host, self.http_port, path)
        }
    }
}

pub fn load_tests(manifest_path: &Path, base: &UrlBuilder, filter: Option<&str>) -> Result<Vec<TestCase>> {
    let data = fs::read_to_string(manifest_path)
        .with_context(|| format!("read {}", manifest_path.display()))?;
    let v: Value = serde_json::from_str(&data).context("parse MANIFEST.json")?;
    let mut out = Vec::new();
    if let Some(th) = v.pointer("/items/testharness") {
        let mut prefix = String::new();
        walk(th, &mut prefix, base, &mut out);
    }
    if let Some(f) = filter {
        out.retain(|t| t.path.contains(f));
    }
    out.sort_by(|a, b| a.path.cmp(&b.path));
    out.dedup_by(|a, b| a.url == b.url);
    Ok(out)
}

fn walk(node: &Value, prefix: &mut String, base: &UrlBuilder, out: &mut Vec<TestCase>) {
    match node {
        Value::Object(map) => {
            for (key, child) in map {
                let saved = prefix.len();
                if !prefix.is_empty() {
                    prefix.push('/');
                }
                prefix.push_str(key);
                walk(child, prefix, base, out);
                prefix.truncate(saved);
            }
        }
        Value::Array(variants) => {
            let file_path = prefix.clone();
            // Skip variants[0] (the content hash); the rest are runnable.
            for variant in variants.iter().skip(1) {
                let url_path = match variant.as_array().and_then(|a| a.first()) {
                    Some(Value::String(s)) => s.clone(),
                    _ => format!("/{file_path}"),
                };
                out.push(TestCase {
                    path: file_path.clone(),
                    url: base.build(&url_path, &file_path),
                });
            }
        }
        _ => {}
    }
}
