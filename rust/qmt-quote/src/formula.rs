//! Read-only Big QMT formula service, separate from the MiniQMT wire profile.
use crate::{DeadlineStream, Result, remaining};
use bson::{Bson, Document, doc};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{
    collections::HashSet,
    io::{Cursor, Read, Write},
    net::{Ipv4Addr, SocketAddr, TcpStream},
    path::Path,
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

pub const MAX_FRAME: usize = 4 * 1024 * 1024;
pub const MAX_SYMBOLS: usize = 100;
pub const MAX_COUNT: u64 = 1000;
const DAILY_FIELDS: &[&str] = &["open", "high", "low", "close", "volume", "amount"];

#[derive(Clone, Copy)]
pub enum ReadKind {
    Instrument,
    Daily,
    Snapshot,
}

/// Only these business requests can reach the socket; no arbitrary method adapter.
pub struct PublicRead {
    kind: ReadKind,
    symbols: Vec<String>,
    count: u64,
}
impl PublicRead {
    pub fn new(kind: ReadKind, symbols: Vec<String>, count: u64) -> Result<Self> {
        let mut seen = HashSet::new();
        if symbols.is_empty()
            || symbols.len() > MAX_SYMBOLS
            || symbols.iter().any(|s| {
                !s.rsplit_once('.').is_some_and(|(code, market)| {
                    !code.is_empty()
                        && code.len() <= 24
                        && code.bytes().all(|b| b.is_ascii_alphanumeric())
                        && matches!(market, "SH" | "SZ" | "BJ")
                }) || !seen.insert(s)
            })
        {
            return Err("formula symbols require 1..100 unique CODE.SH/SZ/BJ identifiers".into());
        }
        if matches!(kind, ReadKind::Instrument) && symbols.len() != 1 {
            return Err("instrument-detail requires exactly one symbol".into());
        }
        if !(1..=MAX_COUNT).contains(&count) {
            return Err("count must be 1 to 1000".into());
        }
        if !matches!(kind, ReadKind::Daily) && count != 1 {
            return Err("count must be 1 for instrument-detail/full-tick".into());
        }
        Ok(Self {
            kind,
            symbols,
            count,
        })
    }
    fn request(&self) -> (&'static str, Document) {
        match self.kind {
            ReadKind::Instrument => (
                "getInstrumentDetail",
                doc! {"strOptionCode":&self.symbols[0]},
            ),
            ReadKind::Daily | ReadKind::Snapshot => {
                let snapshot = matches!(self.kind, ReadKind::Snapshot);
                // Named params follow installed qmt_api.api.get_market_data, not Mini's array tag.
                (
                    "getMarketData",
                    doc! {"fields":if snapshot {vec!["quoter"]} else {DAILY_FIELDS.to_vec()},"stockCodes":self.symbols.clone(),"startTime":"","endTime":"","period":if snapshot {"tick"} else {"1d"},"dividendType":"none","count":if snapshot {1} else {self.count as i32}},
                )
            }
        }
    }
    fn normalize(&self, result: &Bson) -> Result<Value> {
        let data = match self.kind {
            ReadKind::Instrument => {
                let d = result
                    .as_document()
                    .ok_or("instrument result must be a document")?;
                let (code, market) = self.symbols[0].rsplit_once('.').ok_or("invalid symbol")?;
                if d.get_str("InstrumentID")? != code || d.get_str("ExchangeID")? != market {
                    return Err("instrument result identity mismatch".into());
                }
                json!({"symbol":self.symbols[0],"instrument":result.clone().into_relaxed_extjson()})
            }
            _ => normalize_market(
                result,
                &self.symbols,
                self.count,
                matches!(self.kind, ReadKind::Snapshot),
            )?,
        };
        Ok(
            json!({"meta":{"backend":"formula","source":"client-cache","realtime":false,"freshness":"unknown","retrieved_at_unix_ms":SystemTime::now().duration_since(UNIX_EPOCH)?.as_millis() as u64,"period":match self.kind {ReadKind::Instrument=>"instrument",ReadKind::Daily=>"1d",ReadKind::Snapshot=>"tick"},"dividend_type":"none"},"data":data}),
        )
    }
}

/// Validate only the DLLs owning this public route; does not load any vendor DLL.
pub fn endpoint(root: &Path) -> Result<u16> {
    for (name, expected) in [
        (
            "FormulaLib.dll",
            "f03054d4441bc1bd398b4e7569df2d5afcc2bd360d2ea8676ac17fa3ba4ff088",
        ),
        (
            "net.dll",
            "2cd891348d3f504e342b71109fc8753a3ca261bb7658f7105a6cee31c6a91aff",
        ),
    ] {
        let hash: String = Sha256::digest(std::fs::read(root.join("bin.x64").join(name))?)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        if hash != expected {
            return Err(format!("unsupported formula runtime: {name} fingerprint mismatch").into());
        }
    }
    let config = std::fs::read(root.join("config/formulaserver/formulaserver.ini"))?;
    parse_port_bytes(&config)
}

fn parse_port_bytes(config: &[u8]) -> Result<u16> {
    // Only ASCII section/key/port syntax is consumed. Vendor comments may be GBK.
    parse_port(&String::from_utf8_lossy(config))
}

fn parse_port(config: &str) -> Result<u16> {
    let mut section = false;
    let mut port = None;
    for line in config.lines().map(str::trim) {
        if line.starts_with('[') {
            section = line == "[server_formula]";
        } else if section
            && let Some((key, value)) = line.split_once('=')
            && key.trim() == "address"
        {
            if port.is_some() {
                return Err("duplicate formula address".into());
            }
            port = Some(
                value
                    .trim()
                    .rsplit_once(':')
                    .ok_or("invalid formula address")?
                    .1
                    .parse::<u16>()?,
            );
        }
    }
    port.filter(|p| *p != 0)
        .ok_or_else(|| "missing valid server_formula address".into())
}

pub struct FormulaSession {
    stream: Option<TcpStream>,
    timeout: Duration,
    sequence: u32,
}
impl FormulaSession {
    /// Uses the pinned installation's formula address port, always on loopback.
    pub fn connect(root: &Path, timeout: Duration) -> Result<Self> {
        if !(Duration::from_millis(100)..=Duration::from_secs(60)).contains(&timeout) {
            return Err("invalid formula timeout".into());
        }
        let port = endpoint(root)?;
        let deadline = Instant::now() + timeout;
        let stream = TcpStream::connect_timeout(
            &SocketAddr::from((Ipv4Addr::LOCALHOST, port)),
            remaining(deadline)?,
        )?;
        Ok(Self {
            stream: Some(stream),
            timeout,
            sequence: 0,
        })
    }
    /// Retains the socket on success. Wire/result errors close it; never replays.
    pub fn read(&mut self, query: &PublicRead) -> Result<Value> {
        let result = (|| {
            self.sequence = self
                .sequence
                .checked_add(1)
                .ok_or("formula sequence exhausted")?;
            let (method, params) = query.request();
            let body = doc! {"func":method,"params":params}.to_vec()?;
            let mut frame = Vec::with_capacity(12 + body.len());
            frame.extend(((12 + body.len()) as u32).to_be_bytes());
            frame.extend(self.sequence.to_be_bytes());
            frame.extend(3u16.to_be_bytes());
            frame.extend(0u16.to_be_bytes());
            frame.extend(body);
            let mut io = DeadlineStream {
                stream: self.stream.as_mut().ok_or("formula session disconnected")?,
                deadline: Instant::now() + self.timeout,
            };
            io.write_all(&frame)?;
            let mut header = [0; 12];
            io.read_exact(&mut header)?;
            let size = u32::from_be_bytes(header[..4].try_into()?) as usize;
            if !(17..=MAX_FRAME).contains(&size) {
                return Err("invalid formula frame length".into());
            }
            let mut response = header.to_vec();
            response.resize(size, 0);
            io.read_exact(&mut response[12..])?;
            query.normalize(&decode(&response, self.sequence)?)
        })();
        if result.is_err() {
            self.stream = None;
        }
        result
    }
}

fn decode(frame: &[u8], sequence: u32) -> Result<Bson> {
    if frame.len() < 17
        || frame.len() > MAX_FRAME
        || u32::from_be_bytes(frame[..4].try_into()?) as usize != frame.len()
        || u32::from_be_bytes(frame[4..8].try_into()?) != sequence
    {
        return Err("formula length/sequence mismatch".into());
    }
    if frame[8..12] != [0, 3, 0, 0x40] {
        return Err("unsupported formula frame; only plain BSON replies supported".into());
    }
    let mut cursor = Cursor::new(&frame[12..]);
    let reply = Document::from_reader(&mut cursor)?;
    if cursor.position() != (frame.len() - 12) as u64 {
        return Err("trailing formula BSON bytes".into());
    }
    if !matches!(reply.get("status"), Some(Bson::Int32(0) | Bson::Int64(0))) {
        return Err("formula service rejected request".into());
    }
    let params = reply.get_document("params")?;
    if !matches!(params.get("last"), None | Some(Bson::Boolean(true))) {
        return Err("incomplete or invalid formula result stream".into());
    }
    params
        .get("result")
        .cloned()
        .ok_or_else(|| "formula result missing".into())
}

fn normalize_market(
    result: &Bson,
    symbols: &[String],
    count: u64,
    snapshot: bool,
) -> Result<Value> {
    let flat = result.as_array().ok_or("market result must be an array")?;
    if flat.len() % 2 != 0 {
        return Err("unpaired market symbols".into());
    }
    let mut output = serde_json::Map::new();
    for pair in flat.as_chunks::<2>().0 {
        let symbol = pair[0].as_str().ok_or("market symbol must be a string")?;
        if !symbols.iter().any(|s| s == symbol) || output.contains_key(symbol) {
            return Err("unexpected or duplicate market symbol".into());
        }
        let rows = pair[1].as_array().ok_or("market rows must be an array")?;
        if rows.len() % 2 != 0 || rows.len() / 2 > if snapshot { 1 } else { count as usize } {
            return Err("invalid market row count".into());
        }
        let mut normalized = Vec::new();
        let mut times = HashSet::new();
        for row in rows.as_chunks::<2>().0 {
            let time = row[0].as_str().ok_or("market time must be a string")?;
            if !valid_time(time, snapshot) || !times.insert(time) {
                return Err("invalid or duplicate market time".into());
            }
            let values = row[1].as_array().ok_or("market fields must be an array")?;
            if values.is_empty() || values.len() % 2 != 0 {
                return Err("unpaired market fields".into());
            }
            let mut fields = serde_json::Map::new();
            for field in values.as_chunks::<2>().0 {
                let name = field[0]
                    .as_str()
                    .ok_or("market field name must be a string")?;
                let value = match &field[1] {
                    Bson::Int32(n) => json!(n),
                    Bson::Int64(n) => json!(n),
                    Bson::Double(n) if n.is_finite() => json!(n),
                    _ => return Err("market field must be a finite number".into()),
                };
                if name.is_empty() || fields.insert(name.to_owned(), value).is_some() {
                    return Err("duplicate or empty market field".into());
                }
            }
            if if snapshot {
                !fields.contains_key("lastPrice")
            } else {
                DAILY_FIELDS.iter().any(|f| !fields.contains_key(*f))
            } {
                return Err("required market field missing".into());
            }
            normalized.push(json!({"time":time,"fields":fields}));
        }
        output.insert(symbol.to_owned(), json!(normalized));
    }
    // A missing symbol cannot be distinguished from a partial response. Fail closed.
    if !flat.is_empty() && output.len() != symbols.len() {
        return Err("incomplete market symbol set".into());
    }
    if flat.is_empty() {
        for symbol in symbols {
            output.insert(symbol.clone(), json!([]));
        }
    }
    Ok(Value::Object(output))
}
fn valid_time(time: &str, snapshot: bool) -> bool {
    let bytes = time.as_bytes();
    let expected = if snapshot { 17 } else { 8 };
    bytes.len() == expected
        && bytes.iter().enumerate().all(|(i, b)| {
            if snapshot && i == 8 {
                *b == b' '
            } else if snapshot && (i == 11 || i == 14) {
                *b == b':'
            } else {
                b.is_ascii_digit()
            }
        })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{net::TcpListener, thread};

    #[test]
    fn vendor_config_with_legacy_encoded_comments_still_selects_ascii_endpoint() {
        assert_eq!(
            parse_port_bytes(b";\xd6\xd0\xce\xc4\n[server_formula]\naddress=0.0.0.0:58600\n")
                .unwrap(),
            58600
        );
        assert!(parse_port_bytes(b"[server_formula]\naddress=0.0.0.0:\xff\n").is_err());
    }

    #[test]
    fn endpoint_selects_formula_address_port_instead_of_other_server_ports() {
        assert_eq!(parse_port("[server]\nport=18018\n[server_formula]\naddress = 0.0.0.0:58600\nport=60000\n[other]\naddress=localhost:1").unwrap(),58600);
        for config in [
            "[server]\naddress=x:1",
            "[server_formula]\naddress=x:0",
            "[server_formula]\naddress=x:65536",
            "[server_formula]\naddress=x:1\naddress=x:2",
        ] {
            assert!(parse_port(config).is_err());
        }
    }

    #[test]
    fn snapshot_keeps_vendor_time_and_level_fields() {
        let query = PublicRead::new(ReadKind::Snapshot, vec!["000001.SZ".into()], 1).unwrap();
        let payload = doc! {"value":["000001.SZ",["20260521 15:00:00",["lastPrice",10.7,"askPrice1",10.71,"askVol1",1755_i64]]]};
        let result = query.normalize(&payload["value"]).unwrap();
        assert_eq!(
            result["data"]["000001.SZ"][0],
            json!({"time":"20260521 15:00:00","fields":{"lastPrice":10.7,"askPrice1":10.71,"askVol1":1755}})
        );
    }

    fn reply(sequence: u32, payload: Document) -> Vec<u8> {
        let body = payload.to_vec().unwrap();
        let mut frame = Vec::new();
        frame.extend(((12 + body.len()) as u32).to_be_bytes());
        frame.extend(sequence.to_be_bytes());
        frame.extend([0, 3, 0, 0x40]);
        frame.extend(body);
        frame
    }
    #[test]
    fn plain_profile_checks_header_status_completion_and_full_bson_consumption() {
        let good = reply(
            7,
            doc! {"status":0,"params":{"result":8589934592_i64,"last":true}},
        );
        assert_eq!(decode(&good, 7).unwrap(), Bson::Int64(8589934592));
        assert!(decode(&good, 8).is_err());
        for index in [0, 8, 10, 11] {
            let mut bad = good.clone();
            bad[index] ^= 1;
            assert!(decode(&bad, 7).is_err());
        }
        for payload in [
            doc! {"status":1,"params":{"result":[]}},
            doc! {"status":0,"params":{"result":[],"last":false}},
            doc! {"status":0,"params":{"result":[],"last":1}},
            doc! {"status":0,"params":{}},
        ] {
            assert!(decode(&reply(7, payload), 7).is_err());
        }
        let mut trailing = good.clone();
        trailing.push(0);
        let len = trailing.len() as u32;
        trailing[..4].copy_from_slice(&len.to_be_bytes());
        assert!(decode(&trailing, 7).is_err());
        for n in 0..good.len() {
            assert!(decode(&good[..n], 7).is_err());
        }
    }
    #[test]
    fn normalization_preserves_dates_values_and_valid_empty_results() {
        let query = PublicRead::new(ReadKind::Daily, vec!["000001.SZ".into()], 2).unwrap();
        let value = query
            .normalize(&Bson::Array(vec![
                "000001.SZ".into(),
                Bson::Array(vec![
                    "20260731".into(),
                    Bson::Array(vec![
                        "open".into(),
                        11.5.into(),
                        "high".into(),
                        11.63.into(),
                        "low".into(),
                        11.28.into(),
                        "close".into(),
                        11.63.into(),
                        "volume".into(),
                        2024979_i64.into(),
                        "amount".into(),
                        2318839881_f64.into(),
                    ]),
                ]),
            ]))
            .unwrap();
        assert_eq!(
            value["data"]["000001.SZ"][0],
            json!({"time":"20260731","fields":{"open":11.5,"high":11.63,"low":11.28,"close":11.63,"volume":2024979,"amount":2318839881_f64}})
        );
        assert_eq!(value["meta"]["source"], "client-cache");
        assert_eq!(value["meta"]["realtime"], false);
        assert_eq!(
            query.normalize(&Bson::Array(vec![])).unwrap()["data"]["000001.SZ"],
            json!([])
        );
    }
    #[test]
    fn malformed_rows_duplicates_partial_symbols_nonfinite_and_wrong_identity_fail() {
        let symbols = vec!["000001.SZ".to_owned()];
        for raw in [
            doc! {"x":["000001.SZ"]},
            doc! {"x":["600000.SH",[]]},
            doc! {"x":["000001.SZ",[],"000001.SZ",[]]},
            doc! {"x":["000001.SZ",["bad",["close",1]]]},
            doc! {"x":["000001.SZ",["20260731",["close",1,"close",2]]]},
            doc! {"x":["000001.SZ",["20260731",["close",f64::NAN]]]},
            doc! {"x":["000001.SZ",["20260731",["volume",1]]]},
        ] {
            assert!(normalize_market(&raw["x"], &symbols, 2, false).is_err());
        }
        let query = PublicRead::new(ReadKind::Instrument, symbols, 1).unwrap();
        assert!(
            query
                .normalize(&Bson::Document(
                    doc! {"InstrumentID":"600000","ExchangeID":"SH"}
                ))
                .is_err()
        );
        assert!(
            normalize_market(
                &Bson::Array(vec!["000001.SZ".into(), Bson::Array(vec![])]),
                &["000001.SZ".into(), "600000.SH".into()],
                2,
                false
            )
            .is_err()
        );
    }
    #[test]
    fn whitelist_and_limits_validate_before_network() {
        for symbols in [
            vec![],
            vec!["SH".into()],
            vec!["000001.SZ".into(), "000001.SZ".into()],
            vec!["bad symbol.SH".into()],
        ] {
            assert!(PublicRead::new(ReadKind::Daily, symbols, 2).is_err());
        }
        assert!(PublicRead::new(ReadKind::Daily, vec!["000001.SZ".into()], 0).is_err());
        assert!(PublicRead::new(ReadKind::Daily, vec!["000001.SZ".into()], 1001).is_err());
        let (method, params) = PublicRead::new(ReadKind::Snapshot, vec!["000001.SZ".into()], 1)
            .unwrap()
            .request();
        assert_eq!(method, "getMarketData");
        assert_eq!(params.get_str("period").unwrap(), "tick");
        assert_eq!(
            params.get_array("fields").unwrap(),
            &vec![Bson::String("quoter".into())]
        );
    }
    #[test]
    fn retained_session_matches_sequences_fragments_and_closes_after_wire_failure() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            for seq in 1..=3 {
                let mut header = [0; 12];
                stream.read_exact(&mut header).unwrap();
                assert_eq!(u32::from_be_bytes(header[4..8].try_into().unwrap()), seq);
                assert_eq!(&header[8..], &[0, 3, 0, 0]);
                let size = u32::from_be_bytes(header[..4].try_into().unwrap()) as usize;
                let mut body = vec![0; size - 12];
                stream.read_exact(&mut body).unwrap();
                let request = Document::from_reader(&mut Cursor::new(body)).unwrap();
                assert_eq!(request.get_str("func").unwrap(), "getMarketData");
                assert!(request.get_document("params").is_ok());
                let frame = reply(
                    if seq == 3 { 99 } else { seq },
                    doc! {"status":0,"params":{"result":[],"last":true}},
                );
                for chunk in frame.chunks(3) {
                    stream.write_all(chunk).unwrap();
                }
            }
            let mut b = [0];
            assert_eq!(stream.read(&mut b).unwrap(), 0);
        });
        let mut session = FormulaSession {
            stream: Some(TcpStream::connect(address).unwrap()),
            timeout: Duration::from_secs(2),
            sequence: 0,
        };
        let query = PublicRead::new(ReadKind::Daily, vec!["000001.SZ".into()], 2).unwrap();
        assert!(session.read(&query).is_ok());
        assert!(session.read(&query).is_ok());
        assert!(session.read(&query).is_err());
        assert!(session.stream.is_none());
        assert!(session.read(&query).is_err());
        server.join().unwrap();
    }
    #[test]
    fn partial_header_is_bounded_by_whole_operation_deadline() {
        let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
        let address = listener.local_addr().unwrap();
        let server = thread::spawn(move || {
            let (mut s, _) = listener.accept().unwrap();
            for _ in 0..15 {
                if s.write_all(&[0]).is_err() {
                    break;
                }
                thread::sleep(Duration::from_millis(30));
            }
        });
        let mut session = FormulaSession {
            stream: Some(TcpStream::connect(address).unwrap()),
            timeout: Duration::from_millis(100),
            sequence: 0,
        };
        let query = PublicRead::new(ReadKind::Daily, vec!["000001.SZ".into()], 2).unwrap();
        let start = Instant::now();
        assert!(session.read(&query).is_err());
        assert!(start.elapsed() < Duration::from_secs(1));
        assert!(session.stream.is_none());
        server.join().unwrap();
    }
}
