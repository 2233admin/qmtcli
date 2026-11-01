//! Version-pinned account records. This core has no dependency on qmt-quote.
//! Vendor calls are isolated in a child process; no dependency on Python bindings.
use serde_json::{Value, json};
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

/// Implemented platform transport, not a probe of the broker service.
pub const TRANSPORT_AVAILABLE: bool = cfg!(all(windows, target_pointer_width = "64"));
pub mod profile;
pub mod protocol;
#[cfg(windows)]
mod session;
#[cfg(windows)]
mod windows;
#[cfg(windows)]
mod worker;
#[cfg(windows)]
pub use session::AccountSession;
#[cfg(windows)]
pub fn run_worker() -> Result<()> {
    worker::run()
}
#[cfg(not(windows))]
pub fn run_worker() -> Result<()> {
    Err("native account requires Windows x64".into())
}

#[cfg(not(windows))]
#[derive(Default)]
pub struct AccountSession;
#[cfg(not(windows))]
impl AccountSession {
    pub fn connected(&mut self) -> bool {
        false
    }
    pub fn generation(&self) -> u64 {
        0
    }
    pub fn close(&mut self) {}
    pub fn query(
        &mut self,
        _path: &std::path::Path,
        _account: &str,
        _kind: &str,
        _op: protocol::Operation,
        _timeout: std::time::Duration,
    ) -> Result<Value> {
        Err("native account requires Windows x64".into())
    }
}

/// Encode the pinned STOCK identity; never truncate an oversized account.
pub fn encode_account(account: &str, account_type: &str) -> Result<[u8; 28]> {
    if !account_type.eq_ignore_ascii_case("STOCK") {
        return Err("native account currently supports STOCK only".into());
    }
    if account.is_empty()
        || account.len() > 23
        || account.trim().is_empty()
        || !account.bytes().all(|b| (32..=126).contains(&b))
    {
        return Err("account must be 1 to 23 printable ASCII bytes".into());
    }
    let mut result = [0; 28];
    result[..4].copy_from_slice(&2_i32.to_le_bytes());
    result[4..4 + account.len()].copy_from_slice(account.as_bytes());
    Ok(result)
}

fn text(raw: &[u8], offset: usize, size: usize) -> Result<&str> {
    let bytes = raw
        .get(offset..offset + size)
        .ok_or("truncated native record")?;
    Ok(std::str::from_utf8(
        bytes.split(|b| *b == 0).next().unwrap_or_default(),
    )?)
}

fn integer(raw: &[u8], offset: usize) -> Result<i32> {
    Ok(i32::from_le_bytes(
        raw.get(offset..offset + 4)
            .ok_or("truncated int32")?
            .try_into()?,
    ))
}

fn long(raw: &[u8], offset: usize) -> Result<i64> {
    Ok(i64::from_le_bytes(
        raw.get(offset..offset + 8)
            .ok_or("truncated int64")?
            .try_into()?,
    ))
}

fn number(raw: &[u8], offset: usize) -> Result<f64> {
    let n = f64::from_le_bytes(
        raw.get(offset..offset + 8)
            .ok_or("truncated float")?
            .try_into()?,
    );
    if !n.is_finite() {
        return Err("native account values must be finite".into());
    }
    Ok(n)
}

fn identity(raw: &[u8], account: &str, size: usize, symbol: usize) -> Result<Value> {
    encode_account(account, "STOCK")?;
    if raw.len() < size {
        return Err("native record shorter than required size".into());
    }
    if integer(raw, 0)? != 2 || text(raw, 4, 24)? != account {
        return Err("native record does not match requested account/type".into());
    }
    let code = text(raw, symbol, 64)?;
    Ok(json!({"account_type":2,"account_id":account,
              "stock_code": if code.is_empty() { text(raw,28,16)? } else { code }}))
}

/// Decode the public asset fields after checking the expected account identity.
pub fn decode_asset(raw: &[u8], account: &str) -> Result<Value> {
    encode_account(account, "STOCK")?;
    if raw.len() < 76 {
        return Err("native asset shorter than 76 bytes".into());
    }
    if integer(raw, 0)? != 2 || text(raw, 4, 24)? != account {
        return Err("native asset does not match requested account/type".into());
    }
    Ok(
        json!({"account_type":2,"account_id":account,"cash":number(raw,28)?,
        "frozen_cash":number(raw,36)?,"market_value":number(raw,44)?,"total_asset":number(raw,52)?}),
    )
}

/// Decode the 328-byte position layout, preserving unaligned Int64 quantities.
pub fn decode_position(raw: &[u8], account: &str) -> Result<Value> {
    let mut result = identity(raw, account, 328, 112)?;
    for (name, offset) in [
        ("volume", 44),
        ("can_use_volume", 52),
        ("frozen_volume", 76),
        ("on_road_volume", 84),
        ("yesterday_volume", 92),
    ] {
        let n = long(raw, offset)?;
        if n < 0 {
            return Err("native position quantities must be nonnegative".into());
        }
        result[name] = json!(n);
    }
    result["open_price"] = json!(number(raw, 60)?);
    result["market_value"] = json!(number(raw, 68)?);
    Ok(result)
}

/// Decode the 476-byte order layout; a zero order id remains valid.
pub fn decode_order(raw: &[u8], account: &str) -> Result<Value> {
    let mut result = identity(raw, account, 476, 324)?;
    for (name, offset) in [
        ("order_id", 44),
        ("order_type", 56),
        ("order_volume", 60),
        ("price_type", 64),
        ("traded_volume", 76),
        ("order_status", 88),
    ] {
        let n = integer(raw, offset)?;
        if matches!(name, "order_volume" | "traded_volume") && n < 0 {
            return Err("native order quantities must be nonnegative".into());
        }
        result[name] = json!(n);
    }
    result["order_time"] = json!(long(raw, 48)?);
    result["price"] = json!(number(raw, 68)?);
    result["traded_price"] = json!(number(raw, 80)?);
    for (name, offset) in [
        ("order_sysid", 92),
        ("status_msg", 116),
        ("strategy_name", 140),
    ] {
        result[name] = json!(text(raw, offset, 24)?);
    }
    let remark = text(raw, 196, 128)?;
    result["order_remark"] = json!(if remark.is_empty() {
        text(raw, 164, 24)?
    } else {
        remark
    });
    Ok(result)
}

/// Decode the 552-byte trade layout, preferring long symbol/id/remark fields.
pub fn decode_trade(raw: &[u8], account: &str) -> Result<Value> {
    let mut result = identity(raw, account, 552, 392)?;
    let volume = integer(raw, 84)?;
    if volume < 0 {
        return Err("native trade volume must be nonnegative".into());
    }
    let id = text(raw, 312, 80)?;
    let remark = text(raw, 184, 128)?;
    for (name, value) in [
        (
            "traded_id",
            if id.is_empty() {
                text(raw, 44, 24)?
            } else {
                id
            },
        ),
        ("order_sysid", text(raw, 104, 24)?),
        ("strategy_name", text(raw, 128, 24)?),
        (
            "order_remark",
            if remark.is_empty() {
                text(raw, 152, 24)?
            } else {
                remark
            },
        ),
    ] {
        result[name] = json!(value);
    }
    result["traded_time"] = json!(long(raw, 68)?);
    result["traded_price"] = json!(number(raw, 76)?);
    result["traded_volume"] = json!(volume);
    result["traded_amount"] = json!(number(raw, 88)?);
    result["order_id"] = json!(integer(raw, 96)?);
    result["order_type"] = json!(integer(raw, 100)?);
    Ok(result)
}
