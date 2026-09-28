"""Writer driven by transcribed layouts. Never truncate data to fit a field."""
from pathlib import Path
from functools import lru_cache
from .common import ROOT, load


@lru_cache(maxsize=1)
def layouts():
    return load(ROOT/'config/layout_v500.json')['records']


def encode_record(record):
    layout=layouts()[record['record_type']]
    expected={f['name'] for f in layout['fields']}
    if set(record)!=expected:
        raise ValueError(f'fields mismatch: {set(record)^expected}')
    parts=[]
    for f in layout['fields']:
        text=str(record[f['name']])
        if len(text)>f['width']:
            raise ValueError('field overflow: '+f['name'])
        if f['kind']=='n':
            if not text.isascii() or not text.isdigit():
                raise ValueError('invalid numeric: '+f['name'])
            text=text.zfill(f['width'])
        else:
            text=text.ljust(f['width'])
        raw=text.encode('iso-8859-1',errors='strict')
        if any(b<32 or 127<=b<=159 for b in raw):
            raise ValueError('forbidden character')
        parts.append(raw)
    value=b''.join(parts)
    if len(value)!=layout['length']:
        raise ValueError('byte length mismatch')
    return value


def serialize(details,period,sequence=0,reporter=None,entity=None):
    cfg=load(ROOT/'config/reporting.json')
    if not 0<=sequence<=99:
        raise ValueError('sequence out of range')
    reporter=reporter or cfg['synthetic_reporter_cuit']
    entity=entity or cfg['synthetic_entity_code']
    header=dict(record_type='01',reporter_cuit=reporter,period=period,sequence=sequence,
                entity_code=entity,tax='0103',concept='911',form='0943',filler='',
                version='00500',no_activity=int(not details))
    data=b'\r\n'.join(encode_record(r) for r in [header]+details)+b'\r\n'
    name=f'F0943.{reporter}.{period}00.{sequence:04}.txt'
    return name,data
