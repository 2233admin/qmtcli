//! Win32 ownership and the pinned vendor ABI. Loaded only by private worker code.
use crate::{
    Result,
    protocol::{Frame, Queue},
};
use std::{
    ffi::{CStr, c_void},
    fs::{File, OpenOptions},
    os::windows::{ffi::OsStrExt, io::AsRawHandle},
    path::Path,
    ptr, thread,
    time::Duration,
    time::Instant,
};
use windows_sys::Win32::{
    Foundation::{CloseHandle, HANDLE, HMODULE},
    Security::Cryptography::{BCRYPT_USE_SYSTEM_PREFERRED_RNG, BCryptGenRandom},
    System::{
        JobObjects::{
            AssignProcessToJobObject, CreateJobObjectW, JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
            JOBOBJECT_EXTENDED_LIMIT_INFORMATION, JobObjectExtendedLimitInformation,
            SetInformationJobObject,
        },
        LibraryLoader::{GetProcAddress, LoadLibraryExW},
        Memory::{CreateFileMappingW, FILE_MAP_ALL_ACCESS, MapViewOfFile, PAGE_READWRITE},
    },
};

pub struct Job(HANDLE);
impl Job {
    pub fn attach(child: &std::process::Child) -> Result<Self> {
        // No initialization is sent until job attachment succeeds. An early
        // parent death therefore leaves an uninitialized child waiting on EOF.
        unsafe {
            let handle = CreateJobObjectW(ptr::null(), ptr::null());
            if handle.is_null() {
                return Err(std::io::Error::last_os_error().into());
            }
            let job = Self(handle);
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            if SetInformationJobObject(
                handle,
                JobObjectExtendedLimitInformation,
                (&info as *const JOBOBJECT_EXTENDED_LIMIT_INFORMATION).cast(),
                std::mem::size_of_val(&info) as u32,
            ) == 0
                || AssignProcessToJobObject(handle, child.as_raw_handle()) == 0
            {
                return Err(std::io::Error::last_os_error().into());
            }
            Ok(job)
        }
    }
}
impl Drop for Job {
    fn drop(&mut self) {
        unsafe {
            CloseHandle(self.0);
        }
    }
}

pub fn random() -> Result<[u8; 24]> {
    let mut bytes = [0; 24];
    // The null algorithm handle selects the system RNG, not a reusable PRNG seed.
    if unsafe {
        BCryptGenRandom(
            ptr::null_mut(),
            bytes.as_mut_ptr(),
            bytes.len() as u32,
            BCRYPT_USE_SYSTEM_PREFERRED_RNG,
        )
    } < 0
    {
        return Err("Windows system RNG failed".into());
    }
    Ok(bytes)
}

type Factory = unsafe extern "system" fn(
    *mut *mut c_void,
    *mut c_void,
    *mut u64,
    i64,
    i64,
    i32,
    i32,
    i32,
) -> *mut c_void;
type Resume = unsafe extern "system" fn(*mut *mut c_void, *mut c_void, *mut u64) -> *mut c_void;
type Get = unsafe extern "system" fn(*mut c_void, i64) -> *mut c_void;
type Claim = unsafe extern "system" fn(*mut c_void, *mut i64) -> bool;
type Mark = unsafe extern "system" fn(*mut c_void, i64);
type Current = unsafe extern "system" fn(*mut c_void) -> i64;
type Wait = unsafe extern "system" fn(*mut c_void, i64, *mut i64) -> bool;

pub struct Library(HMODULE);
impl Library {
    pub fn load(bin: &Path) -> Result<Self> {
        let name = bin
            .join("ringbuffer.dll")
            .as_os_str()
            .encode_wide()
            .chain(Some(0))
            .collect::<Vec<_>>();
        // Match Python's verified restricted loader search: DLL directory + defaults.
        let handle = unsafe { LoadLibraryExW(name.as_ptr(), ptr::null_mut(), 0x1100) };
        if handle.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }
        Ok(Self(handle))
    }
    fn bind<T: Copy>(&self, name: &CStr) -> Result<T> {
        let proc = unsafe { GetProcAddress(self.0, name.as_ptr().cast()) }
            .ok_or("missing pinned ringbuffer export")?;
        if std::mem::size_of::<T>() != std::mem::size_of_val(&proc) {
            return Err("invalid ABI pointer width".into());
        }
        // Call sites supply only the function pointer signatures mirrored from
        // the already verified x64 ctypes adapter, never Rust/C++ object values.
        Ok(unsafe { std::mem::transmute_copy(&proc) })
    }
}

const QUEUE_BYTES: u64 = 75497752;
pub struct Ring {
    _file: File,
    _mapping: HANDLE,
    base: *mut c_void,
    obj: *mut c_void,
    get: Get,
    claim: Claim,
    commit: Mark,
    current: Current,
    wait: Wait,
    finish: Mark,
}
impl Ring {
    pub fn open(library: &Library, path: &Path, create: bool) -> Result<Self> {
        let file = OpenOptions::new().read(true).write(true).open(path)?;
        if create {
            file.set_len(QUEUE_BYTES)?;
        }
        if file.metadata()?.len() != QUEUE_BYTES {
            return Err("invalid native queue size".into());
        }
        let mapping = unsafe {
            CreateFileMappingW(
                file.as_raw_handle(),
                ptr::null(),
                PAGE_READWRITE,
                0,
                0,
                ptr::null(),
            )
        };
        if mapping.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }
        let base =
            unsafe { MapViewOfFile(mapping, FILE_MAP_ALL_ACCESS, 0, 0, QUEUE_BYTES as usize) }
                .Value;
        if base.is_null() {
            return Err(std::io::Error::last_os_error().into());
        }
        let mut size = QUEUE_BYTES;
        let mut obj = ptr::null_mut();
        if create {
            let f:Factory=library.bind(c"?create@RingBufferWriter@ringbuffer@base@@SA?AV?$unique_ptr@VRingBufferWriter@ringbuffer@base@@U?$default_delete@VRingBufferWriter@ringbuffer@base@@@std@@@std@@PEAXPEA_K_J2W4IOType@23@3W4WaitStrategyType@23@@Z")?;
            unsafe {
                f(&mut obj, base, &mut size, 512, 131072, 1, 0, 2);
            }
        } else {
            let header = unsafe { std::slice::from_raw_parts(base.cast::<u8>(), 48) };
            if &header[..8] != b"Head\0\0\0\0"
                || header[8..]
                    .as_chunks::<8>()
                    .0
                    .iter()
                    .map(|s| u64::from_le_bytes(*s))
                    .ne([512, 131072, 1, 0, 2])
            {
                return Err("invalid native queue header".into());
            }
            let f:Resume=library.bind(c"?resume@RingBufferWriter@ringbuffer@base@@SA?AV?$unique_ptr@VRingBufferWriter@ringbuffer@base@@U?$default_delete@VRingBufferWriter@ringbuffer@base@@@std@@@std@@PEAXPEA_K@Z")?;
            unsafe {
                f(&mut obj, base, &mut size);
            }
        }
        if obj.is_null() || size > QUEUE_BYTES {
            return Err("native ringbuffer initialization failed".into());
        }
        Ok(Self {
            _file: file,
            _mapping: mapping,
            base,
            obj,
            get: library.bind(c"?get@RingBufferWriter@ringbuffer@base@@QEAAPEAX_J@Z")?,
            claim: library.bind(c"?tryClaim@RingBufferWriter@ringbuffer@base@@QEAA_NPEA_J@Z")?,
            commit: library.bind(c"?commit@RingBufferWriter@ringbuffer@base@@QEAAX_J@Z")?,
            current: library.bind(c"?current@RingBufferReader@ringbuffer@base@@QEBA_JXZ")?,
            wait: library.bind(c"?tryWaitFor@RingBufferReader@ringbuffer@base@@QEAA_N_JPEA_J@Z")?,
            finish: library.bind(c"?finish@RingBufferReader@ringbuffer@base@@QEAAX_J@Z")?,
        })
    }
    fn slot(&self, sequence: i64) -> Result<*mut u8> {
        let slot = unsafe { (self.get)(self.obj, sequence) }.cast::<u8>();
        let offset = (slot as usize)
            .checked_sub(self.base as usize)
            .ok_or("native slot outside mapping")?;
        if offset
            .checked_add(512)
            .is_none_or(|n| n > QUEUE_BYTES as usize)
        {
            return Err("native slot outside mapping".into());
        }
        Ok(slot)
    }
    fn send(&mut self, raw: &[u8; 512], deadline: Instant) -> Result<()> {
        while Instant::now() < deadline {
            let mut sequence = 0;
            if unsafe { (self.claim)(self.obj, &mut sequence) } {
                let slot = self.slot(sequence)?;
                unsafe {
                    ptr::copy_nonoverlapping(raw.as_ptr(), slot, 512);
                    (self.commit)(self.obj, sequence);
                }
                return Ok(());
            }
            thread::sleep(Duration::from_millis(1));
        }
        Err("native input queue deadline exceeded".into())
    }
    fn receive(&mut self, deadline: Instant) -> Result<Frame> {
        while Instant::now() < deadline {
            let sequence = unsafe { (self.current)(self.obj) }
                .checked_add(1)
                .ok_or("native reader sequence exhausted")?;
            let mut available = 0;
            if unsafe { (self.wait)(self.obj, sequence, &mut available) } {
                let mut raw = [0; 512];
                let slot = self.slot(sequence)?;
                unsafe {
                    ptr::copy_nonoverlapping(slot, raw.as_mut_ptr(), 512);
                    (self.finish)(self.obj, sequence);
                }
                return Frame::decode(&raw);
            }
            thread::sleep(Duration::from_millis(1));
        }
        Err("native response deadline exceeded".into())
    }
}

// Vendor objects, module and mappings intentionally live to worker process exit.
// Their C++ allocator/destructor contract is not guessed in Rust. Never create
// these objects in the public CLI process or repeat creation per request.
pub struct NativeQueue {
    pub reply: Ring,
    pub outgoing: Ring,
    _library: Library,
}
impl NativeQueue {
    pub fn open(bin: &Path, data: &Path, reply: &Path) -> Result<Self> {
        let library = Library::load(bin)?;
        let reply = Ring::open(&library, reply, true)?;
        let outgoing = Ring::open(&library, &data.join("up_queue_xtquant"), false)?;
        Ok(Self {
            reply,
            outgoing,
            _library: library,
        })
    }
}
impl Queue for NativeQueue {
    fn send(&mut self, raw: &[u8; 512], deadline: Instant) -> Result<()> {
        self.outgoing.send(raw, deadline)
    }
    fn receive(&mut self, deadline: Instant) -> Result<Frame> {
        self.reply.receive(deadline)
    }
}

pub fn probe(bin: &Path, path: &Path) -> Result<()> {
    // A fresh private queue only; no broker queue is opened by this diagnostic.
    let _file = OpenOptions::new().write(true).create_new(true).open(path)?;
    let library = Library::load(bin)?;
    let mut ring = Ring::open(&library, path, true)?;
    let frame =
        super::protocol::encode_request(1, 20005, 123, &super::encode_account("A", "STOCK")?)?;
    let deadline = Instant::now() + Duration::from_secs(2);
    ring.send(&frame, deadline)?;
    let received = ring.receive(deadline)?;
    if received.sequence != 1 || received.kind != 20005 || received.session != 123 {
        return Err("native ring probe mismatch".into());
    }
    Ok(())
}
