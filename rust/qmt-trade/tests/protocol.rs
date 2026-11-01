use qmt_trade::Result;
use qmt_trade::protocol::{AccountConnection, Frame, Operation, Queue};
use std::{
    collections::VecDeque,
    time::{Duration, Instant},
};

struct Fake {
    replies: VecDeque<Frame>,
    sent: Vec<Frame>,
}
impl Queue for Fake {
    fn send(&mut self, frame: &[u8; 512], _: Instant) -> Result<()> {
        self.sent.push(Frame::decode(frame)?);
        Ok(())
    }
    fn receive(&mut self, _: Instant) -> Result<Frame> {
        self.replies.pop_front().ok_or_else(|| "fixture EOF".into())
    }
}
fn reply(seq: u64, kind: u32, last: bool, body: &[u8]) -> Frame {
    Frame {
        sequence: seq,
        kind,
        action: 1,
        last,
        session: 123,
        body: body.to_vec(),
    }
}
fn queue(mut frames: Vec<Frame>) -> Fake {
    frames.insert(0, reply(1, 10002, true, &123_i64.to_le_bytes()));
    Fake {
        replies: frames.into(),
        sent: vec![],
    }
}

#[test]
fn snapshot_validates_account_and_reads_each_section_with_fresh_sequences() {
    let position = include_bytes!("fixtures/position.bin");
    let order = include_bytes!("fixtures/order.bin");
    let trade = include_bytes!("fixtures/trade.bin");
    let mut parts = vec![
        reply(2, 30001, true, include_bytes!("fixtures/asset.bin")),
        reply(3, 30004, true, position),
        reply(4, 30002, true, order),
    ];
    for (offset, chunk) in trade.chunks(300).enumerate() {
        let mut body = vec![];
        body.extend(1_u32.to_le_bytes());
        body.extend(30003_u32.to_le_bytes());
        body.extend(552_u64.to_le_bytes());
        body.extend((chunk.len() as u64).to_le_bytes());
        body.extend((offset as u64 * 300).to_le_bytes());
        body.extend([0; 6]);
        body.extend(chunk);
        parts.push(reply(5, 10009, offset == 1, &body));
    }
    let q = queue(parts);
    let mut client = AccountConnection::connect(q, "A", 123, Duration::from_secs(1)).unwrap();
    let snapshot = client
        .query(Operation::Snapshot, Duration::from_secs(1))
        .unwrap();
    assert_eq!(snapshot["asset"]["cash"], 100.5);
    assert_eq!(
        snapshot["positions"][0]["volume"].as_i64(),
        Some(1_i64 << 33)
    );
    assert_eq!(snapshot["orders"][0]["order_id"], 0);
    assert_eq!(snapshot["trades"][0]["traded_id"], "TRADE01");
    let q = client.into_queue();
    assert_eq!(
        q.sent.iter().map(|f| f.kind).collect::<Vec<_>>(),
        [10001, 20005, 20008, 20006, 20007]
    );
    assert_eq!(
        q.sent.iter().map(|f| f.sequence).collect::<Vec<_>>(),
        [1, 2, 3, 4, 5]
    );
}

#[test]
fn empty_list_requires_successful_account_validation_and_negative_one_completion() {
    let q = queue(vec![
        reply(2, 30001, true, include_bytes!("fixtures/asset.bin")),
        reply(3, 20000, true, &(-1_i64).to_le_bytes()),
    ]);
    let mut c = AccountConnection::connect(q, "A", 123, Duration::from_secs(1)).unwrap();
    assert_eq!(
        c.query(Operation::Positions, Duration::from_secs(1))
            .unwrap()["positions"],
        serde_json::json!([])
    );
    let q = queue(vec![reply(2, 20000, true, &(-1_i64).to_le_bytes())]);
    let mut c = AccountConnection::connect(q, "A", 123, Duration::from_secs(1)).unwrap();
    assert!(
        c.query(Operation::Positions, Duration::from_secs(1))
            .is_err()
    );
    assert!(c.query(Operation::Asset, Duration::from_secs(1)).is_err());
}

#[test]
fn wrong_session_and_invalid_fragment_fail_closed() {
    let mut wrong = reply(2, 30001, true, include_bytes!("fixtures/asset.bin"));
    wrong.session = 124;
    let mut c =
        AccountConnection::connect(queue(vec![wrong]), "A", 123, Duration::from_secs(1)).unwrap();
    assert!(c.query(Operation::Asset, Duration::from_secs(1)).is_err());
    let q = queue(vec![
        reply(2, 30001, true, include_bytes!("fixtures/asset.bin")),
        reply(3, 10009, true, &[0; 38]),
    ]);
    let mut c = AccountConnection::connect(q, "A", 123, Duration::from_secs(1)).unwrap();
    assert!(c.query(Operation::Trades, Duration::from_secs(1)).is_err());
}

#[test]
fn stale_response_is_not_used_as_current_asset_and_writes_cannot_be_encoded() {
    let mut old = include_bytes!("fixtures/asset.bin").to_vec();
    old[28..36].copy_from_slice(&9999_f64.to_le_bytes());
    let q = queue(vec![
        reply(1, 30001, true, &old),
        reply(2, 30001, true, include_bytes!("fixtures/asset.bin")),
    ]);
    let mut c = AccountConnection::connect(q, "A", 123, Duration::from_secs(1)).unwrap();
    assert_eq!(
        c.query(Operation::Asset, Duration::from_secs(1)).unwrap()["asset"]["cash"],
        100.5
    );
    assert!(qmt_trade::protocol::encode_request(1, 20001, 123, &[0; 28]).is_err());
    assert!(Operation::parse("order_stock").is_err());
}

#[test]
fn invalid_action_and_incomplete_or_overlapping_fragments_poison_the_connection() {
    let mut action = reply(2, 30001, true, include_bytes!("fixtures/asset.bin"));
    action.action = 2;
    let mut c =
        AccountConnection::connect(queue(vec![action]), "A", 123, Duration::from_secs(1)).unwrap();
    assert!(c.query(Operation::Asset, Duration::from_secs(1)).is_err());
    for (offset, last) in [(0_u64, true), (1, false)] {
        let mut body = Vec::new();
        body.extend(1_u32.to_le_bytes());
        body.extend(30003_u32.to_le_bytes());
        body.extend(552_u64.to_le_bytes());
        body.extend(300_u64.to_le_bytes());
        body.extend(offset.to_le_bytes());
        body.extend([0; 6]);
        body.extend(&include_bytes!("fixtures/trade.bin")[..300]);
        let frames = vec![
            reply(2, 30001, true, include_bytes!("fixtures/asset.bin")),
            reply(3, 10009, last, &body),
        ];
        let mut c =
            AccountConnection::connect(queue(frames), "A", 123, Duration::from_secs(1)).unwrap();
        assert!(c.query(Operation::Trades, Duration::from_secs(1)).is_err());
        assert!(c.query(Operation::Asset, Duration::from_secs(1)).is_err());
    }
}

#[test]
fn empty_completion_cannot_discard_rows_already_received() {
    let frames = vec![
        reply(2, 30001, true, include_bytes!("fixtures/asset.bin")),
        reply(3, 30004, false, include_bytes!("fixtures/position.bin")),
        reply(3, 20000, true, &(-1_i64).to_le_bytes()),
    ];
    let mut c =
        AccountConnection::connect(queue(frames), "A", 123, Duration::from_secs(1)).unwrap();
    assert!(
        c.query(Operation::Positions, Duration::from_secs(1))
            .is_err()
    );
}
