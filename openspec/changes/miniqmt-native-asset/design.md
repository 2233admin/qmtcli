# Design

Agent -> existing CLI/RPC/JSONL -> native asset adapter -> bounded worker process
-> pinned ringbuffer.dll (local runtime, not xtquant) -> MiniQMT message queues.

Keep frame/account/asset codecs pure Python and separately testable. Worker uses
the client's atomic claim/commit implementation instead of inventing shared
memory synchronization. Validate binary hashes before native calls; no arbitrary
DLL paths, symbols or message methods are exposed to agents. Use a unique session
and its own reply queue; never consume another client's reply queue.

Native library calls use recovered Windows x64 ABI primitives and are confined
to the worker. First verify queue round-trip using an isolated file, then a live
connection; no guessed messages go to a running service. The asset response's
trailing bytes have no verified public meaning and must not be assigned names.

Failure behavior: validate request before connecting; reject unrecognized build;
timeouts and worker crashes become errors. On disconnect do not retry a query
without a new owned session. Preserve SDK behavior for existing callers.

Research evidence is local under F:/projects/_research; publish only sanitized
protocol descriptions and hashes, never account values or queue dumps.
