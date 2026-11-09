use qmtcli_rs::{MAX_REQUEST_BYTES, Result, Runtime, emit, failure, serve};
use serde_json::{Value, json};
use std::io::{self, Read};

fn run() -> Result<bool> {
    let args = std::env::args_os()
        .skip(1)
        .map(|s| s.into_string().map_err(|_| "arguments must be Unicode"))
        .collect::<std::result::Result<Vec<_>, _>>()?;
    match args.first().map(String::as_str) {
        Some("--internal-account-worker") if args.len() == 1 => Ok(qmt_trade::run_worker().is_ok()),
        Some("server") if args.len() == 1 => {
            serve(io::stdin().lock(), io::stdout().lock())?;
            Ok(true)
        }
        Some("rpc") if args.len() <= 2 => {
            let bytes = if let Some(arg) = args.get(1) {
                arg.as_bytes().to_vec()
            } else {
                let mut data = Vec::new();
                io::stdin()
                    .take((MAX_REQUEST_BYTES + 1) as u64)
                    .read_to_end(&mut data)?;
                data
            };
            if bytes.len() > MAX_REQUEST_BYTES {
                return Err("request exceeds byte limit".into());
            }
            let request: Value = serde_json::from_slice(&bytes)?;
            let response = Runtime::default().handle(&request);
            emit(&mut io::stdout().lock(), &response)?;
            Ok(response["ok"] == true)
        }
        Some("--help" | "-h") | None => {
            emit(
                &mut io::stdout().lock(),
                &json!({"ok":true,"data":{"usage":
                "qmtcli-rs capabilities|schema|examples|status; qmtcli-rs rpc [JSON]; qmtcli-rs server"}}),
            )?;
            Ok(true)
        }
        Some(command) if args.len() == 1 => {
            let response = Runtime::default().handle(&json!({"command":command}));
            emit(&mut io::stdout().lock(), &response)?;
            Ok(response["ok"] == true)
        }
        _ => Err("unsupported arguments; use --help or rpc JSON".into()),
    }
}

fn main() -> std::process::ExitCode {
    match run() {
        Ok(true) => std::process::ExitCode::SUCCESS,
        Ok(false) => std::process::ExitCode::FAILURE,
        Err(e) => {
            let _ = emit(&mut io::stdout().lock(), &failure(e));
            std::process::ExitCode::FAILURE
        }
    }
}
