"""Allowlisted public QMT calls; this module runs on QMT's strategy owner thread."""

import inspect
import json
import math
import threading
import uuid


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.status = code, status


def json_loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result

    def constant(_):
        raise ValueError('non-finite JSON number')

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def validate(value, schema, name):
    kinds = schema.get('type', 'any')
    kinds = kinds if isinstance(kinds, list) else [kinds]
    matches = {
        'any': True, 'string': isinstance(value, str),
        'boolean': type(value) is bool, 'integer': type(value) is int,
        'number': type(value) in (int, float),
        'object': isinstance(value, dict), 'array': isinstance(value, (list, tuple)),
        'null': value is None,
    }
    if not any(matches.get(kind, False) for kind in kinds):
        raise ApiError('invalid_parameter', 'invalid type for ' + name)
    if type(value) in (float, int) and not math.isfinite(value):
        raise ApiError('invalid_parameter', 'non-finite parameter: ' + name)
    if isinstance(value, str) and len(value) > schema.get('max_length', 1048576):
        raise ApiError('invalid_parameter', 'parameter too long: ' + name)
    if isinstance(value, (list, tuple)) and len(value) > schema.get('max_items', 1000000):
        raise ApiError('invalid_parameter', 'too many items: ' + name)
    if isinstance(value, (list, tuple)) and 'items' in schema:
        for item in value:
            validate(item, schema['items'], name + '[]')
    if 'enum' in schema and value not in schema['enum']:
        raise ApiError('invalid_parameter', 'invalid value for ' + name)


class Service:
    def __init__(self, app, namespace, codec, catalog):
        self.app, self.namespace, self.codec, self.catalog = app, namespace, codec, catalog
        self.apis = {item['id']: item for item in catalog['apis']}
        self.generation = uuid.uuid4().hex
        self.owner = threading.get_ident()
        self.streams = {}
        self.drawing_sites = {(name, None): index + 1 for index, name in enumerate(
            ("context.draw_text", "context.draw_vertline", "context.draw_icon", "context.draw_number"))}
        self.stream_lock = threading.Lock()
        self.config = namespace.get('_SDK_CONFIG', {})

    def initialize(self, context):
        self.assert_owner()
        properties = self.config.get('init_properties', {})
        calls = self.config.get('init_calls', [])
        if (properties or calls) and not self.config.get('strategy_write_enabled', False):
            raise ApiError('effect_disabled', 'strategy startup writes are disabled', 403)
        property_types = {'benchmark': str, 'capital': (int, float), 'refresh_rate': (int, float),
                          'do_back_test': bool, 'start': str, 'end': str, 'data_info_level': int}
        prepared = []
        for name, value in properties.items():
            spec = self.specification('context.' + name)
            expected = property_types.get(name)
            if not spec.get('writable') or expected is None or type(value) not in (expected if isinstance(expected, tuple) else (expected,)):
                raise ApiError('invalid_parameter', 'invalid startup property')
            if type(value) in (int, float) and not math.isfinite(value):
                raise ApiError('invalid_parameter', 'non-finite startup property')
            prepared.append((name, value))
        bound_calls = []
        for call in calls:
            if not isinstance(call, dict) or set(call) != {'api', 'params'}:
                raise ApiError('invalid_parameter', 'invalid startup call')
            spec = self.specification(call['api'])
            if spec['kind'] != 'init_method':
                raise ApiError('wrong_entry', 'only init methods belong in init_calls')
            params = call['params']
            if spec['id'] == 'context.set_account':
                if params.get('account_id') != self.app.accountID or params.get('account_type', '') not in ('', self.config.get('account_type')):
                    raise ApiError('account_mismatch', 'startup account does not match configuration', 403)
            args, _ = self.arguments(spec, params, context)
            bound_calls.append((self.function(spec, context), args))
        # Validate the complete startup plan before applying its first native mutation.
        for name, value in prepared:
            setattr(context, name, value)
        for function, args in bound_calls:
            function(*args)

    def assert_owner(self):
        if threading.get_ident() != self.owner:
            raise ApiError('wrong_thread', 'SDK calls require the strategy owner thread', 503)

    def context_state(self, context):
        mode = getattr(context, 'do_back_test', None)
        return {'generation': self.generation,
                'mode': 'backtest' if mode is True else 'live' if mode is False else 'unknown',
                'barpos': getattr(context, 'barpos', None)}

    def specification(self, api):
        if not isinstance(api, str) or api not in self.apis:
            raise ApiError('unknown_api', 'unknown public API')
        return self.apis[api]

    def function(self, spec, context):
        binding = spec['binding']
        if binding['owner'] == 'context':
            function = getattr(context, binding['name'], None)
        elif binding['owner'] == 'global':
            function = self.namespace.get(binding['name'])
        elif spec['id'] == 'bridge.subscriptions':
            function = self.subscriptions
        elif spec['id'] == 'bridge.discovery':
            function = self.discovery
        else:
            function = None
        if not callable(function):
            raise ApiError('native_unavailable', 'public API is not available in this QMT context', 501)
        return function

    def arguments(self, spec, params, context, callback=None):
        if not isinstance(params, dict):
            raise ApiError('invalid_parameter', 'params must be an object')
        candidates = spec.get('variants', [spec['params']])
        failures = []
        for variant in candidates:
            try:
                allowed = {p['name'] for p in variant if not p.get('inject')}
                if set(params) - allowed:
                    raise ApiError('invalid_parameter', 'unknown or injected parameter')
                values, omitted, bound = [], False, {}
                for parameter in variant:
                    name, inject = parameter['name'], parameter.get('inject')
                    if inject:
                        value = context if inject == 'context' else callback
                        if value is None:
                            raise ApiError('stream_required', 'callback requires a persistent stream')
                        # QMT documents optional positional groups immediately before ContextInfo.
                        if omitted and inject != 'context':
                            raise ApiError('invalid_parameter', 'non-contiguous optional parameters')
                        omitted = False
                    elif name in params:
                        if omitted:
                            raise ApiError('invalid_parameter', 'non-contiguous optional parameters')
                        value = self.codec.decode(params[name])
                        validate(value, parameter.get('schema', {}), name)
                    elif 'default' in parameter:
                        value = parameter['default']
                    elif parameter.get('required'):
                        raise ApiError('invalid_parameter', 'missing parameter: ' + name)
                    else:
                        omitted = True
                        continue
                    values.append(value)
                    bound[name] = value
                if spec['id'] == 'global.query_credit_opvolume':
                    codes, prices = bound['stockCode'], bound['price']
                    code_list, price_list = isinstance(codes, (list, tuple)), isinstance(prices, (list, tuple))
                    if code_list != price_list or (code_list and len(codes) != len(prices)):
                        raise ApiError('invalid_parameter', 'credit securities and prices must have matching shape and length')
                return values, variant
            except (ValueError, TypeError, OverflowError) as error:
                failures.append(error if isinstance(error, ApiError) else
                                ApiError('invalid_parameter', 'invalid typed parameter'))
            except ApiError as error:
                failures.append(error)
        raise failures[0]

    def authorize(self, spec, params, context, headers):
        self.assert_owner()
        state = self.context_state(context)
        modes = spec.get('modes', [])
        if modes and state['mode'] not in modes:
            raise ApiError('wrong_mode', 'API is not available in the current strategy mode', 409)
        effect = spec['effect']
        if effect == 'trade' and not self.app.trading_enabled:
            raise ApiError('trading_disabled', 'trading is disabled at startup', 403)
        if effect in ('data_write', 'strategy_write') and not self.config.get(effect + '_enabled', False):
            raise ApiError('effect_disabled', effect + ' is disabled at startup', 403)
        for parameter in spec['params']:
            if parameter['name'] == 'subscribe':
                value = params.get('subscribe', parameter.get('default'))
                if value is not False:
                    raise ApiError('stream_required', 'implicit subscription is not owned; use an explicit stream', 409)
        if spec.get('requires_account') or effect == 'trade':
            account = self.app.accountID
            if not account or headers.get('X-Bridge-Account') != account:
                raise ApiError('account_mismatch', 'an exact account binding is required', 403)
            try:
                self.namespace['_validate_account_context'](account, context)
            except RuntimeError:
                raise ApiError('account_mismatch', 'strategy account binding changed', 409) from None
            for key, value in params.items():
                canonical = key.lower().replace('_', '')
                canonical = canonical[3:] if canonical.startswith('str') else canonical
                if canonical in ('accountid', 'account', 'stockaccount', 'accid') and value != account:
                    raise ApiError('account_mismatch', 'parameter account does not match startup binding', 403)
            configured_type = self.config.get('account_type')
            if configured_type:
                for key, value in params.items():
                    canonical = key.lower().replace('_', '')
                    canonical = canonical[3:] if canonical.startswith('str') else canonical
                    if canonical == 'accounttype' and value != configured_type:
                        raise ApiError('account_mismatch', 'account type does not match startup binding', 403)
        return state

    def prepare_call(self, request, context, headers, callback=None, streaming=False):
        if not isinstance(request, dict) or set(request) - {'api', 'params', 'expected_context', 'site'}:
            raise ApiError('invalid_request', 'expected api, params and optional expected_context')
        spec = self.specification(request.get('api'))
        if 'site' in request:
            site = request['site']
            if streaming or spec['id'] not in ('context.draw_text', 'context.draw_vertline', 'context.draw_icon', 'context.draw_number'):
                raise ApiError('invalid_request', 'site is only supported by drawing calls')
            if not isinstance(site, str) or not 1 <= len(site) <= 128:
                raise ApiError('invalid_parameter', 'site must be a bounded nonempty string')
            try:
                site.encode('utf-8')
            except UnicodeError:
                raise ApiError('invalid_parameter', 'site must be valid Unicode') from None
        params = request.get('params', {})
        if not isinstance(params, dict):
            raise ApiError('invalid_parameter', 'params must be an object')
        if spec['kind'] not in (('subscription', 'timer', 'callback', 'lifecycle') if streaming else ('method', 'property')):
            raise ApiError('wrong_entry', 'API requires its lifecycle, startup or stream entry', 409)
        state = self.authorize(spec, params, context, headers)
        expected = request.get('expected_context')
        if expected is not None:
            if not isinstance(expected, dict) or set(expected) - {'generation', 'barpos'}:
                raise ApiError('invalid_request', 'invalid expected_context')
            if any(state.get(key) != value for key, value in expected.items()):
                raise ApiError('context_changed', 'strategy context changed', 409)
        if spec['kind'] in ('property', 'callback', 'lifecycle'):
            if params:
                raise ApiError('invalid_parameter', 'property reads accept no parameters')
            return spec, None, [], state
        args, _ = self.arguments(spec, params, context, callback)
        function = self.function(spec, context)
        if spec['id'] in ('context.draw_text', 'context.draw_vertline', 'context.draw_icon', 'context.draw_number'):
            function, args = self.drawing_call(spec['id'], request.get('site'), args, context)
        return spec, function, args, state

    def drawing_call(self, api, site, args, context):
        # Installed _PyContextInfo.py:515-546 supplies caller-line identity and axis.
        native = getattr(context, 'context', None)
        if native is None or not isinstance(args[-1], str):
            raise ApiError('native_unavailable', 'native drawing context or limit is unavailable', 501)
        axis = 0 if args[-1].lower() == 'noaxis' else 1
        if api == 'context.draw_text':
            function = getattr(native, 'draw_text', None)
        elif api == 'context.draw_vertline':
            function = getattr(native, 'draw_vertline', None)
        elif api == 'context.draw_icon':
            function = getattr(native, 'draw_icon', None)
        else:
            function = getattr(native, 'draw_number', None)
        if not callable(function):
            raise ApiError('native_unavailable', 'native drawing method is unavailable', 501)
        key = (api, site)
        line = self.drawing_sites.get(key)
        if line is None:
            if len(self.drawing_sites) >= 4096:
                raise ApiError('drawing_site_limit', 'drawing site capacity reached for this generation', 429)
            line = len(self.drawing_sites) + 1
            self.drawing_sites[key] = line
        return function, args[:-1] + [line, axis]

    def subscriptions(self, context):
        return self.namespace['_subscription_snapshot'](self.app, context)

    def discovery(self, context):
        def describe(obj):
            result = []
            if obj is None:
                return result
            for name in sorted(name for name in dir(obj) if not name.startswith('_'))[:512]:
                try:
                    value = inspect.getattr_static(obj, name)
                except AttributeError:
                    continue
                doc = getattr(value, '__doc__', None)
                result.append({'name': name, 'callable': callable(value),
                               'doc': doc[:2048] if isinstance(doc, str) else None})
            return result
        globals_view = []
        for name, value in sorted(self.namespace.items()):
            if name.startswith('_') or not callable(value):
                continue
            doc = getattr(value, '__doc__', None)
            globals_view.append({'name': name, 'doc': doc[:2048] if isinstance(doc, str) else None})
            if len(globals_view) == 512:
                break
        return {'context_class': type(context).__name__, 'context_module': type(context).__module__,
                'context_members': describe(context),
                'native_context_members': describe(getattr(context, 'context', None)),
                'global_callables': globals_view, 'business_methods_invoked': False,
                'generation': self.generation}

    def emit(self, api, *args, **kwargs):
        with self.stream_lock:
            streams = tuple(stream for stream in self.streams.values()
                            if stream.spec['id'] == api)
        for stream in streams:
            stream.callback(*args, **kwargs)

    def validate_context(self, context):
        if self.streams:
            try:
                self.namespace['_validate_account_context'](self.app.accountID, context)
            except RuntimeError:
                self.retire_all('account context changed')
                return
        for stream in tuple(self.streams.values()):
            try:
                self.authorize(stream.spec, {}, context, stream.request.headers)
            except ApiError:
                stream.retire('strategy mode or account binding changed')

    def retire_all(self, reason):
        self.assert_owner()
        with self.stream_lock:
            streams = tuple(self.streams.values())
        for stream in streams:
            stream.retire(reason)

    def capabilities(self, context):
        self.assert_owner()
        available = []
        for spec in self.catalog['apis']:
            binding = spec['binding']
            if binding['owner'] == 'context':
                try:
                    inspect.getattr_static(context, binding['name'])
                    present = True
                except AttributeError:
                    present = False
            elif binding['owner'] == 'global':
                present = callable(self.namespace.get(binding['name']))
            else:
                present = None
            available.append({'id': spec['id'], 'kind': spec['kind'], 'effect': spec['effect'],
                              'native_entry_present': present,
                              'adapter_entry_present': binding['owner'] == 'bridge' or spec['kind'] in ('callback', 'lifecycle') or bool(present),
                              'verified': spec.get('verified', [])})
        return {'protocol': self.catalog['protocol'], 'catalog_version': self.catalog['catalog_version'],
                'context': self.context_state(context), 'trading_enabled': self.app.trading_enabled,
                'apis': available, 'targets': self.catalog['targets'],
                'unresolved_contracts': self.catalog['unresolved_contracts'],
                'scope': self.catalog['scope'], 'limits': self.catalog['limits']}


def handlers(base, stream_module=None):
    class ApiHandler(base):
        trading_required = False
        account_required = False

        def prepare(self):
            super().prepare()
            self._invoked = False

        def write_error(self, status_code, **kwargs):
            error = kwargs.get('exc_info', (None, None, None))[1]
            if isinstance(error, ApiError):
                code, message = error.code, str(error)
            else:
                code, message = 'request_failed', 'bridge request failed'
            self.set_header('Content-Type', 'application/json; charset=utf-8')
            self.finish(json.dumps({'ok': False, 'error': {'code': code, 'message': message,
                'outcome': 'unknown' if getattr(self, '_invoked', False) else 'not_invoked'}},
                ensure_ascii=False, allow_nan=False))

        def fail(self, error):
            self.set_status(error.status)
            self.finish(json.dumps({'ok': False, 'error': {'code': error.code, 'message': str(error),
                'outcome': 'unknown' if self._invoked else 'not_invoked'}}, allow_nan=False))

        def body(self):
            if len(self.request.body) > self.application.sdk.catalog['limits']['request_bytes']:
                raise ApiError('request_too_large', 'SDK request exceeds size limit', 413)
            try:
                return json_loads(self.request.body)
            except (ValueError, UnicodeError, RecursionError):
                raise ApiError('invalid_json', 'request must be bounded valid JSON') from None

        def success(self, data, state=None):
            response = {'ok': True, 'data': self.application.sdk.codec.encode(data)}
            if state is not None:
                response['context'] = state
            raw = json.dumps(response, ensure_ascii=False, allow_nan=False)
            if len(raw.encode('utf-8')) > self.application.sdk.catalog['limits']['result_bytes']:
                raise ApiError('result_too_large', 'SDK result exceeds size limit', 502)
            self.finish(raw)

    class CapabilitiesHandler(ApiHandler):
        def get(self):
            try:
                # Catalog JSON is already a wire value, not an SDK result to tag again.
                self.finish(json.dumps({'ok': True, 'data': self.application.sdk.capabilities(self._ctx())},
                                       ensure_ascii=False, allow_nan=False))
            except ApiError as error:
                self.fail(error)

    class CallHandler(ApiHandler):
        def post(self):
            service = self.application.sdk
            try:
                spec, function, args, state = service.prepare_call(
                    self.body(), self._ctx(), self.request.headers)
                self._invoked = True
                result = (getattr(self._ctx(), spec['binding']['name'])
                          if spec['kind'] == 'property' else function(*args))
                self.success(result, state)
            except ApiError as error:
                self.fail(error)
            except BaseException:
                # Native exception text may contain accounts, requests or credentials.
                self.fail(ApiError('native_call_failed', 'SDK call or result encoding failed', 502))

    routes = [(r'/api/capabilities', CapabilitiesHandler), (r'/api/call', CallHandler)]
    if stream_module is not None:
        routes += stream_module.handlers(ApiHandler, ApiError)
    return routes
