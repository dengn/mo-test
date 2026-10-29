import json,decimal,datetime,hashlib
decimal.getcontext().prec=80
def decode(v):
    if not isinstance(v, dict) or 'kind' not in v:
        return v
    k = v['kind']
    x = v['value']
    return {'decimal': lambda: decimal.Decimal(x), 'datetime': lambda: datetime.datetime.fromisoformat(x), 'date': lambda: datetime.date.fromisoformat(x), 'duration': lambda: datetime.timedelta(microseconds=x), 'bytes': lambda: bytes.fromhex(x)}[k]()
def normalize(v, n):
    if v is None:
        return ['sql_null']
    if n.startswith('json'):
        return ['json', json.loads(v) if isinstance(v, (str, bytes)) else v]
    if n.startswith('decimal'):
        return str(decimal.Decimal(v).normalize())
    if n in ['varbinary', 'blob']:
        return bytes(v).hex()
    if n == 'date':
        return v.isoformat()
    if n == 'datetime6':
        return v.isoformat(timespec='microseconds')
    if n == 'time6':
        return (v.days * 86400 + v.seconds) * 1000000 + v.microseconds
    if n == 'float32':
        return format(float(v), '.6g')
    if n == 'double':
        return float(v).hex() if float(v) != 0 else '0'
    if n == 'char_padding':
        return str(v).rstrip(' ')
    if n == 'boolean':
        return bool(v)
    if n in ['tinyint', 'smallint', 'int32', 'int64', 'uint64']:
        return int(v)
    return str(v)
def canon(rows, n):
    return [[int(r[0]), int(r[1]), normalize(r[2], n), str(r[3]), int(r[4])] for r in sorted(rows, key=lambda r: (r[0], r[1]))]
def sha(v):
    return hashlib.sha256(json.dumps(v, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
