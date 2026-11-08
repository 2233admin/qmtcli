"""Owned, bounded per-callback SSE streams for public QMT registrations."""

import asyncio
from collections import deque
import json
import threading
import uuid

from tornado.ioloop import IOLoop
from tornado.iostream import StreamClosedError


MAX_PENDING_EVENTS = 256
MAX_PENDING_BYTES = 32 * 1024 * 1024


def handlers(api_handler, ApiError):
    class StreamHandler(api_handler):
        def initialize(self):
            self.token = uuid.uuid4().hex
            self.lock = threading.Lock()
            self.pending = deque()
            self.pending_bytes = 0
            self.sequence = 0
            self.closed = False
            self.failure = None
            self.native_id = None
            self.native_domain = None
            self.cleanup = None
            self.cleanup_failed = False
            self.ready = False
            self.wake = None
            self.loop = None
            self.context = None
            self.spec = None

        def callback(self, *args, **kwargs):
            # Freeze native views before the SDK reuses them; never call SDK methods here.
            with self.lock:
                if self.closed or self.failure:
                    return
            service = self.application.sdk
            try:
                parts = [part for part in args if part is not self.context]
                wire = {'args': service.codec.encode(parts), 'kwargs': service.codec.encode(kwargs)}
                raw = json.dumps(wire, ensure_ascii=False, allow_nan=False)
                size = len(raw.encode('utf-8'))
                if size > service.catalog['limits']['event_bytes']:
                    raise ValueError('oversized native event')
                with self.lock:
                    if self.closed or self.failure:
                        return
                    self.sequence += 1
                    if len(self.pending) >= MAX_PENDING_EVENTS or self.pending_bytes + size > MAX_PENDING_BYTES:
                        self.failure = ('overflow', 'per-callback delivery overflow; resynchronization is required')
                        self.pending.clear()
                        self.pending_bytes = 0
                    else:
                        self.pending.append((self.sequence, wire, size))
                        self.pending_bytes += size
            except BaseException:
                with self.lock:
                    if not self.closed:
                        self.failure = ('encoding_failed', 'native callback could not be encoded; resynchronization is required')
            try:
                self.loop.add_callback(self.wake.set)
            except RuntimeError:
                # Shutdown owns cleanup; a late callback cannot revive the stream.
                pass

        def frame(self, event, data):
            raw = json.dumps({'ok': True, 'data': data}, ensure_ascii=False, allow_nan=False)
            frame = 'event: ' + event + '\ndata: ' + raw + '\n\n'
            complete = len(frame.encode('utf-8')) <= self.application.sdk.catalog['limits']['event_bytes']
            if not complete:
                frame = 'event: gap\ndata: ' + json.dumps({'ok': True, 'data': {
                    'stream_id': self.token, 'generation': self.application.sdk.generation,
                    'code': 'event_too_large', 'message': 'wire frame exceeds byte limit; resynchronization is required',
                    'last_sequence': self.sequence}}, allow_nan=False) + '\n\n'
            self.write(frame)
            return complete

        def retire(self, reason='closed'):
            self.application.sdk.assert_owner()
            with self.lock:
                if self.closed:
                    return not self.cleanup_failed
                self.closed = True
                self.pending.clear()
                self.pending_bytes = 0
            service = self.application.sdk
            with service.stream_lock:
                service.streams.pop(self.token, None)
            native_id, cleanup = self.native_id, self.cleanup
            self.native_id, self.cleanup = None, None
            if native_id is not None and cleanup is not None:
                try:
                    result = cleanup(native_id)
                    # False means no matching task, not confirmed cancellation.
                    if self.native_domain == 'timer' and result is not True:
                        raise RuntimeError('native timer cancellation was not confirmed')
                except BaseException:
                    self.cleanup_failed = True
                    self.application.market_cleanup_error = RuntimeError('SDK subscription cleanup is uncertain')
            if self.wake:
                self.wake.set()
            return not self.cleanup_failed

        def on_connection_close(self):
            if self.loop is not None:
                self.retire('connection closed')
            super().on_connection_close()

        def description(self):
            return {'stream_id': self.token, 'generation': self.application.sdk.generation,
                    'api': self.spec['id'], 'kind': self.spec['kind'],
                    'native_id': self.native_id, 'delivery': 'per_callback'}

        def collision(self):
            if self.native_id is None:
                return False
            service = self.application.sdk
            if self.native_domain == 'quote':
                return not service.namespace['_check_quote_ownership'](
                    self.application, self.native_id, self)
            owners = [item for item in service.streams.values() if item is not self and
                      item.native_domain == self.native_domain and item.native_id == self.native_id]
            if not owners:
                return False
            self.native_id = None
            for item in owners:
                item.native_id = None
                item.retire('native ID collision')
            self.application.market_cleanup_error = RuntimeError('native subscription identity is ambiguous')
            return True

        def register(self, request):
            service = self.application.sdk
            spec = service.specification(request.get('api'))
            self.spec = spec
            name = spec['id']
            if name in ('context.run_time', 'context.cancel_schedule_run'):
                raise ApiError('unclosed_lifecycle', 'this timer has no remotely owned registration contract', 501)
            spec, function, args, self.state = service.prepare_call(
                request, self.context, self.request.headers, self.callback, streaming=True)
            if spec['kind'] in ('callback', 'lifecycle'):
                return
            if name in ('context.subscribe_quote', 'context.subscribe_whole_quote'):
                self.native_domain = 'quote'
                self.cleanup = getattr(self.context, 'unsubscribe_quote', None)
            elif name == 'global.subscribe_formula':
                self.native_domain = 'formula'
                self.cleanup = service.namespace.get('unsubscribe_formula')
            elif name == 'context.schedule_run':
                self.native_domain = 'timer'
                self.cleanup = getattr(self.context, 'cancel_schedule_run', None)
            else:
                raise ApiError('unclosed_lifecycle', 'registration has no verified cleanup binding', 501)
            if not callable(self.cleanup):
                raise ApiError('native_unavailable', 'registration cleanup is not available', 501)
            self._invoked = True
            native_id = function(*args)
            if not ((type(native_id) is int and native_id > 0) or
                    (isinstance(native_id, str) and native_id)):
                raise ApiError('registration_unknown', 'native registration did not return an owned identity', 502)
            self.native_id = native_id
            if self.collision():
                raise ApiError('registration_unknown', 'native subscription identity is ambiguous', 502)

        async def post(self):
            service = self.application.sdk
            self.context, self.loop, self.wake = self._ctx(), IOLoop.current(), asyncio.Event()
            current_task = getattr(asyncio, "current_task", None)
            task = current_task() if current_task is not None else asyncio.Task.current_task()
            self.application.market_tasks.add(task)
            try:
                request = self.body()
                if not isinstance(request, dict):
                    raise ApiError('invalid_request', 'stream request must be an object')
                self.register(request)
                if self.closed or self.application.stopping:
                    raise ApiError('bridge_stopping', 'bridge stopped during registration', 503)
                with service.stream_lock:
                    service.streams[self.token] = self
                self.set_header('Content-Type', 'text/event-stream; charset=utf-8')
                self.set_header('Cache-Control', 'no-store')
                self.set_header('X-Accel-Buffering', 'no')
                self.frame('subscribed', {'stream_id': self.token, 'api': self.spec['id'],
                    'generation': service.generation, 'native_id': service.codec.encode(self.native_id),
                    'delivery': 'per_callback', 'context': self.state})
                await self.flush()
                self.ready = True
                while not self.closed:
                    with self.lock:
                        failure = self.failure
                        item = self.pending.popleft() if self.pending else None
                        if item:
                            self.pending_bytes -= item[2]
                        self.wake.clear()
                    if failure:
                        self.frame('gap', {'stream_id': self.token, 'generation': service.generation,
                                          'code': failure[0], 'message': failure[1],
                                          'last_sequence': self.sequence})
                        await self.flush()
                        break
                    if item:
                        sequence, wire, _ = item
                        complete = self.frame('callback', {'stream_id': self.token, 'generation': service.generation,
                                               'sequence': sequence, **wire})
                        await self.flush()
                        if not complete:
                            break
                    else:
                        try:
                            await asyncio.wait_for(self.wake.wait(), 5)
                        except asyncio.TimeoutError:
                            self.write(': heartbeat\n\n')
                            await self.flush()
            except ApiError as error:
                if not self.ready:
                    self.fail(error)
            except (StreamClosedError, asyncio.CancelledError):
                pass
            except BaseException:
                if not self.ready:
                    self.fail(ApiError('stream_failed', 'SDK stream registration or encoding failed', 502))
            finally:
                self.retire()
                self.application.market_tasks.discard(task)
                if not self._finished:
                    self.finish()

    class UnsubscribeHandler(api_handler):
        def post(self):
            service = self.application.sdk
            try:
                request = self.body()
                if not isinstance(request, dict) or set(request) != {'stream_id'} or not isinstance(request['stream_id'], str):
                    raise ApiError('invalid_request', 'an exact stream_id is required')
                stream = service.streams.get(request['stream_id'])
                if stream is None:
                    raise ApiError('unknown_subscription', 'subscription is not owned by this bridge generation', 404)
                service.authorize(stream.spec, {}, self._ctx(), self.request.headers)
                self._invoked = True
                if not stream.retire('explicit unsubscribe'):
                    raise ApiError('cleanup_unknown', 'native cleanup was not confirmed', 502)
                self.success({'stream_id': request['stream_id'], 'closed': True})
            except ApiError as error:
                self.fail(error)

    return [(r'/api/stream', StreamHandler), (r'/api/unsubscribe', UnsubscribeHandler)]
