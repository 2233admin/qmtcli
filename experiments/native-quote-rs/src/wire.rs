//! Observed, version-pinned local protocol, not a published official wire API.
use crate::Result;
use bson::{Bson, Document, doc};
use flate2::{Compression, Decompress, FlushDecompress, Status, write::ZlibEncoder};
use std::io::{Cursor, Read, Write};

const MAX_SIZE: usize = 16 * 1024 * 1024;
const MAX_PAYLOAD: usize = 64 * 1024 * 1024;

pub(crate) fn crc(body: &[u8]) -> u32 {
    let mut hash = crc32fast::Hasher::new_with_initial(0xffff_ffff);
    hash.update(body);
    hash.finalize()
}

pub(crate) fn encode(seq: u32, method: &str, params: Document) -> Result<Vec<u8>> {
    if !matches!(method, "authPid" | "getFullTick") {
        return Err("read-only quote method allowlist rejected request".into());
    }
    if method == "authPid" && params != doc! { "pid": std::process::id() as i32 } {
        return Err("authentication requires the actual caller PID".into());
    }
    let mut payload = doc! { "func": method, "params": params }.to_vec()?;
    let offset = 15 + method.len();
    if payload.get(offset..offset + 8) != Some(b"\x03params\0") {
        return Err("unexpected BSON request container".into());
    }
    // Change only the known params container; retain named elements, not 0/1 keys.
    payload[offset] = 4;
    let mut compressor = ZlibEncoder::new(Vec::new(), Compression::default());
    compressor.write_all(&payload)?;
    let mut body = compressor.finish()?;
    let flags: u16 = if method == "authPid" { 0x42 } else { 0x2042 };
    if flags & 0x2000 != 0 {
        body.extend(crc(&body).to_be_bytes());
    }
    let size = body.len() + 12;
    if size > MAX_SIZE {
        return Err("quote frame size exceeds limit".into());
    }
    let mut frame = Vec::with_capacity(size);
    frame.extend((size as u32).to_be_bytes());
    frame.extend(seq.to_be_bytes());
    frame.extend(3_u16.to_be_bytes());
    frame.extend(flags.to_be_bytes());
    frame.extend(body);
    Ok(frame)
}

pub(crate) fn request(
    io: &mut (impl Read + Write),
    seq: u32,
    method: &str,
    params: Document,
) -> Result<Document> {
    io.write_all(&encode(seq, method, params)?)?;
    read_reply(io, seq)
}

pub(crate) fn read_reply(reader: &mut impl Read, expected_seq: u32) -> Result<Document> {
    let mut header = [0_u8; 12];
    reader.read_exact(&mut header)?;
    let size = u32::from_be_bytes(header[..4].try_into()?) as usize;
    let seq = u32::from_be_bytes(header[4..8].try_into()?);
    let kind = u16::from_be_bytes(header[8..10].try_into()?);
    let flags = u16::from_be_bytes(header[10..12].try_into()?);
    if !(12..=MAX_SIZE).contains(&size) {
        return Err("invalid quote RPC frame size".into());
    }
    if seq != expected_seq {
        return Err("quote RPC reply sequence mismatch".into());
    }
    if kind != 3 || !matches!(flags, 0x42 | 0x2042) {
        return Err("unsupported quote RPC kind/flags".into());
    }
    let mut body = vec![0_u8; size - 12];
    reader.read_exact(&mut body)?;
    if flags & 0x2000 != 0 {
        let split = body.len().checked_sub(4).ok_or("missing quote RPC CRC")?;
        if u32::from_be_bytes(body[split..].try_into()?) != crc(&body[..split]) {
            return Err("quote RPC CRC mismatch".into());
        }
        body.truncate(split);
    }
    let decoded = inflate(&body, MAX_PAYLOAD)?;
    let mut cursor = Cursor::new(&decoded);
    let reply = Document::from_reader(&mut cursor)?;
    if cursor.position() != decoded.len() as u64 {
        return Err("trailing BSON data in quote reply".into());
    }
    if !matches!(reply.get("status"), Some(Bson::Int32(0) | Bson::Int64(0))) {
        return Err("native quote service rejected request".into());
    }
    Ok(reply.get_document("params")?.clone())
}

fn inflate(body: &[u8], limit: usize) -> Result<Vec<u8>> {
    let mut decoded = Vec::new();
    let mut inflater = Decompress::new(true);
    loop {
        let (before_in, before_out) = (inflater.total_in(), inflater.total_out());
        let mut chunk = [0_u8; 16 * 1024];
        let status = inflater.decompress(
            &body[before_in as usize..],
            &mut chunk,
            FlushDecompress::None,
        )?;
        let count = (inflater.total_out() - before_out) as usize;
        if decoded.len() + count > limit {
            return Err("invalid compressed quote RPC payload: decompression limit".into());
        }
        decoded.extend_from_slice(&chunk[..count]);
        if status == Status::StreamEnd {
            if inflater.total_in() != body.len() as u64 {
                return Err("invalid compressed quote RPC payload: trailing bytes".into());
            }
            return Ok(decoded);
        }
        if inflater.total_in() == before_in && count == 0 {
            return Err("invalid compressed quote RPC payload: incomplete stream".into());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn valid_payload_larger_than_one_output_chunk_roundtrips() {
        let value = "x".repeat(65537);
        let raw = frame(
            &doc! { "status": 0, "params": { "large": &value } }
                .to_vec()
                .unwrap(),
        );
        let reply = read_reply(&mut &raw[..], 1).unwrap();
        assert_eq!(reply.get_str("large").unwrap(), value);
    }

    fn frame(payload: &[u8]) -> Vec<u8> {
        let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
        encoder.write_all(payload).unwrap();
        let compressed = encoder.finish().unwrap();
        wrap_compressed(&compressed)
    }

    fn wrap_compressed(compressed: &[u8]) -> Vec<u8> {
        let mut raw = Vec::new();
        raw.extend(((compressed.len() + 16) as u32).to_be_bytes());
        raw.extend(1_u32.to_be_bytes());
        raw.extend(3_u16.to_be_bytes());
        raw.extend(0x2042_u16.to_be_bytes());
        raw.extend(compressed);
        raw.extend(crc(compressed).to_be_bytes());
        raw
    }

    fn reply() -> Vec<u8> {
        frame(&doc! { "status": 0, "params": { "result": { "600000.SH": { "time": 1793345411000_i64 } } } }.to_vec().unwrap())
    }

    struct Fragmented(Cursor<Vec<u8>>);
    impl Read for Fragmented {
        fn read(&mut self, buffer: &mut [u8]) -> std::io::Result<usize> {
            let count = buffer.len().min(3);
            self.0.read(&mut buffer[..count])
        }
    }

    #[test]
    fn fragmented_and_coalesced_replies_preserve_int64_and_next_frame() {
        let first = reply();
        let mut bytes = first.clone();
        bytes.extend(first);
        let mut reader = Fragmented(Cursor::new(bytes));
        for _ in 0..2 {
            let params = read_reply(&mut reader, 1).unwrap();
            assert_eq!(
                params
                    .get_document("result")
                    .unwrap()
                    .get_document("600000.SH")
                    .unwrap()
                    .get_i64("time")
                    .unwrap(),
                1793345411000
            );
        }
        assert!(read_reply(&mut reader, 1).is_err());
    }

    #[test]
    fn corrupt_crc_sequence_kind_size_and_truncation_fail() {
        let good = reply();
        let mut crc_bad = good.clone();
        *crc_bad.last_mut().unwrap() ^= 1;
        assert!(
            read_reply(&mut &crc_bad[..], 1)
                .unwrap_err()
                .to_string()
                .contains("CRC")
        );
        assert!(
            read_reply(&mut &good[..], 2)
                .unwrap_err()
                .to_string()
                .contains("sequence")
        );
        let mut kind_bad = good.clone();
        kind_bad[9] = 12;
        assert!(
            read_reply(&mut &kind_bad[..], 1)
                .unwrap_err()
                .to_string()
                .contains("unsupported")
        );
        let mut size_bad = good.clone();
        size_bad[..4].copy_from_slice(&((MAX_SIZE + 1) as u32).to_be_bytes());
        assert!(
            read_reply(&mut &size_bad[..], 1)
                .unwrap_err()
                .to_string()
                .contains("size")
        );
        assert!(read_reply(&mut &good[..good.len() - 1], 1).is_err());
    }

    #[test]
    fn rejected_status_and_malformed_params_are_not_empty_successes() {
        for doc in [
            doc! { "status": 1, "params": {} },
            doc! { "status": 0, "params": [] },
        ] {
            assert!(read_reply(&mut &frame(&doc.to_vec().unwrap())[..], 1).is_err());
        }
        let empty = frame(
            &doc! { "status": 0, "params": { "result": {} } }
                .to_vec()
                .unwrap(),
        );
        assert!(
            read_reply(&mut &empty[..], 1)
                .unwrap()
                .get_document("result")
                .unwrap()
                .is_empty()
        );
    }

    #[test]
    fn compressed_overflow_trailing_bytes_and_truncated_stream_fail() {
        let bomb = frame(&vec![b'x'; 1025]);
        assert!(
            inflate(&bomb[12..bomb.len() - 4], 1024)
                .unwrap_err()
                .to_string()
                .contains("compressed")
        );
        let good = reply();
        let compressed = &good[12..good.len() - 4];
        let mut with_trailer = compressed.to_vec();
        with_trailer.extend(b"trailer");
        assert!(
            read_reply(&mut &wrap_compressed(&with_trailer)[..], 1)
                .unwrap_err()
                .to_string()
                .contains("compressed")
        );
        assert!(
            read_reply(
                &mut &wrap_compressed(&compressed[..compressed.len() - 1])[..],
                1
            )
            .is_err()
        );
    }
}
