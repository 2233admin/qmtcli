//! Read-only account wire state machine, independent of DLL and process ownership.
use crate::{Result, decode_asset, decode_order, decode_position, decode_trade, encode_account};
use serde_json::{Value, json};
use std::time::{Duration, Instant};

#[derive(Clone, Copy, Debug)]
pub enum Operation {
    Asset,
    Positions,
    Orders,
    CancelableOrders,
    Trades,
    Snapshot,
}
impl Operation {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Asset => "asset",
            Self::Positions => "positions",
            Self::Orders => "orders",
            Self::CancelableOrders => "cancelable_orders",
            Self::Trades => "trades",
            Self::Snapshot => "snapshot",
        }
    }
    pub fn parse(s: &str) -> Result<Self> {
        Ok(match s {
            "asset" => Self::Asset,
            "positions" => Self::Positions,
            "orders" => Self::Orders,
            "cancelable_orders" => Self::CancelableOrders,
            "trades" => Self::Trades,
            "snapshot" => Self::Snapshot,
            _ => return Err("unsupported read-only account operation".into()),
        })
    }
}

#[derive(Debug)]
pub struct Frame {
    pub sequence: u64,
    pub kind: u32,
    pub action: u8,
    pub last: bool,
    pub session: u64,
    pub body: Vec<u8>,
}
impl Frame {
    pub fn decode(raw: &[u8]) -> Result<Self> {
        if raw.len() != 512 || raw[12] > 2 || raw[13] > 1 {
            return Err("invalid account frame header".into());
        }
        Ok(Self {
            sequence: u64::from_le_bytes(raw[..8].try_into()?),
            kind: u32::from_le_bytes(raw[8..12].try_into()?),
            action: raw[12],
            last: raw[13] != 0,
            session: u64::from_le_bytes(raw[16..24].try_into()?),
            body: raw[24..].to_vec(),
        })
    }
}

pub trait Queue {
    fn send(&mut self, frame: &[u8; 512], deadline: Instant) -> Result<()>;
    fn receive(&mut self, deadline: Instant) -> Result<Frame>;
}
pub fn encode_request(sequence: u64, kind: u32, session: u64, body: &[u8]) -> Result<[u8; 512]> {
    let expected = match kind {
        10001 => 12,
        20005 | 20007 => 28,
        20006 => 37,
        20008 => 108,
        _ => return Err("account request is not read-only".into()),
    };
    if sequence == 0 || session == 0 || session > i32::MAX as u64 || body.len() != expected {
        return Err("invalid account request identity/length".into());
    }
    let mut raw = [0; 512];
    raw[..8].copy_from_slice(&sequence.to_le_bytes());
    raw[8..12].copy_from_slice(&kind.to_le_bytes());
    raw[13] = 1;
    raw[16..24].copy_from_slice(&session.to_le_bytes());
    raw[24..24 + body.len()].copy_from_slice(body);
    Ok(raw)
}
fn deadline(timeout: Duration) -> Result<Instant> {
    if timeout.is_zero() || timeout > Duration::from_secs(60) {
        return Err("invalid account timeout".into());
    }
    Ok(Instant::now() + timeout)
}
pub struct AccountConnection<Q: Queue> {
    queue: Q,
    account: String,
    session: u64,
    sequence: u64,
    valid: bool,
}
impl<Q: Queue> AccountConnection<Q> {
    pub fn connect(mut queue: Q, account: &str, session: u64, timeout: Duration) -> Result<Self> {
        encode_account(account, "STOCK")?;
        let deadline = deadline(timeout)?;
        let mut body = Vec::from(session.to_le_bytes());
        body.extend(std::process::id().to_le_bytes());
        queue.send(&encode_request(1, 10001, session, &body)?, deadline)?;
        let reply = queue.receive(deadline)?;
        if reply.session != session
            || reply.sequence != 1
            || reply.kind != 10002
            || reply.action != 1
            || !reply.last
            || reply.body.get(..8) != Some(&session.to_le_bytes())
        {
            return Err("invalid native account connection acknowledgement".into());
        }
        Ok(Self {
            queue,
            account: account.to_owned(),
            session,
            sequence: 1,
            valid: true,
        })
    }
    pub fn query(&mut self, operation: Operation, timeout: Duration) -> Result<Value> {
        let deadline = deadline(timeout)?;
        if !self.valid {
            return Err("account connection closed; connect again".into());
        }
        let result = self.query_inner(operation, deadline);
        if result.is_err() {
            self.valid = false;
        }
        result
    }
    fn request(&mut self, kind: u32, body: &[u8], deadline: Instant) -> Result<u64> {
        self.sequence = self
            .sequence
            .checked_add(1)
            .ok_or("account sequence exhausted")?;
        self.queue.send(
            &encode_request(self.sequence, kind, self.session, body)?,
            deadline,
        )?;
        Ok(self.sequence)
    }
    fn receive(&mut self, sequence: u64, deadline: Instant) -> Result<Frame> {
        loop {
            if Instant::now() >= deadline {
                return Err("account response deadline exceeded".into());
            }
            let frame = self.queue.receive(deadline)?;
            if frame.session != self.session {
                return Err("native response belongs to another session".into());
            }
            if frame.sequence != sequence {
                continue;
            }
            if frame.action != 1 {
                return Err("invalid account response action".into());
            }
            return Ok(frame);
        }
    }
    fn query_inner(&mut self, operation: Operation, deadline: Instant) -> Result<Value> {
        let account = encode_account(&self.account, "STOCK")?;
        let sequence = self.request(20005, &account, deadline)?;
        let asset = self.receive(sequence, deadline)?;
        if asset.kind != 30001 || !asset.last {
            return Err("native account validation failed".into());
        }
        let mut result = json!({"asset":decode_asset(&asset.body,&self.account)?});
        let keys: &[&str] = match operation {
            Operation::Asset => &[],
            Operation::Positions => &["positions"],
            Operation::Orders | Operation::CancelableOrders => &["orders"],
            Operation::Trades => &["trades"],
            Operation::Snapshot => &["positions", "orders", "trades"],
        };
        for key in keys {
            let mut body = account.to_vec();
            type RecordDecoder = fn(&[u8], &str) -> Result<Value>;
            let (request, response, size, decode): (u32, u32, usize, RecordDecoder) = match *key {
                "positions" => {
                    body.extend([0; 80]);
                    (20008, 30004, 328, decode_position)
                }
                "orders" => {
                    body.extend([0; 8]);
                    body.push(matches!(operation, Operation::CancelableOrders) as u8);
                    (20006, 30002, 476, decode_order)
                }
                _ => (20007, 30003, 552, decode_trade),
            };
            let seq = self.request(request, &body, deadline)?;
            let mut rows = Vec::new();
            let mut fragment = Vec::new();
            loop {
                let frame = self.receive(seq, deadline)?;
                if frame.kind == 20000 {
                    if !frame.last
                        || !rows.is_empty()
                        || !fragment.is_empty()
                        || frame.body.get(..8) != Some(&(-1_i64).to_le_bytes())
                    {
                        return Err("invalid native empty/error completion".into());
                    }
                    break;
                }
                let data = if frame.kind == 10009 {
                    let b = &frame.body;
                    if b.len() < 38 {
                        return Err("truncated list fragment".into());
                    }
                    let flag = u32::from_le_bytes(b[..4].try_into()?);
                    let original = u32::from_le_bytes(b[4..8].try_into()?);
                    let total = u64::from_le_bytes(b[8..16].try_into()?);
                    let n = u64::from_le_bytes(b[16..24].try_into()?);
                    let offset = u64::from_le_bytes(b[24..32].try_into()?);
                    if flag != 1
                        || original != response
                        || total != size as u64
                        || n == 0
                        || offset != fragment.len() as u64
                        || n > total.saturating_sub(offset)
                        || n > b.len().saturating_sub(38) as u64
                    {
                        return Err("invalid native list fragment".into());
                    }
                    fragment.extend_from_slice(&b[38..38 + n as usize]);
                    if fragment.len() < size {
                        if frame.last {
                            return Err("premature last fragment".into());
                        }
                        continue;
                    }
                    std::mem::take(&mut fragment)
                } else {
                    if frame.kind != response || !fragment.is_empty() {
                        return Err("unexpected native list record".into());
                    }
                    frame.body
                };
                if rows.len() >= 100000 {
                    return Err("native record count exceeds resource limit".into());
                }
                rows.push(decode(&data, &self.account)?);
                if frame.last {
                    break;
                }
            }
            result[*key] = json!(rows);
        }
        Ok(result)
    }
    pub fn into_queue(self) -> Q {
        self.queue
    }
}
