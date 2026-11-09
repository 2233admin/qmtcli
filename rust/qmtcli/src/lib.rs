//! Agent-facing dispatch; quote and account cores do not depend on this adapter.
use bson::Bson;
use qmt_quote::{QuoteClient, QuoteSession};
use qmt_trade::{AccountSession, protocol::Operation};
use serde_json::{Value, json};
use std::{
    io::{self, BufRead, Read, Write},
    path::PathBuf,
    time::Duration,
};

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;
pub const MAX_REQUEST_BYTES: usize = 1024 * 1024;

#[derive(Clone, Copy)]
enum Command {
    Capabilities,
    Schema,
    Examples,
    Status,
    Doctor,
    FullTick,
    Instrument,
    Daily,
    Account(Operation),
}
struct Spec {
    name: &'static str,
    command: Command,
    description: &'static str,
}
const SPECS: &[Spec] = &[
    Spec {
        name: "instrument-detail",
        command: Command::Instrument,
        description: "Big QMT formula cached instrument information, one symbol",
    },
    Spec {
        name: "daily-bars",
        command: Command::Daily,
        description: "Big QMT formula latest OHLCV/amount daily bars, unadjusted client cache",
    },
    Spec {
        name: "asset",
        command: Command::Account(Operation::Asset),
        description: "Read native account assets",
    },
    Spec {
        name: "positions",
        command: Command::Account(Operation::Positions),
        description: "Read native account positions",
    },
    Spec {
        name: "orders",
        command: Command::Account(Operation::Orders),
        description: "Read native orders, optionally cancelable only",
    },
    Spec {
        name: "trades",
        command: Command::Account(Operation::Trades),
        description: "Read native account trades",
    },
    Spec {
        name: "account-snapshot",
        command: Command::Account(Operation::Snapshot),
        description: "Non-atomic asset/positions/orders/trades through one retained worker",
    },
    Spec {
        name: "capabilities",
        command: Command::Capabilities,
        description: "Implemented Rust commands and limits",
    },
    Spec {
        name: "schema",
        command: Command::Schema,
        description: "JSON request schema",
    },
    Spec {
        name: "examples",
        command: Command::Examples,
        description: "Native request examples",
    },
    Spec {
        name: "status",
        command: Command::Status,
        description: "This process's session status, not broker login status",
    },
    Spec {
        name: "doctor",
        command: Command::Doctor,
        description: "Validate an installed quote runtime without connecting",
    },
    Spec {
        name: "full-tick",
        command: Command::FullTick,
        description: "Fresh query of the quote service's cached full-tick snapshot",
    },
];

#[derive(PartialEq)]
struct QuoteKey {
    root: PathBuf,
    port: u16,
    timeout: Duration,
}
#[derive(Default)]
pub struct Runtime {
    quote: Option<(QuoteKey, QuoteSession)>,
    formula: Option<(PathBuf, Duration, qmt_quote::formula::FormulaSession)>,
    account: AccountSession,
}

pub fn failure(message: impl ToString) -> Value {
    json!({"ok":false,"error":message.to_string()})
}

fn capabilities() -> Value {
    json!({"implementation":"rust","version":env!("CARGO_PKG_VERSION"),
        "transport":["cli","rpc","jsonl-stdio"],"read_only":true,
        "commands":SPECS.iter().filter(|s|!matches!(s.command,Command::Account(_)) || qmt_trade::TRANSPORT_AVAILABLE).map(|s|json!({"name":s.name,"description":s.description})).collect::<Vec<_>>(),
        "limits":{"symbols":1000,"request_bytes":MAX_REQUEST_BYTES},
        "account_transport_implemented":qmt_trade::TRANSPORT_AVAILABLE,
        "backends":{"native":{"commands":["full-tick","asset","positions","orders","trades","account-snapshot"]},"formula":{"commands":["instrument-detail","daily-bars","full-tick"],"source":"client-cache","realtime":false,"limits":{"symbols":100,"daily_count":1000,"frame_bytes":qmt_quote::formula::MAX_FRAME},"daily_fields":["open","high","low","close","volume","amount"],"daily_dividend_type":"none","streaming":false,"compression":false}},
        "unavailable":{"account_subscriptions":"unsolicited native events not implemented","mcp":"not implemented",
                       "bulk_history":"not implemented; formula daily close reads available","subscriptions":"not implemented"}})
}

impl Runtime {
    pub fn handle(&mut self, request: &Value) -> Value {
        let mut response = match self.dispatch(request) {
            Ok(data) => json!({"ok":true,"data":data}),
            Err(e) => failure(e),
        };
        if let Some(id) = request.get("id").filter(|id| !id.is_null()) {
            response["id"] = id.clone();
        }
        response
    }

    fn dispatch(&mut self, request: &Value) -> Result<Value> {
        if !request.is_object() {
            return Err("request must be a JSON object".into());
        }
        let name = request["command"]
            .as_str()
            .ok_or("command must be a string")?;
        let normalized = name.replace('_', "-");
        let spec = SPECS
            .iter()
            .find(|s| s.name == normalized)
            .ok_or("unsupported Rust command; see capabilities")?;
        match spec.command {
            Command::Capabilities => Ok(capabilities()),
            Command::Schema => Ok(json!({"type":"object","required":["command"],"properties":{
            "command":{"enum":SPECS.iter().flat_map(|s|if s.name.contains('-') {
                vec![s.name.to_owned(),s.name.replace('-',"_")]
            } else {vec![s.name.to_owned()]}).collect::<Vec<_>>()},
            "backend":{"enum":["native","formula"]},"path":{"type":"string","minLength":1},"symbols":{"type":"array","minItems":1,"maxItems":1000,"items":{"type":"string","pattern":"^[!-~]{1,64}$"}},
            "count":{"type":"integer","minimum":1,"maximum":1000},
            "account":{"type":"string","minLength":1,"maxLength":23,"pattern":"^[ -~]+$"},"account_type":{"enum":["STOCK","stock"]},"cancelable_only":{"type":"boolean"},
            "quote_port":{"type":"integer","minimum":1,"maximum":65535},"timeout":{"type":"number","minimum":0.1,"maximum":60}},
            "allOf":[
                {"if":{"properties":{"command":{"enum":["instrument-detail","instrument_detail","daily-bars","daily_bars"]}}},"then":{"required":["backend","path","symbols"],"properties":{"backend":{"const":"formula"}}}},
                {"if":{"properties":{"backend":{"const":"formula"}},"required":["backend"]},"then":{"properties":{"symbols":{"maxItems":100,"uniqueItems":true,"items":{"type":"string","pattern":"^[A-Za-z0-9]{1,24}\\.(SH|SZ|BJ)$"}}}}},
                {"if":{"properties":{"command":{"enum":["instrument-detail","instrument_detail"]}}},"then":{"properties":{"symbols":{"maxItems":1}}}},
                {"if":{"properties":{"backend":{"const":"formula"},"command":{"enum":["instrument-detail","instrument_detail","full-tick","full_tick"]}},"required":["backend","command"]},"then":{"properties":{"count":{"const":1}}}},
                {"if":{"properties":{"backend":{"const":"formula"}},"required":["backend"]},"then":{"propertyNames":{"enum":["id","command","backend","path","symbols","count","timeout"]}}},
                {"if":{"properties":{"command":{"enum":["full-tick","full_tick"]}}},"then":{"required":["backend","path","symbols"]}},
                {"if":{"properties":{"command":{"const":"doctor"}}},"then":{"required":["path"]}},
                {"if":{"properties":{"command":{"enum":["asset","positions","orders","trades","account-snapshot","account_snapshot"]}}},"then":{"required":["backend","path","account"],"properties":{"backend":{"const":"native"}}}}
            ]})),
            Command::Examples => Ok(json!([{"id":1,"command":"full_tick","backend":"native",
                "path":"D:\\QMT","symbols":["600000.SH","000001.SZ"]},
                {"id":2,"command":"account_snapshot","backend":"native","path":"D:\\QMT","account":"YOUR_ACCOUNT"},
                {"id":3,"command":"instrument-detail","backend":"formula","path":"D:\\QMT","symbols":["000001.SZ"]},
                {"id":4,"command":"daily-bars","backend":"formula","path":"D:\\QMT","symbols":["000001.SZ","600000.SH"],"count":2},
                {"id":5,"command":"full-tick","backend":"formula","path":"D:\\QMT","symbols":["000001.SZ","600000.SH"]}])),
            Command::Status => Ok(json!({"implementation":"rust","scope":"this process",
                "quote_session_connected":self.quote.is_some(),"broker_login":"not checked",
                "formula_session_connected":self.formula.is_some(),
                "account_transport_implemented":qmt_trade::TRANSPORT_AVAILABLE,"account_transport_available":self.account.connected(),"native_generation":self.account.generation()})),
            Command::Doctor => {
                if request["backend"] == "formula" {
                    let (root, _) = formula_key(request)?;
                    let port = qmt_quote::formula::endpoint(&root)?;
                    return Ok(
                        json!({"formula_profile":"matched","host":"127.0.0.1","port":port,"service_connection":"not attempted","source":"client-cache"}),
                    );
                }
                let key = quote_key(request)?;
                QuoteClient::new(&key.root).validate_runtime()?;
                Ok(
                    json!({"quote_profile":"matched","service_connection":"not attempted",
                    "account_transport_implemented":qmt_trade::TRANSPORT_AVAILABLE,"account_transport_available":self.account.connected(),
                    "account_profile":qmt_trade::profile::validate(&key.root).map(|_|"matched".to_owned()).unwrap_or_else(|e|format!("unmatched: {e}")),
                    "account_service_queue_present":key.root.join("userdata_mini/up_queue_xtquant").is_file()}),
                )
            }
            Command::FullTick if request["backend"] == "formula" => {
                self.formula_read(request, qmt_quote::formula::ReadKind::Snapshot)
            }
            Command::FullTick => self.full_tick(request),
            Command::Instrument => {
                self.formula_read(request, qmt_quote::formula::ReadKind::Instrument)
            }
            Command::Daily => self.formula_read(request, qmt_quote::formula::ReadKind::Daily),
            Command::Account(operation) => self.account_query(request, operation),
        }
    }

    fn formula_read(
        &mut self,
        request: &Value,
        kind: qmt_quote::formula::ReadKind,
    ) -> Result<Value> {
        if request["backend"] != "formula" {
            return Err("public Big QMT reads require explicit backend=formula".into());
        }
        for key in request
            .as_object()
            .ok_or("request must be an object")?
            .keys()
        {
            if ![
                "id", "command", "backend", "path", "symbols", "count", "timeout",
            ]
            .contains(&key.as_str())
            {
                return Err(format!("unsupported formula argument: {key}").into());
            }
        }
        let symbols = request["symbols"]
            .as_array()
            .ok_or("symbols must be an array")?
            .iter()
            .map(|v| {
                v.as_str()
                    .map(str::to_owned)
                    .ok_or("symbols must contain strings")
            })
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let count = match request.get("count") {
            None => {
                if matches!(kind, qmt_quote::formula::ReadKind::Daily) {
                    2
                } else {
                    1
                }
            }
            Some(v) => v.as_u64().ok_or("count must be an integer")?,
        };
        if !matches!(kind, qmt_quote::formula::ReadKind::Daily) && count != 1 {
            return Err("count must be 1 for instrument-detail/full-tick".into());
        }
        let query = qmt_quote::formula::PublicRead::new(kind, symbols, count)?;
        let (root, timeout) = formula_key(request)?;
        if self
            .formula
            .as_ref()
            .is_none_or(|(r, t, _)| r != &root || *t != timeout)
        {
            self.formula = None;
            let session = qmt_quote::formula::FormulaSession::connect(&root, timeout)?;
            self.formula = Some((root, timeout, session));
        }
        let result = self
            .formula
            .as_mut()
            .ok_or("missing formula session")?
            .2
            .read(&query);
        if result.is_err() {
            self.formula = None;
        }
        result
    }

    fn account_query(&mut self, request: &Value, mut operation: Operation) -> Result<Value> {
        if request["backend"].as_str() != Some("native") {
            return Err("Rust account queries require explicit backend=native".into());
        }
        let account = request["account"].as_str().ok_or("requires account")?;
        let kind = match request.get("account_type") {
            None => "STOCK",
            Some(v) => v.as_str().ok_or("account_type must be a string")?,
        };
        qmt_trade::encode_account(account, kind)?;
        if matches!(operation, Operation::Orders) {
            match request.get("cancelable_only") {
                Some(Value::Bool(true)) => operation = Operation::CancelableOrders,
                Some(Value::Bool(false)) | None => {}
                _ => return Err("cancelable_only must be a boolean".into()),
            }
        }
        let path = request["path"]
            .as_str()
            .filter(|s| !s.is_empty())
            .ok_or("requires an explicit QMT path")?;
        let timeout = match request.get("timeout") {
            None => 5.0,
            Some(v) => v.as_f64().ok_or("timeout must be numeric")?,
        };
        if !timeout.is_finite() || !(0.1..=60.0).contains(&timeout) {
            return Err("timeout must be 0.1 to 60 seconds".into());
        }
        let data = self.account.query(
            std::path::Path::new(path),
            account,
            kind,
            operation,
            Duration::from_secs_f64(timeout),
        )?;
        let key = match operation {
            Operation::Asset => "asset",
            Operation::Positions => "positions",
            Operation::Orders | Operation::CancelableOrders => "orders",
            Operation::Trades => "trades",
            Operation::Snapshot => return Ok(data),
        };
        data.get(key)
            .cloned()
            .ok_or_else(|| "native worker returned an incomplete result".into())
    }

    fn full_tick(&mut self, request: &Value) -> Result<Value> {
        // The Python entry defaults to SDK. Do not silently reinterpret that default.
        if request["backend"].as_str() != Some("native") {
            return Err(
                "Rust full-tick requires explicit backend=native; SDK fallback is unavailable"
                    .into(),
            );
        }
        let values = request["symbols"]
            .as_array()
            .ok_or("symbols must be an array")?;
        if values.is_empty() || values.len() > 1000 {
            return Err("requires 1 to 1000 symbols".into());
        }
        let symbols = values
            .iter()
            .map(|s| s.as_str().ok_or("symbols must contain strings"))
            .collect::<std::result::Result<Vec<_>, _>>()?;
        if symbols
            .iter()
            .any(|s| s.is_empty() || s.len() > 64 || !s.bytes().all(|b| b.is_ascii_graphic()))
        {
            return Err("symbols must be nonempty printable ASCII, max 64 bytes".into());
        }
        let key = quote_key(request)?;
        if self
            .quote
            .as_ref()
            .is_none_or(|(current, _)| current != &key)
        {
            // Drop the old owner before attempting a differently configured session.
            self.quote = None;
            let session = QuoteClient::new(&key.root)
                .with_port(key.port)
                .with_timeout(key.timeout)
                .connect()?;
            self.quote = Some((key, session));
        }
        let result = self
            .quote
            .as_mut()
            .ok_or("missing quote session")?
            .1
            .get_full_tick(&symbols);
        match result {
            Ok(data) => Ok(Bson::Document(data).into_relaxed_extjson()),
            Err(e) => {
                self.quote = None;
                Err(e)
            }
        }
    }
}

fn formula_key(request: &Value) -> Result<(PathBuf, Duration)> {
    let path = request["path"]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or("requires an explicit QMT installation root")?;
    let timeout = match request.get("timeout") {
        None => 5.0,
        Some(v) => v.as_f64().ok_or("timeout must be numeric")?,
    };
    if !timeout.is_finite() || !(0.1..=60.0).contains(&timeout) {
        return Err("timeout must be 0.1 to 60 seconds".into());
    }
    Ok((
        PathBuf::from(path).canonicalize()?,
        Duration::from_secs_f64(timeout),
    ))
}

fn quote_key(request: &Value) -> Result<QuoteKey> {
    let path = request["path"]
        .as_str()
        .filter(|s| !s.is_empty())
        .ok_or("requires an explicit QMT path")?;
    let mut root = PathBuf::from(path).canonicalize()?;
    if root.file_name().is_some_and(|name| name == "userdata_mini") {
        root = root
            .parent()
            .ok_or("invalid userdata_mini path")?
            .to_owned();
    }
    let port = match request.get("quote_port") {
        None => 58610,
        Some(n) => n
            .as_u64()
            .filter(|n| (1..=65535).contains(n))
            .ok_or("invalid quote_port")? as u16,
    };
    let timeout = match request.get("timeout") {
        None => 5.0,
        Some(n) => n.as_f64().ok_or("timeout must be numeric")?,
    };
    if !timeout.is_finite() || !(0.1..=60.0).contains(&timeout) {
        return Err("timeout must be 0.1 to 60 seconds".into());
    }
    Ok(QuoteKey {
        root,
        port,
        timeout: Duration::from_secs_f64(timeout),
    })
}

pub fn emit(output: &mut impl Write, value: &Value) -> io::Result<()> {
    serde_json::to_writer(&mut *output, value)?;
    output.write_all(b"\n")?;
    output.flush()
}

pub fn serve(mut input: impl BufRead, mut output: impl Write) -> io::Result<()> {
    let mut runtime = Runtime::default();
    loop {
        let mut line = Vec::new();
        let n = (&mut input)
            .take((MAX_REQUEST_BYTES + 1) as u64)
            .read_until(b'\n', &mut line)?;
        if n == 0 {
            return Ok(());
        } // Runtime drops its owned quote socket at EOF.
        if n > MAX_REQUEST_BYTES {
            if line.last() != Some(&b'\n') {
                input.skip_until(b'\n')?;
            }
            emit(&mut output, &failure("request exceeds byte limit"))?;
            continue;
        }
        let text = match std::str::from_utf8(&line) {
            Ok(text) => text.trim().trim_start_matches('\u{feff}'),
            Err(_) => {
                emit(&mut output, &failure("request must be UTF-8"))?;
                continue;
            }
        };
        if text.is_empty() {
            continue;
        }
        let response = match serde_json::from_str::<Value>(text) {
            Ok(request) => runtime.handle(&request),
            Err(_) => failure("invalid JSON request"),
        };
        emit(&mut output, &response)?;
    }
}
