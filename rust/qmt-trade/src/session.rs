//! Parent-side supervision. This module never loads the vendor DLL.
use crate::{
    Result, encode_account, profile,
    protocol::Operation,
    windows::{self, Job},
    worker::{MARKER, MAX_LINE},
};
use serde_json::{Value, json};
use std::os::windows::process::CommandExt;
use std::{
    fs::OpenOptions,
    io::{BufRead, BufReader, Read, Write},
    path::{Path, PathBuf},
    process::{Child, ChildStdin, Command, Stdio},
    sync::mpsc::{self, Receiver},
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

struct Worker {
    child: Child,
    input: Option<ChildStdin>,
    messages: Option<Receiver<std::result::Result<Value, String>>>,
    reader: Option<JoinHandle<()>>,
    job: Option<Job>,
    reply: Option<PathBuf>,
}
impl Worker {
    fn start(
        command: &mut Command,
        init: &Value,
        deadline: Instant,
        reply: Option<PathBuf>,
    ) -> Result<Self> {
        let mut child = match command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .creation_flags(0x08000000)
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                if let Some(path) = reply {
                    let _ = std::fs::remove_file(path);
                }
                return Err(e.into());
            }
        };
        let job = match Job::attach(&child) {
            Ok(job) => job,
            Err(e) => {
                let _ = child.kill();
                let _ = child.wait();
                if let Some(path) = reply {
                    let _ = std::fs::remove_file(path);
                }
                return Err(e);
            }
        };
        let stdout = child.stdout.take().ok_or("worker stdout missing")?;
        let (tx, rx) = mpsc::sync_channel(4);
        let reader = thread::spawn(move || {
            let mut input = BufReader::new(stdout);
            loop {
                let mut line = Vec::new();
                match (&mut input)
                    .take((MAX_LINE + 1) as u64)
                    .read_until(b'\n', &mut line)
                {
                    Ok(0) => {
                        let _ = tx.send(Err("native worker exited".into()));
                        break;
                    }
                    Ok(n) if n <= MAX_LINE => {
                        if let Some(raw) = line.strip_prefix(MARKER.as_bytes()) {
                            let value = serde_json::from_slice(raw)
                                .map_err(|_| "native worker returned invalid JSON".to_owned());
                            if tx.send(value).is_err() {
                                break;
                            }
                        }
                    }
                    _ => {
                        let _ = tx.send(Err("invalid/oversized worker output".into()));
                        break;
                    }
                }
            }
        });
        let input = child.stdin.take();
        let mut worker = Self {
            child,
            input,
            messages: Some(rx),
            reader: Some(reader),
            job: Some(job),
            reply,
        };
        worker.send(init)?;
        let ready = worker.receive(deadline)?;
        if ready["ready"] != true || ready["pid"].as_u64() != Some(worker.child.id() as u64) {
            return Err(ready["error"]
                .as_str()
                .unwrap_or("invalid worker initialization acknowledgement")
                .to_owned()
                .into());
        }
        Ok(worker)
    }
    fn send(&mut self, value: &Value) -> Result<()> {
        let input = self.input.as_mut().ok_or("native worker input closed")?;
        serde_json::to_writer(&mut *input, value)?;
        input.write_all(b"\n")?;
        input.flush()?;
        Ok(())
    }
    fn receive(&self, deadline: Instant) -> Result<Value> {
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .ok_or("native worker response deadline exceeded")?;
        self.messages
            .as_ref()
            .ok_or("worker reader closed")?
            .recv_timeout(remaining)
            .map_err(|_| "native worker response deadline exceeded")?
            .map_err(Into::into)
    }
    fn request(&mut self, id: u64, operation: Operation, deadline: Instant) -> Result<Value> {
        let remaining = deadline
            .checked_duration_since(Instant::now())
            .ok_or("account request deadline exceeded")?;
        self.send(
            &json!({"id":id,"operation":operation.as_str(),"timeout":remaining.as_secs_f64()}),
        )?;
        let reply = self.receive(deadline)?;
        if reply["id"].as_u64() != Some(id) {
            return Err("native worker response id mismatch".into());
        }
        if reply["ok"] != true || !reply["data"].is_object() {
            return Err(reply["error"]
                .as_str()
                .unwrap_or("invalid native worker result")
                .to_owned()
                .into());
        }
        Ok(reply["data"].clone())
    }
    fn connected(&mut self) -> bool {
        matches!(self.child.try_wait(), Ok(None))
    }
}
impl Drop for Worker {
    fn drop(&mut self) {
        self.input.take();
        // Closing this non-inherited job kills only the worker and its children.
        self.job.take();
        let _ = self.child.wait();
        self.messages.take(); // Unblock a reader waiting on a full bounded channel.
        if let Some(reader) = self.reader.take() {
            let _ = reader.join();
        }
        if let Some(reply) = self.reply.take() {
            let _ = std::fs::remove_file(reply);
        }
    }
}

#[derive(Default)]
pub struct AccountSession {
    worker: Option<Worker>,
    key: Option<(PathBuf, String)>,
    generation: u64,
    request: u64,
}
impl AccountSession {
    pub fn connected(&mut self) -> bool {
        self.worker.as_mut().is_some_and(Worker::connected)
    }
    pub fn generation(&self) -> u64 {
        self.generation
    }
    pub fn close(&mut self) {
        self.worker = None;
        self.key = None;
    }
    pub fn query(
        &mut self,
        path: &Path,
        account: &str,
        account_type: &str,
        operation: Operation,
        timeout: Duration,
    ) -> Result<Value> {
        encode_account(account, account_type)?;
        if timeout < Duration::from_millis(100) || timeout > Duration::from_secs(60) {
            return Err("account timeout must be 0.1 to 60 seconds".into());
        }
        let started = time::OffsetDateTime::now_utc()
            .format(&time::format_description::well_known::Rfc3339)?;
        let clock = Instant::now();
        let result = self.query_inner(path, account, operation, timeout);
        match result {
            Ok(mut data) => {
                if matches!(operation, Operation::Snapshot) {
                    if !data["asset"].is_object()
                        || ["positions", "orders", "trades"]
                            .iter()
                            .any(|key| !data[*key].is_array())
                    {
                        self.close();
                        return Err("incomplete native snapshot".into());
                    }
                    data["meta"] = json!({"started_at":started,"finished_at":time::OffsetDateTime::now_utc().format(&time::format_description::well_known::Rfc3339)?,
                        "duration_ms":clock.elapsed().as_secs_f64()*1000.0,"atomic":false,"backend":"native",
                        "asset_backend":"native","positions_backend":"native","orders_backend":"native","trades_backend":"native",
                        "generation":0,"native_generation":self.generation,"sequence_start":0,"sequence_end":0,"event_sequence_available":false});
                }
                Ok(data)
            }
            Err(e) => {
                self.close();
                Err(e)
            }
        }
    }
    fn query_inner(
        &mut self,
        path: &Path,
        account: &str,
        operation: Operation,
        timeout: Duration,
    ) -> Result<Value> {
        let given = path.canonicalize()?;
        let data = if given.file_name().is_some_and(|n| n == "userdata_mini") {
            given
        } else {
            given.join("userdata_mini")
        };
        let key = (data.clone(), account.to_owned());
        if self.key.as_ref() != Some(&key) || !self.connected() {
            self.close();
            let paths = profile::validate(&data)?;
            if !paths.data.join("up_queue_xtquant").is_file() {
                return Err(
                    "MiniQMT native service queue is missing; start and log in to MiniQMT".into(),
                );
            }
            let deadline = Instant::now() + timeout;
            let executable = std::env::current_exe()?;
            let generation = self
                .generation
                .checked_add(1)
                .ok_or("account generation exhausted")?;
            let (session, owner, reply) = reserve(&paths.data)?;
            self.generation = generation;
            let init = json!({"path":paths.data,"account":account,"session":session,"owner":owner,
                "timeout":deadline.saturating_duration_since(Instant::now()).as_secs_f64()});
            let mut command = Command::new(executable);
            command.arg("--internal-account-worker");
            self.worker = Some(Worker::start(&mut command, &init, deadline, Some(reply))?);
            self.key = Some(key);
            self.request = self
                .request
                .checked_add(1)
                .ok_or("account request id exhausted")?;
            return self
                .worker
                .as_mut()
                .ok_or("missing native worker")?
                .request(self.request, operation, deadline);
        }
        self.request = self
            .request
            .checked_add(1)
            .ok_or("account request id exhausted")?;
        self.worker
            .as_mut()
            .ok_or("missing native worker")?
            .request(self.request, operation, Instant::now() + timeout)
    }
}

fn reserve(data: &Path) -> Result<(u64, String, PathBuf)> {
    for _ in 0..16 {
        let random = windows::random()?;
        let session = (u32::from_le_bytes(random[..4].try_into()?) & 0x7fff_ffff) as u64;
        if session == 0 {
            continue;
        }
        let owner = random[8..]
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        let path = data.join(format!("down_queue_{session}"));
        match OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut file) => {
                if let Err(e) = file.write_all(format!("qmtcli-native-owner:{owner}").as_bytes()) {
                    let _ = std::fs::remove_file(&path);
                    return Err(e.into());
                }
                return Ok((session, owner, path));
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e.into()),
        }
    }
    Err("could not reserve a private native reply queue".into())
}

#[cfg(test)]
mod tests {
    use super::*;

    // A test-only child executable mode; no production environment override.
    #[test]
    #[ignore]
    fn fixture_child() {
        if std::env::var("QMTCLI_TEST_CHILD").ok().as_deref() != Some("yes") {
            return;
        }
        let mut input = std::io::stdin().lock();
        let init = crate::worker::read_message(&mut input).unwrap().unwrap();
        crate::worker::emit(&json!({"ready":true,"pid":std::process::id()})).unwrap();
        while let Some(request) = crate::worker::read_message(&mut input).unwrap() {
            if init["mode"] == "hang" {
                loop {
                    std::thread::sleep(Duration::from_secs(1));
                }
            }
            if init["mode"] == "invalid" {
                println!("{MARKER}not-json");
                continue;
            }
            let id =
                request["id"].as_u64().unwrap() + if init["mode"] == "wrong-id" { 1 } else { 0 };
            crate::worker::emit(&json!({"id":id,"ok":true,"data":{"asset":{"account_id":"A"}}}))
                .unwrap();
        }
    }
    fn start(mode: &str) -> Worker {
        let mut command = Command::new(std::env::current_exe().unwrap());
        command
            .args([
                "--ignored",
                "--exact",
                "session::tests::fixture_child",
                "--format",
                "terse",
                "--nocapture",
            ])
            .env("QMTCLI_TEST_CHILD", "yes");
        Worker::start(
            &mut command,
            &json!({"mode":mode}),
            Instant::now() + Duration::from_secs(5),
            None,
        )
        .unwrap()
    }
    #[test]
    fn worker_reuses_process_and_correlates_forty_responses() {
        let mut worker = start("echo");
        let pid = worker.child.id();
        for id in 1..=40 {
            let data = worker
                .request(
                    id,
                    Operation::Asset,
                    Instant::now() + Duration::from_secs(2),
                )
                .unwrap();
            assert_eq!(data["asset"]["account_id"], "A");
            assert_eq!(worker.child.id(), pid);
        }
    }
    #[test]
    fn timed_out_worker_is_killed_by_its_owned_job() {
        let mut worker = start("hang");
        let clock = Instant::now();
        assert!(
            worker
                .request(1, Operation::Snapshot, clock + Duration::from_millis(100))
                .is_err()
        );
        assert!(worker.child.try_wait().unwrap().is_none());
        worker.job.take();
        // Job kill-on-close does not promise a nonzero status. Check that the
        // previously running child terminates; the request itself failed above.
        let _ = worker.child.wait().unwrap();
        assert!(worker.child.try_wait().unwrap().is_some());
        assert!(clock.elapsed() < Duration::from_secs(3));
    }
    #[test]
    fn wrong_ids_and_malformed_worker_output_are_errors() {
        for mode in ["wrong-id", "invalid"] {
            let mut worker = start(mode);
            assert!(
                worker
                    .request(1, Operation::Asset, Instant::now() + Duration::from_secs(2))
                    .is_err()
            );
        }
    }
}
