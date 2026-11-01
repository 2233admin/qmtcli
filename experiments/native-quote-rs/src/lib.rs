//! Experimental read-only MiniQMT client. Not an official or complete QMT SDK.

use bson::{Bson, Document, doc};
use sha2::{Digest, Sha256};
use std::{
    io::{self, Read, Write},
    net::{Ipv4Addr, SocketAddr, TcpStream},
    path::PathBuf,
    time::{Duration, Instant},
};

#[cfg(test)]
mod session_tests;
mod wire;
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

// Temporary experiment profile mirrors qmtcli.native_quote.PROFILES.
const PROFILE: [(&str, &str); 5] = [
    (
        "miniquote.exe",
        "1bfd04220c7635d22ae81a2e70e40c09cb7192aa51ba90c1e6b6ec1859c76ade",
    ),
    (
        "QuoteCenter_mini.dll",
        "a2154c07b097aa7daf8b8f9528f4f039135d585a4968ae5b4f1e2315afd02925",
    ),
    (
        "quoter.dll",
        "e1cc4b1819b2c9d9490ef83e0e906e680f45c8fa6bb314a350373196e22f1015",
    ),
    (
        "net.dll",
        "2cd891348d3f504e342b71109fc8753a3ca261bb7658f7105a6cee31c6a91aff",
    ),
    (
        "utils.dll",
        "fa55c69e4d8a0b449894dcf8bf767dd03e2c0cdc6b33727e0530445950fd14a8",
    ),
];

/// Pinned runtime configuration. Connect explicitly to retain an owned socket.
pub struct QuoteClient {
    root: PathBuf,
    port: u16,
    timeout: Duration,
}

impl QuoteClient {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        Self {
            root: root.into(),
            port: 58610,
            timeout: Duration::from_secs(5),
        }
    }

    pub fn with_port(mut self, port: u16) -> Self {
        self.port = port;
        self
    }

    pub fn with_timeout(mut self, timeout: Duration) -> Self {
        self.timeout = timeout;
        self
    }

    /// Official business shape: code_list -> document keyed by security code.
    /// Preserves cached timestamps and numeric BSON types, including Int64.
    pub fn get_full_tick(&self, code_list: &[&str]) -> Result<Document> {
        validate_symbols(code_list)?;
        self.connect()?.get_full_tick(code_list)
    }

    /// Validate the runtime and authenticate once. Never reconnects implicitly.
    pub fn connect(&self) -> Result<QuoteSession> {
        if self.port == 0
            || !(Duration::from_millis(100)..=Duration::from_secs(60)).contains(&self.timeout)
        {
            return Err("invalid port/timeout: budget must be 0.1 to 60 seconds".into());
        }
        self.validate_runtime()?;
        let deadline = Instant::now() + self.timeout;
        let address = SocketAddr::from((Ipv4Addr::LOCALHOST, self.port));
        let stream = TcpStream::connect_timeout(&address, remaining(deadline)?)?;
        QuoteSession::authenticate(stream, self.timeout, deadline)
    }

    fn validate_runtime(&self) -> Result<()> {
        if !cfg!(all(windows, target_pointer_width = "64")) {
            return Err("native quote experiment requires Windows x64".into());
        }
        let root = if self.root.file_name().is_some_and(|n| n == "userdata_mini") {
            self.root
                .parent()
                .ok_or("invalid MiniQMT path")?
                .to_path_buf()
        } else {
            self.root.clone()
        };
        if !root.join("userdata_mini").is_dir() {
            return Err("requires existing MiniQMT root or userdata_mini path".into());
        }
        for (name, expected) in PROFILE {
            let bytes = std::fs::read(root.join("bin.x64").join(name))?;
            let actual: String = Sha256::digest(bytes)
                .iter()
                .map(|byte| format!("{byte:02x}"))
                .collect();
            if actual != expected {
                return Err(
                    format!("unsupported MiniQMT runtime: {name} fingerprint mismatch").into(),
                );
            }
        }
        Ok(())
    }
}

/// Single-owner read session. A failed wire/result invalidates the connection;
/// callers must use QuoteClient::connect again. Drop releases the socket.
pub struct QuoteSession {
    stream: Option<TcpStream>,
    timeout: Duration,
    sequence: u32,
}

impl QuoteSession {
    fn authenticate(mut stream: TcpStream, timeout: Duration, deadline: Instant) -> Result<Self> {
        let mut io = DeadlineStream {
            stream: &mut stream,
            deadline,
        };
        let auth = wire::request(
            &mut io,
            1,
            "authPid",
            doc! { "pid": std::process::id() as i32 },
        )?;
        if !matches!(auth.get_bool("success"), Ok(true)) {
            return Err("normal caller-PID authentication rejected".into());
        }
        Ok(Self {
            stream: Some(stream),
            timeout,
            sequence: 1,
        })
    }

    /// Fresh request/response on the retained socket; no quote-result cache.
    pub fn get_full_tick(&mut self, code_list: &[&str]) -> Result<Document> {
        validate_symbols(code_list)?;
        let result = self.query(code_list);
        if result.is_err() {
            drop(self.stream.take());
        }
        result
    }

    fn query(&mut self, code_list: &[&str]) -> Result<Document> {
        let stream = self
            .stream
            .as_mut()
            .ok_or("quote session closed; connect a new session")?;
        self.sequence = self
            .sequence
            .checked_add(1)
            .ok_or("quote sequence exhausted; connect a new session")?;
        let mut io = DeadlineStream {
            stream,
            deadline: Instant::now() + self.timeout,
        };
        let symbols = code_list
            .iter()
            .map(|s| Bson::String((*s).into()))
            .collect::<Vec<_>>();
        let reply = wire::request(
            &mut io,
            self.sequence,
            "getFullTick",
            doc! { "stockMarkets": symbols },
        )?;
        let result = reply.get_document("result")?;
        if result
            .iter()
            .any(|(key, value)| !selected(key, code_list) || !matches!(value, Bson::Document(_)))
        {
            return Err("invalid full-tick symbol mapping".into());
        }
        Ok(result.clone())
    }
}

fn validate_symbols(symbols: &[&str]) -> Result<()> {
    if symbols.is_empty()
        || symbols.len() > 1000
        || symbols
            .iter()
            .any(|s| s.is_empty() || s.len() > 64 || !s.bytes().all(|b| b.is_ascii_graphic()))
    {
        return Err("requires 1 to 1000 nonempty ASCII symbols, max 64 bytes each".into());
    }
    Ok(())
}

fn selected(code: &str, selectors: &[&str]) -> bool {
    selectors.iter().any(|selector| {
        *selector == code
            || (!selector.contains('.')
                && code
                    .rsplit_once('.')
                    .is_some_and(|(stock, market)| !stock.is_empty() && market == *selector))
    })
}

fn remaining(deadline: Instant) -> io::Result<Duration> {
    deadline
        .checked_duration_since(Instant::now())
        .filter(|d| !d.is_zero())
        .ok_or_else(|| io::Error::new(io::ErrorKind::TimedOut, "native quote deadline exceeded"))
}

struct DeadlineStream<'a> {
    stream: &'a mut TcpStream,
    deadline: Instant,
}

impl Read for DeadlineStream<'_> {
    fn read(&mut self, buf: &mut [u8]) -> io::Result<usize> {
        self.stream
            .set_read_timeout(Some(remaining(self.deadline)?))?;
        self.stream.read(buf)
    }
}

impl Write for DeadlineStream<'_> {
    fn write(&mut self, buf: &[u8]) -> io::Result<usize> {
        self.stream
            .set_write_timeout(Some(remaining(self.deadline)?))?;
        self.stream.write(buf)
    }
    fn flush(&mut self) -> io::Result<()> {
        self.stream.flush()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn symbols_are_validated_before_runtime_or_network_access() {
        let client = QuoteClient::new("missing");
        for symbols in [vec![], vec!["bad\0symbol"], vec!["中文"], vec![" "]] {
            assert!(
                client
                    .get_full_tick(&symbols)
                    .unwrap_err()
                    .to_string()
                    .contains("symbols")
            );
        }
    }

    #[test]
    fn crc_matches_native_and_python_vectors() {
        assert_eq!(wire::crc(b""), 0xffff_ffff);
        assert_eq!(wire::crc(b"123456789"), 0xd202_d277);
    }

    #[test]
    fn official_market_selectors_accept_only_matching_market() {
        assert!(selected("600000.SH", &["SH", "SZ"]));
        assert!(selected("000001.SZ", &["600000.SH", "SZ"]));
        assert!(!selected("600000.SH", &["SZ"]));
        assert!(!selected("000001.SZ", &["600000.SH"]));
        assert!(!selected(".SH", &["SH"]));
    }

    #[test]
    fn invalid_budgets_and_expired_deadline_fail_before_io() {
        for client in [
            QuoteClient::new("missing").with_port(0),
            QuoteClient::new("missing").with_timeout(Duration::ZERO),
            QuoteClient::new("missing").with_timeout(Duration::from_secs(61)),
        ] {
            assert!(
                client
                    .get_full_tick(&["600000.SH"])
                    .unwrap_err()
                    .to_string()
                    .contains("port/timeout")
            );
        }
        assert_eq!(
            remaining(Instant::now() - Duration::from_secs(1))
                .unwrap_err()
                .kind(),
            io::ErrorKind::TimedOut
        );
    }

    #[test]
    fn request_uses_named_bson_array_and_int32_caller_pid() {
        let frame = wire::encode(
            1,
            "authPid",
            bson::doc! { "pid": std::process::id() as i32 },
        )
        .unwrap();
        let mut compressed = flate2::read::ZlibDecoder::new(&frame[12..]);
        let mut decoded = Vec::new();
        std::io::Read::read_to_end(&mut compressed, &mut decoded).unwrap();
        assert_eq!(&decoded[22..30], b"\x04params\0");
        // Restore the document tag so the standard codec preserves the named key.
        decoded[22] = 3;
        let doc = bson::Document::from_reader(&mut &decoded[..]).unwrap();
        assert_eq!(
            doc.get_document("params").unwrap().get_i32("pid").unwrap(),
            std::process::id() as i32
        );
        assert!(wire::encode(1, "authPid", bson::doc! { "pid": -1 }).is_err());
        assert!(wire::encode(1, "supplyHistoryData2", bson::doc! {}).is_err());
    }
}
