# -*- coding: utf-8 -*-
"""Typed JSON for documented QMT table, array and native-object values."""

import base64
import datetime
import math
import numbers

MAX_DEPTH = 32
MAX_ITEMS = 1000000
MAX_SAFE_INTEGER = 9007199254740991


def encode(value):
    state = {'active': set(), 'items': 0}
    return _encode(value, state, 0)


def _encode(value, state, depth):
    state['items'] += 1
    if depth > MAX_DEPTH or state['items'] > MAX_ITEMS:
        raise ValueError('SDK result exceeds structured-value limits')
    if value is None or isinstance(value, (str, bool)):
        return value
    kind = type(value).__name__
    module = type(value).__module__
    if kind in ('NAType', 'NaTType') and module.startswith('pandas'):
        return {'$type': 'missing', 'value': 'NA' if kind == 'NAType' else 'NaT'}
    if isinstance(value, numbers.Integral):
        integer = int(value)
        if abs(integer) > MAX_SAFE_INTEGER:
            return {'$type': 'integer', 'value': str(integer)}
        return integer
    if isinstance(value, numbers.Real):
        number = float(value)
        if not math.isfinite(number):
            label = 'nan' if math.isnan(number) else ('inf' if number > 0 else '-inf')
            return {'$type': 'float', 'value': label}
        return number
    if isinstance(value, datetime.datetime):
        result = {'$type': 'timestamp' if kind == 'Timestamp' else 'datetime',
                  'value': value.isoformat()}
        if kind == 'Timestamp':
            result['nanoseconds'] = str(value.value)
        return result
    if isinstance(value, datetime.date):
        return {'$type': 'date', 'value': value.isoformat()}
    if isinstance(value, datetime.timedelta):
        return {'$type': 'timedelta', 'days': value.days,
                'seconds': value.seconds, 'microseconds': value.microseconds}
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {'$type': 'bytes', 'base64': base64.b64encode(bytes(value)).decode('ascii')}
    identity = id(value)
    if identity in state['active']:
        raise ValueError('cyclic SDK result')
    state['active'].add(identity)
    try:
        return _container(value, state, depth, module, kind)
    finally:
        state['active'].remove(identity)


def _container(value, state, depth, module, kind):
    def item(part):
        return _encode(part, state, depth + 1)

    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value) and '$type' not in value:
            return {key: item(part) for key, part in value.items()}
        return {'$type': 'mapping', 'entries': [[item(key), item(part)]
                                               for key, part in value.items()]}
    if isinstance(value, list):
        return [item(part) for part in value]
    if isinstance(value, tuple):
        return {'$type': 'tuple', 'items': [item(part) for part in value]}
    if module.startswith('pandas') and kind == 'DataFrame':
        return {'$type': 'dataframe', 'columns': item(list(value.columns)),
                'index': item(list(value.index)), 'index_names': item(list(value.index.names)),
                'column_names': item(list(value.columns.names)),
                'dtypes': [str(dtype) for dtype in value.dtypes],
                'data': [[item(part) for part in row]
                         for row in value.itertuples(index=False, name=None)]}
    if module.startswith('pandas') and kind == 'Series':
        return {'$type': 'series', 'name': item(value.name),
                'index': item(list(value.index)), 'index_names': item(list(value.index.names)),
                'dtype': str(value.dtype), 'data': item(value.tolist())}
    if module.startswith('pandas') and kind == 'Panel':
        return {'$type': 'panel', 'items': item(list(value.items)),
                'major_axis': item(list(value.major_axis)),
                'minor_axis': item(list(value.minor_axis)), 'data': item(value.values)}
    if module.startswith('numpy') and hasattr(value, 'dtype'):
        if getattr(value, 'ndim', 0) == 0:
            if str(value.dtype).startswith(('datetime64', 'timedelta64')):
                return {'$type': 'numpy-scalar', 'dtype': str(value.dtype), 'value': str(value)}
            return item(value.item())
        return {'$type': 'ndarray', 'dtype': str(value.dtype),
                'shape': list(value.shape), 'data': item(value.tolist())}
    fields = {}
    for name in dir(value):
        if name.startswith('m_') and not callable(getattr(value, name)):
            fields[name] = item(getattr(value, name))
    if fields:
        return {'$type': 'sdk-object', 'class': kind, 'fields': fields}
    raise TypeError('unsupported SDK result type: ' + kind)


def decode(value, depth=0):
    if depth > MAX_DEPTH:
        raise ValueError('SDK parameters exceed structured-value depth')
    if isinstance(value, list):
        return [decode(part, depth + 1) for part in value]
    if not isinstance(value, dict):
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError('non-finite JSON number requires an explicit typed value')
        return value
    tag = value.get('$type')
    if tag is None:
        return {key: decode(part, depth + 1) for key, part in value.items()}
    if tag == 'integer':
        text = value.get('value')
        if not isinstance(text, str) or len(text) > 128:
            raise ValueError('invalid typed integer')
        return int(text)
    if tag == 'bytes':
        text = value.get('base64')
        if not isinstance(text, str):
            raise ValueError('invalid typed bytes')
        return base64.b64decode(text, validate=True)
    if tag == 'float':
        choices = {'nan': float('nan'), 'inf': float('inf'), '-inf': -float('inf')}
        if value.get('value') not in choices:
            raise ValueError('invalid typed float')
        return choices[value['value']]
    if tag == 'timedelta':
        values = [value.get(key, 0) for key in ('days', 'seconds', 'microseconds')]
        if any(type(part) is not int for part in values):
            raise ValueError('invalid typed timedelta')
        return datetime.timedelta(days=values[0], seconds=values[1], microseconds=values[2])
    if tag in ('timestamp', 'datetime', 'date'):
        text = value.get('value')
        if not isinstance(text, str) or len(text) > 128:
            raise ValueError('invalid typed datetime')
        import pandas as pd
        parsed = pd.Timestamp(text)
        if tag == 'timestamp' and 'nanoseconds' in value:
            nanos = value['nanoseconds']
            if not isinstance(nanos, str) or len(nanos) > 32 or int(nanos) != parsed.value:
                raise ValueError('inconsistent typed timestamp')
        if parsed.nanosecond:
            raise ValueError('native datetime parameters do not support sub-microsecond precision')
        if tag == 'date' and (parsed.hour or parsed.minute or parsed.second or parsed.microsecond):
            raise ValueError('typed date must not contain a time')
        return parsed.date() if tag == 'date' else parsed.to_pydatetime()
    if tag == 'tuple':
        return tuple(decode(value['items'], depth + 1))
    if tag == 'mapping':
        pairs = value.get('entries')
        if not isinstance(pairs, list) or any(not isinstance(p, list) or len(p) != 2 for p in pairs):
            raise ValueError('invalid typed mapping')
        return {decode(key, depth + 1): decode(part, depth + 1) for key, part in pairs}
    raise ValueError('unsupported SDK parameter type: ' + str(tag))
