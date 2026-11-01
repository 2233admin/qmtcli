use serde_json::{Value, json};
use std::io::Write;
use std::process::{Command, Stdio};

#[test]
fn discovery_does_not_require_qmt_and_only_advertises_implemented_transports() {
    let result = Command::new(env!("CARGO_BIN_EXE_qmtcli-rs"))
        .arg("capabilities")
        .output()
        .unwrap();
    assert!(result.status.success());
    let value: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(value["ok"], true);
    let names = value["data"]["commands"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v["name"].as_str().unwrap())
        .collect::<Vec<_>>();
    assert!(names.contains(&"full-tick"));
    assert_eq!(
        names.contains(&"account-snapshot"),
        qmt_trade::TRANSPORT_AVAILABLE
    );
    assert!(!names.contains(&"account-subscribe"));
}

#[test]
#[cfg(windows)]
fn account_requests_are_discovered_and_validate_identity_before_loading_native_code() {
    let mut runtime = qmtcli_rs::Runtime::default();
    let cap = runtime.handle(&json!({"command":"capabilities"}));
    assert!(
        cap["data"]["commands"]
            .as_array()
            .unwrap()
            .iter()
            .any(|v| v["name"] == "account-snapshot")
    );
    let result=runtime.handle(&json!({"id":55,"command":"account_snapshot","backend":"native","path":"missing-root","account":"A","account_type":"CREDIT"}));
    assert_eq!(result["ok"], false);
    assert_eq!(result["id"], 55);
    assert!(result["error"].as_str().unwrap().contains("STOCK"));
}

#[test]
fn jsonl_reports_bad_inputs_then_continues_and_echoes_ids() {
    let mut child = Command::new(env!("CARGO_BIN_EXE_qmtcli-rs"))
        .arg("server")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let mut input = child.stdin.take().unwrap();
    writeln!(input, "not-json").unwrap();
    writeln!(input, "[]").unwrap();
    writeln!(input, "{}", json!({"id":"ready", "command":"capabilities"})).unwrap();
    writeln!(
        input,
        "{}",
        json!({"id":4, "command":"full_tick", "backend":"sdk", "symbols":["600000.SH"]})
    )
    .unwrap();
    drop(input);
    let output = child.wait_with_output().unwrap();
    assert!(output.status.success());
    let rows = String::from_utf8(output.stdout)
        .unwrap()
        .lines()
        .map(|s| serde_json::from_str::<Value>(s).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(rows.len(), 4);
    assert_eq!(rows[0]["ok"], false);
    assert_eq!(rows[1]["ok"], false);
    assert_eq!(rows[2]["id"], "ready");
    assert_eq!(rows[2]["ok"], true);
    assert_eq!(rows[3]["id"], 4);
    assert_eq!(rows[3]["ok"], false);
}

#[test]
fn rpc_failure_uses_json_stdout_and_nonzero_exit() {
    let result = Command::new(env!("CARGO_BIN_EXE_qmtcli-rs"))
        .args([
            "rpc",
            r#"{"id":7,"command":"full_tick","backend":"native","symbols":[]}"#,
        ])
        .output()
        .unwrap();
    assert!(!result.status.success());
    let value: Value = serde_json::from_slice(&result.stdout).unwrap();
    assert_eq!(value["ok"], false);
    assert_eq!(value["id"], 7);
}

#[test]
fn oversized_line_is_discarded_without_losing_next_request() {
    let mut input = vec![b'x'; qmtcli_rs::MAX_REQUEST_BYTES + 100];
    input.extend_from_slice(b"\n{\"id\":9,\"command\":\"status\"}\n");
    let mut output = Vec::new();
    qmtcli_rs::serve(std::io::Cursor::new(input), &mut output).unwrap();
    let lines = String::from_utf8(output).unwrap();
    let values = lines
        .lines()
        .map(|s| serde_json::from_str::<Value>(s).unwrap())
        .collect::<Vec<_>>();
    assert_eq!(values.len(), 2);
    assert_eq!(values[0]["ok"], false);
    assert_eq!(values[1]["id"], 9);
    assert_eq!(values[1]["ok"], true);
}
