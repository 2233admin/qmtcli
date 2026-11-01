//! Private executable mode: owns every vendor object until this process exits.
use crate::{
    Result, profile,
    protocol::{AccountConnection, Operation},
    windows,
};
use serde_json::{Value, json};
use std::{
    io::{self, BufRead, Read, Write},
    path::Path,
    time::Duration,
};
pub const MARKER: &str = "QMTCLI_NATIVE_RESULT:";
pub const MAX_LINE: usize = 16 * 1024 * 1024;

pub(crate) fn read_message(input: &mut impl BufRead) -> Result<Option<Value>> {
    let mut line = Vec::new();
    let count = input
        .take((MAX_LINE + 1) as u64)
        .read_until(b'\n', &mut line)?;
    if count == 0 {
        return Ok(None);
    }
    if count > MAX_LINE {
        return Err("worker message exceeds resource limit".into());
    }
    let value: Value = serde_json::from_slice(&line)?;
    if !value.is_object() {
        return Err("worker message must be an object".into());
    }
    Ok(Some(value))
}
pub(crate) fn emit(value: &Value) -> Result<()> {
    let mut out = io::stdout().lock();
    out.write_all(MARKER.as_bytes())?;
    serde_json::to_writer(&mut out, value)?;
    out.write_all(b"\n")?;
    out.flush()?;
    Ok(())
}
fn timeout(value: &Value) -> Result<Duration> {
    let n = value["timeout"].as_f64().ok_or("missing worker timeout")?;
    if !n.is_finite() || n <= 0.0 || n > 60.0 {
        return Err("invalid worker timeout".into());
    }
    Ok(Duration::from_secs_f64(n))
}

pub fn run() -> Result<()> {
    let mut id = None;
    let result = (|| -> Result<()> {
        let mut input = io::stdin().lock();
        let init = read_message(&mut input)?.ok_or("worker initialization EOF")?;
        let path = Path::new(init["path"].as_str().ok_or("missing worker path")?);
        let paths = profile::validate(path)?;
        if let Some(path) = init["probe_path"].as_str() {
            windows::probe(&paths.bin, Path::new(path))?;
            emit(&json!({"ready":true,"probe":true,"pid":std::process::id()}))?;
            return Ok(());
        }
        if !paths.data.join("up_queue_xtquant").is_file() {
            return Err("MiniQMT native service queue is missing".into());
        }
        let session = init["session"]
            .as_u64()
            .filter(|n| *n > 0 && *n <= i32::MAX as u64)
            .ok_or("invalid worker session")?;
        let owner = init["owner"]
            .as_str()
            .filter(|s| s.len() == 32 && s.bytes().all(|b| b.is_ascii_hexdigit()))
            .ok_or("invalid reply owner")?;
        let reply = paths.data.join(format!("down_queue_{session}"));
        let marker = format!("qmtcli-native-owner:{owner}");
        if reply.metadata()?.len() != marker.len() as u64
            || std::fs::read(&reply)? != marker.as_bytes()
        {
            return Err("reply queue is not owned by this worker".into());
        }
        let account = init["account"].as_str().ok_or("missing worker account")?;
        let queue = windows::NativeQueue::open(&paths.bin, &paths.data, &reply)?;
        let mut client = AccountConnection::connect(queue, account, session, timeout(&init)?)?;
        emit(&json!({"ready":true,"pid":std::process::id()}))?;
        while let Some(request) = read_message(&mut input)? {
            id = Some(request["id"].as_u64().ok_or("invalid worker request id")?);
            let op = Operation::parse(
                request["operation"]
                    .as_str()
                    .ok_or("missing read operation")?,
            )?;
            let data = client.query(op, timeout(&request)?)?;
            emit(&json!({"id":id,"ok":true,"data":data}))?;
        }
        Ok(())
    })();
    if let Err(ref e) = result {
        let _ = emit(&json!({"ready":false,"id":id,"ok":false,"error":e.to_string()}));
    }
    result
}
