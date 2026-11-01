//! Agent-facing dispatch; quote and account cores do not depend on this adapter.
use bson::Bson;
use qmt_quote::{QuoteClient, QuoteSession};
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
}
struct Spec {
    name: &'static str,
    command: Command,
    description: &'static str,
}
const SPECS: &[Spec] = &[
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
}

pub fn failure(message: impl ToString) -> Value {
    json!({"ok":false,"error":message.to_string()})
}

fn capabilities() -> Value {
    json!({"implementation":"rust","version":env!("CARGO_PKG_VERSION"),
        "transport":["cli","rpc","jsonl-stdio"],"read_only":true,
        "commands":SPECS.iter().map(|s|json!({"name":s.name,"description":s.description})).collect::<Vec<_>>(),
        "limits":{"symbols":1000,"request_bytes":MAX_REQUEST_BYTES},
        "unavailable":{"account_transport":"Rust worker/ABI migration pending","mcp":"not implemented",
                       "history":"not implemented","subscriptions":"not implemented"}})
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
            "backend":{"const":"native"},"path":{"type":"string","minLength":1},"symbols":{"type":"array","minItems":1,"maxItems":1000,"items":{"type":"string","pattern":"^[!-~]{1,64}$"}},
            "quote_port":{"type":"integer","minimum":1,"maximum":65535},"timeout":{"type":"number","minimum":0.1,"maximum":60}},
            "allOf":[
                {"if":{"properties":{"command":{"enum":["full-tick","full_tick"]}}},"then":{"required":["backend","path","symbols"]}},
                {"if":{"properties":{"command":{"const":"doctor"}}},"then":{"required":["path"]}}
            ]})),
            Command::Examples => Ok(json!([{"id":1,"command":"full_tick","backend":"native",
                "path":"D:\\QMT","symbols":["600000.SH","000001.SZ"]}])),
            Command::Status => Ok(json!({"implementation":"rust","scope":"this process",
                "quote_session_connected":self.quote.is_some(),"broker_login":"not checked",
                "account_transport_available":qmt_trade::TRANSPORT_AVAILABLE})),
            Command::Doctor => {
                let key = quote_key(request)?;
                QuoteClient::new(&key.root).validate_runtime()?;
                Ok(
                    json!({"quote_profile":"matched","service_connection":"not attempted",
                    "account_transport_available":qmt_trade::TRANSPORT_AVAILABLE}),
                )
            }
            Command::FullTick => self.full_tick(request),
        }
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
