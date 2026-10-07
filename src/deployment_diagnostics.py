"""Failure metadata only: no exception values, input, paths, or source text."""
import re,traceback
from pathlib import Path

def failure(error):
    # Exception text and source lines can contain private operand values.
    frames=traceback.extract_tb(error.__traceback__)
    location=frames[-1] if frames else None
    kind=type(error).__name__
    return dict(type=kind if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',kind) else 'Exception',
        errno=error.errno if isinstance(error,OSError) and type(error.errno) is int else None,
        source_file=Path(location.filename).name if location else None,
        source_line=location.lineno if location else None)

def filtered(value):
    """Validate actor-supplied diagnostic metadata before operator disclosure."""
    if not isinstance(value,dict):return None
    kind=value.get('type');number=value.get('errno');name=value.get('source_file');line=value.get('source_line')
    if not isinstance(kind,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}',kind):return None
    if number is not None and (type(number) is not int or not 0<=number<=4096):return None
    if name is not None and (not isinstance(name,str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,63}\.py',name)):return None
    if line is not None and (type(line) is not int or not 1<=line<=100000):return None
    return dict(type=kind,errno=number,source_file=name,source_line=line)
