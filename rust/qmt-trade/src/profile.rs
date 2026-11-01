//! Match the previously verified Python account runtime before loading any DLL.
use crate::Result;
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
pub struct Paths {
    pub data: PathBuf,
    pub bin: PathBuf,
}
pub fn validate(path: &Path) -> Result<Paths> {
    if !cfg!(all(windows, target_pointer_width = "64")) {
        return Err("native account requires Windows x64".into());
    }
    let given = path.canonicalize()?;
    let data = if given.file_name().is_some_and(|n| n == "userdata_mini") {
        given
    } else {
        given.join("userdata_mini")
    };
    if !data.is_dir() {
        return Err("requires an installed MiniQMT root or userdata_mini".into());
    }
    let bin = data.parent().ok_or("invalid MiniQMT path")?.join("bin.x64");
    for (name, expected) in [
        (
            "ringbuffer.dll",
            "b40def1af839286baaf6b8bdcde7c88a0c555dbfb56d9bb3592661db84922c48",
        ),
        (
            "XtQuantServer.dll",
            "6dc0474701691e5be22d501f92cc36c75e13d9f24781debc69fe90dfaf4b4050",
        ),
        (
            "OrderService_mini.dll",
            "1443f023b59b71386700236400cd77367587e7afde7c29476272407212d266f0",
        ),
    ] {
        let actual = Sha256::digest(std::fs::read(bin.join(name))?)
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect::<String>();
        if actual != expected {
            return Err(format!("unsupported MiniQMT account runtime: {name}").into());
        }
    }
    Ok(Paths { data, bin })
}
