//! Owned loopback fixtures only: never connect to a broker or run a strategy.
use super::*;
use flate2::{Compression, read::ZlibDecoder, write::ZlibEncoder};
use std::{net::TcpListener, thread};

fn request(stream: &mut TcpStream) -> (u32, Document) {
    let mut header = [0; 12];
    stream.read_exact(&mut header).unwrap();
    let size = u32::from_be_bytes(header[..4].try_into().unwrap()) as usize;
    assert!((12..4096).contains(&size));
    let flags = u16::from_be_bytes(header[10..].try_into().unwrap());
    let mut body = vec![0; size - 12];
    stream.read_exact(&mut body).unwrap();
    if flags & 0x2000 != 0 {
        let split = body.len() - 4;
        assert_eq!(
            u32::from_be_bytes(body[split..].try_into().unwrap()),
            wire::crc(&body[..split])
        );
        body.truncate(split);
    }
    let mut raw = Vec::new();
    ZlibDecoder::new(&body[..]).read_to_end(&mut raw).unwrap();
    let tag = raw.windows(8).position(|b| b == b"\x04params\0").unwrap();
    raw[tag] = 3;
    (
        u32::from_be_bytes(header[4..8].try_into().unwrap()),
        Document::from_reader(&mut &raw[..]).unwrap(),
    )
}

fn response(seq: u32, params: Document) -> Vec<u8> {
    let mut compressor = ZlibEncoder::new(Vec::new(), Compression::default());
    compressor
        .write_all(&doc! { "status": 0, "params": params }.to_vec().unwrap())
        .unwrap();
    let mut body = compressor.finish().unwrap();
    body.extend(wire::crc(&body).to_be_bytes());
    let mut frame = Vec::new();
    frame.extend(((body.len() + 12) as u32).to_be_bytes());
    frame.extend(seq.to_be_bytes());
    frame.extend(3_u16.to_be_bytes());
    frame.extend(0x2042_u16.to_be_bytes());
    frame.extend(body);
    frame
}

fn fixture(
    action: impl FnOnce(TcpStream) + Send + 'static,
    timeout: Duration,
) -> (QuoteSession, thread::JoinHandle<()>) {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
    let address = listener.local_addr().unwrap();
    let worker = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let (seq, auth) = request(&mut stream);
        assert_eq!(seq, 1);
        assert_eq!(auth.get_str("func").unwrap(), "authPid");
        assert_eq!(
            auth.get_document("params").unwrap().get_i32("pid").unwrap(),
            std::process::id() as i32
        );
        stream
            .write_all(&response(seq, doc! { "success": true }))
            .unwrap();
        action(stream);
    });
    let stream = TcpStream::connect_timeout(&address, Duration::from_secs(1)).unwrap();
    let session =
        QuoteSession::authenticate(stream, timeout, Instant::now() + Duration::from_secs(1))
            .unwrap();
    (session, worker)
}

#[test]
fn session_reuses_auth_reads_fresh_values_and_closes_after_peer_eof() {
    let (mut session, worker) = fixture(
        |mut stream| {
            for seq in [2, 3] {
                let (got, query) = request(&mut stream);
                assert_eq!(got, seq);
                assert_eq!(query.get_str("func").unwrap(), "getFullTick");
                let mut heartbeat = Vec::new();
                heartbeat.extend(16_u32.to_be_bytes());
                heartbeat.extend(0xffffffff_u32.to_be_bytes());
                heartbeat.extend(1_u16.to_be_bytes());
                heartbeat.extend(0x2e40_u16.to_be_bytes());
                heartbeat.extend(wire::crc(&[]).to_be_bytes());
                let mut reply = heartbeat;
                reply.extend(response(
                    seq,
                    doc! { "result": { "600000.SH": { "time": i64::from(seq) } } },
                ));
                // Split/coalesce across frame boundaries deliberately.
                stream.write_all(&reply[..7]).unwrap();
                stream.write_all(&reply[7..]).unwrap();
            }
            let (seq, _) = request(&mut stream);
            assert_eq!(seq, 4);
        },
        Duration::from_secs(1),
    );
    assert!(session.get_full_tick(&[]).is_err()); // Input error preserves the healthy socket.
    for seq in [2, 3] {
        assert_eq!(
            session
                .get_full_tick(&["600000.SH"])
                .unwrap()
                .get_document("600000.SH")
                .unwrap()
                .get_i64("time")
                .unwrap(),
            seq
        );
    }
    assert!(session.get_full_tick(&["600000.SH"]).is_err());
    assert!(
        session
            .get_full_tick(&["600000.SH"])
            .unwrap_err()
            .to_string()
            .contains("closed")
    );
    worker.join().unwrap();
}

#[test]
fn timeout_invalidates_socket_and_does_not_replay() {
    let (mut session, worker) = fixture(
        |mut stream| {
            assert_eq!(request(&mut stream).0, 2);
            thread::sleep(Duration::from_millis(250));
            let mut b = [0];
            assert_eq!(stream.read(&mut b).unwrap(), 0);
        },
        Duration::from_millis(100),
    );
    assert!(session.get_full_tick(&["600000.SH"]).is_err());
    assert!(
        session
            .get_full_tick(&["600000.SH"])
            .unwrap_err()
            .to_string()
            .contains("closed")
    );
    worker.join().unwrap();
}

#[test]
fn malformed_result_invalidates_session() {
    let (mut session, worker) = fixture(
        |mut stream| {
            let (seq, _) = request(&mut stream);
            stream
                .write_all(&response(seq, doc! { "result": { "UNREQUESTED": {} } }))
                .unwrap();
            assert_eq!(stream.read(&mut [0]).unwrap(), 0);
        },
        Duration::from_secs(1),
    );
    assert!(
        session
            .get_full_tick(&["600000.SH"])
            .unwrap_err()
            .to_string()
            .contains("symbol mapping")
    );
    assert!(
        session
            .get_full_tick(&["600000.SH"])
            .unwrap_err()
            .to_string()
            .contains("closed")
    );
    worker.join().unwrap();
}

#[test]
fn explicit_reconnect_authenticates_again_and_restarts_sequence() {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
    let address = listener.local_addr().unwrap();
    let worker = thread::spawn(move || {
        for attempt in 0..2 {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            let (seq, auth) = request(&mut stream);
            assert_eq!(seq, 1);
            assert_eq!(auth.get_str("func").unwrap(), "authPid");
            stream
                .write_all(&response(seq, doc! { "success": true }))
                .unwrap();
            let (seq, query) = request(&mut stream);
            assert_eq!(seq, 2);
            assert_eq!(query.get_str("func").unwrap(), "getFullTick");
            if attempt == 1 {
                stream
                    .write_all(&response(seq, doc! { "result": {} }))
                    .unwrap();
                assert_eq!(stream.read(&mut [0]).unwrap(), 0);
            }
        }
    });
    let connect = || {
        QuoteSession::authenticate(
            TcpStream::connect(address).unwrap(),
            Duration::from_secs(1),
            Instant::now() + Duration::from_secs(1),
        )
        .unwrap()
    };
    let mut first = connect();
    assert!(first.get_full_tick(&["600000.SH"]).is_err());
    assert!(
        first
            .get_full_tick(&["600000.SH"])
            .unwrap_err()
            .to_string()
            .contains("closed")
    );
    let mut second = connect();
    assert!(second.get_full_tick(&["600000.SH"]).unwrap().is_empty());
    drop(second);
    worker.join().unwrap();
}

#[test]
fn sequence_exhaustion_closes_socket_without_wrapping() {
    let (mut session, worker) = fixture(
        |mut stream| {
            assert_eq!(stream.read(&mut [0]).unwrap(), 0);
        },
        Duration::from_secs(1),
    );
    session.sequence = u32::MAX;
    assert!(
        session
            .get_full_tick(&["600000.SH"])
            .unwrap_err()
            .to_string()
            .contains("exhausted")
    );
    assert!(
        session
            .get_full_tick(&["600000.SH"])
            .unwrap_err()
            .to_string()
            .contains("closed")
    );
    worker.join().unwrap();
}

#[test]
fn rejected_authentication_releases_connection() {
    let listener = TcpListener::bind((Ipv4Addr::LOCALHOST, 0)).unwrap();
    let address = listener.local_addr().unwrap();
    let worker = thread::spawn(move || {
        let (mut stream, _) = listener.accept().unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(2)))
            .unwrap();
        let (seq, _) = request(&mut stream);
        stream
            .write_all(&response(seq, doc! { "success": false }))
            .unwrap();
        assert_eq!(stream.read(&mut [0]).unwrap(), 0);
    });
    let result = QuoteSession::authenticate(
        TcpStream::connect(address).unwrap(),
        Duration::from_secs(1),
        Instant::now() + Duration::from_secs(1),
    );
    assert!(
        result
            .err()
            .unwrap()
            .to_string()
            .contains("authentication rejected")
    );
    worker.join().unwrap();
}
