use qmt_trade::decode_asset;
use qmt_trade::{decode_order, decode_position, decode_trade, encode_account};
use serde_json::Value;

#[test]
fn all_four_codecs_match_verified_python_synthetic_fixtures() {
    type Decoder = fn(&[u8], &str) -> qmt_trade::Result<Value>;
    let cases: &[(Decoder, &[u8], &str)] = &[
        (
            decode_asset,
            include_bytes!("fixtures/asset.bin"),
            include_str!("fixtures/asset.json"),
        ),
        (
            decode_position,
            include_bytes!("fixtures/position.bin"),
            include_str!("fixtures/position.json"),
        ),
        (
            decode_order,
            include_bytes!("fixtures/order.bin"),
            include_str!("fixtures/order.json"),
        ),
        (
            decode_trade,
            include_bytes!("fixtures/trade.bin"),
            include_str!("fixtures/trade.json"),
        ),
    ];
    for &(decode, raw, expected) in cases {
        assert_eq!(
            decode(raw, "A").unwrap(),
            serde_json::from_str::<Value>(expected).unwrap()
        );
        assert!(decode(raw, "B").is_err());
        assert!(decode(&raw[..raw.len() - 1], "A").is_err());
    }
    let p = decode_position(include_bytes!("fixtures/position.bin"), "A").unwrap();
    assert_eq!(p["volume"].as_i64(), Some(1_i64 << 33));
}

#[test]
fn records_reject_invalid_utf8_and_negative_quantities() {
    let mut position = include_bytes!("fixtures/position.bin").to_vec();
    position[112] = 0xff;
    assert!(decode_position(&position, "A").is_err());
    position = include_bytes!("fixtures/position.bin").to_vec();
    position[44..52].copy_from_slice(&(-1_i64).to_le_bytes());
    assert!(decode_position(&position, "A").is_err());
    let mut order = include_bytes!("fixtures/order.bin").to_vec();
    order[60..64].copy_from_slice(&(-1_i32).to_le_bytes());
    assert!(decode_order(&order, "A").is_err());
    let mut trade = include_bytes!("fixtures/trade.bin").to_vec();
    trade[76..84].copy_from_slice(&f64::INFINITY.to_le_bytes());
    assert!(decode_trade(&trade, "A").is_err());
}

#[test]
fn account_input_is_bounded_and_stock_only() {
    assert!(encode_account("A", "STOCK").is_ok());
    assert!(encode_account(&"A".repeat(23), "stock").is_ok());
    for name in ["", " ", "A\n", "账户", &"A".repeat(24)] {
        assert!(encode_account(name, "STOCK").is_err());
    }
    assert!(encode_account("A", "CREDIT").is_err());
}

#[test]
fn asset_matches_existing_native_public_fields_and_rejects_other_account() {
    let mut raw = vec![0; 76];
    raw[..4].copy_from_slice(&2_i32.to_le_bytes());
    raw[4] = b'A';
    for (i, n) in [100.5_f64, 2.0, 200.0, 302.5, 0.0, 0.0]
        .into_iter()
        .enumerate()
    {
        raw[28 + i * 8..36 + i * 8].copy_from_slice(&n.to_le_bytes());
    }
    let asset = decode_asset(&raw, "A").unwrap();
    assert_eq!(asset["cash"], 100.5);
    assert_eq!(asset["total_asset"], 302.5);
    assert!(decode_asset(&raw, "B").is_err());
    assert!(decode_asset(&raw[..75], "A").is_err());
    raw[28..36].copy_from_slice(&f64::NAN.to_le_bytes());
    assert!(decode_asset(&raw, "A").is_err());
}
