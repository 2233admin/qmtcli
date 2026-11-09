use bson::Bson;
use qmt_quote::{QuoteClient, Result};

fn run() -> Result<serde_json::Value> {
    let mut args = std::env::args_os().skip(1);
    let path = args
        .next()
        .ok_or("usage: qmt-native-quote-experiment <QMT-root|userdata_mini> <code.market>...")?;
    let codes = args
        .map(|arg| arg.into_string().map_err(|_| "symbols must be UTF-8"))
        .collect::<std::result::Result<Vec<_>, _>>()?;
    let symbols = codes.iter().map(String::as_str).collect::<Vec<_>>();
    let ticks = QuoteClient::new(std::path::PathBuf::from(path)).get_full_tick(&symbols)?;
    Ok(serde_json::json!({ "ok": true, "data": Bson::Document(ticks).into_relaxed_extjson() }))
}

fn main() {
    match run() {
        Ok(value) => println!("{value}"),
        Err(error) => {
            println!(
                "{}",
                serde_json::json!({ "ok": false, "error": error.to_string() })
            );
            std::process::exit(1);
        }
    }
}
