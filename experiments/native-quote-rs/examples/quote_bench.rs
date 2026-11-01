//! Benchmark adapter only. Talks exclusively to an explicitly selected loopback fixture.
use bson::{Bson, Document};
use qmt_native_quote_experiment::{QuoteClient, QuoteSession, Result};
use serde_json::{Value, json};
use std::{
    hint::black_box,
    io::{self, BufRead, Cursor},
    time::{Duration, Instant},
};

#[allow(dead_code)]
#[path = "../src/wire.rs"]
mod wire;

fn codes(count: usize) -> Vec<String> {
    if count == 2 {
        vec!["600000.SH".into(), "000001.SZ".into()]
    } else {
        (0..count)
            .map(|i| format!("{:06}.SH", 600000 + i))
            .collect()
    }
}

fn batch(session: &mut QuoteSession, command: &Value) -> Result<Value> {
    let count = command["count"].as_u64().ok_or("count")? as usize;
    let iterations = command["iterations"].as_u64().ok_or("iterations")? as usize;
    let warmup = command["warmup"].as_u64().unwrap_or(3) as usize;
    if !matches!(count, 2 | 1000) || !(1..=5000).contains(&iterations) || warmup > 20 {
        return Err("invalid benchmark bounds".into());
    }
    let mode = command["mode"].as_str().ok_or("mode")?;
    if !matches!(mode, "snapshot" | "json" | "decode") {
        return Err("invalid benchmark mode".into());
    }
    let symbols = codes(count);
    let symbols = symbols.iter().map(String::as_str).collect::<Vec<_>>();
    let frame = if mode == "decode" {
        std::fs::read(command["frame_path"].as_str().ok_or("frame_path")?)?
    } else {
        Vec::new()
    };
    let mut durations = Vec::new();
    let mut output_bytes = 0;
    for i in 0..warmup + iterations {
        let clock = Instant::now();
        let result: Document = if mode == "decode" {
            wire::read_reply(&mut Cursor::new(&frame), 1)?
                .get_document("result")?
                .clone()
        } else {
            session.get_full_tick(&symbols)?
        };
        if result.len() != count {
            return Err("incorrect row count".into());
        }
        let first = result.get_document("600000.SH")?;
        if first.len() != 18
            || first.get_i64("time")? != 1793345400000
            || first.get_array("bidPrice")?.len() != 5
        {
            return Err("incorrect fixture result".into());
        }
        let encoded = if mode == "json" {
            Some(serde_json::to_vec(
                &Bson::Document(result).into_relaxed_extjson(),
            )?)
        } else {
            black_box(result);
            None
        };
        black_box(&encoded);
        let ns = clock.elapsed().as_nanos() as u64;
        if i >= warmup {
            durations.push(ns);
            output_bytes += encoded.as_ref().map_or(0, Vec::len);
        }
    }
    Ok(
        json!({"iterations":iterations,"count":count,"mode":mode,"samples_ns":durations,"output_bytes":output_bytes,"errors":0}),
    )
}

fn run() -> Result<()> {
    let args = std::env::args().skip(1).collect::<Vec<_>>();
    if args.len() < 2 {
        return Err("usage: quote_bench <root> <fixture-port> [--once]".into());
    }
    let mut session = QuoteClient::new(&args[0])
        .with_port(args[1].parse()?)
        .with_timeout(Duration::from_secs(10))
        .connect()?;
    println!(
        "READY:{}",
        json!({"pid":std::process::id(),"runtime":if cfg!(debug_assertions) {"rust-debug"} else {"rust-release"}})
    );
    if args.iter().any(|arg| arg == "--once") {
        let result = batch(
            &mut session,
            &json!({"count":2,"mode":"json","iterations":1,"warmup":0}),
        )?;
        println!("BENCH:{result}");
        return Ok(());
    }
    for line in io::stdin().lock().lines() {
        let command: Value = serde_json::from_str(&line?)?;
        let result = batch(&mut session, &command)?;
        println!("BENCH:{result}");
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
