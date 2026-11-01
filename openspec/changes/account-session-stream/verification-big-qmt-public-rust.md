# Big QMT public reads — Rust 0.3.0

Scope: instrument-detail, latest unadjusted daily OHLCV/amount bars and cached
full-tick through explicit backend=formula. All are public read-only formula RPC;
no account queries, strategy starts, order actions or client configuration changes.

## Evidence observed on 2026-11-02

- `cargo test --release --offline --locked --workspace --all-targets`: exit 0;
  54 passed, 1 ignored internal child entry. Includes MiniQMT's existing tests,
  nine formula tests and two additional CLI contract tests.
- `cargo clippy --release --offline --locked --workspace --all-targets -- -D warnings`:
  exit 0. Initial constant-size chunks lint corrected to `as_chunks::<2>()`.
- `cargo build --release --offline --locked -p qmtcli-rs`: exit 0.
- `ruff check .` using existing main-checkout venv executable: exit 0.
  Python production code was not changed; this slice did not rerun Python pytest.
- `experiments/accept_big_qmt_public.py` against the packaged `dist/rust/qmtcli-rs.exe`
  and the already running installed Big QMT: exit 0, 10 JSONL requests checked,
  correct identity/data/metadata, invalid count rejected, healthy session retained,
  subsequent snapshot succeeds, normal EOF exit. Child PATH contains System32 only.
- Installed jsonschema 4.26.0 validates discovery schema, examples and actual
  requests; invalid count and native daily-bars rejected by schema.
- PE imports from llvm-readobj are Windows system DLLs, with no Python/Qt/broker
  runtime import. Formula DLLs are fingerprinted files, never loaded by this route.
- Final exe SHA-256: `236e39e7fc773edd2b01569c3c176cc85467aacc1c314ad04e4f1806cb83ffe6`.

Two-stock observations: daily dates 20260731/20260803 with all six requested
fields; snapshot times 20260521 15:00:00 / 15:00:04. These are **old client cache**,
not evidence of today's data. Every formula result labels unknown freshness and
separates retrieval time from source time. No live subscriptions or download API.

## Negative controls and correction

The same acceptance script against preserved 0.2.0 exits 1, passed=false: missing
formula backend cannot pass acceptance. The initial 0.3.0 actual-entry run also
exited 1: `read_to_string` rejected the installed INI's legacy-encoded comments.
A focused regression test first failed with Utf8Error, then passed after limiting
INI interpretation to its ASCII section/key/port syntax; non-ASCII port still
fails. The initial feature tests were not demonstrated red before implementation;
the old-package acceptance negative control and the encoding regression provide
the observed failure checks. Do not describe this entire slice as strict TDD.

Raw local receipts (outside Git):
`F:\projects\_research\qmt-ida-20261031\recovery\big-qmt\formula-path\`:
`daily-ohlcv-control.json`, `qmtcli-0.2-negative-control.json`,
`qmtcli-0.3-config-encoding-failed.json`, `qmtcli-0.3-tests.log`,
`qmtcli-0.3-clippy.log`. Successful public-data receipt, release checksums and
the structural gate pointer are distributed with the local package in dist/rust.

## Reproduction and limits

Code Intel `--mode normal` was stopped after over nine minutes without a result
from `provider.codenexus-adapt`. Snapshot and doctor completed; structural verdict
is **unverified**, not pass. Its source snapshot was
`816ef04bb3625e04643918e71dd61d1908ca470efd293c0ab9a3f43bd53eec9b`;
the partial artifact directory and elapsed time are recorded in the packaged
`structural-gate.json`. No provider cause was established. Bounded source review,
the actual-entry checks and the independent Rust/Clippy/schema checks above are
the completed evidence; this does not claim a completed Code Intel gate.

Use Rust 1.99.1 GNU with the matching explicit RUSTC/RUSTDOC paths. On this host,
prepend the existing private LLVM dlltool directory and LLVM/bin to PATH. Reuse
the release target cache; no global Cargo configuration was changed. An initial
debug build was stopped after a compile error and slow dependency generation;
an extra uv environment install was stopped and the existing Ruff executable
used. The cause of slow Cargo startup was not established; overriding cache
cleanup is not proven to be its fix. KB recall ran in degraded lexical mode with
no hits; work KB registration was missing, so no new domain or global policy was
invented. The reproducible build/acceptance contract remains here and rust/README.

Big QMT process 97984 remained responsive during acceptance. Only owned CLI/build
processes were started/stopped. This slice does not complete the wider account,
subscription, auction-data or clean-machine acceptance work; parent OpenSpec
remains in_review.
