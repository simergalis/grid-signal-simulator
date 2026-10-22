"""Reuse the pinned Phase 4 observer, with D3-only output adaptations in memory."""
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "phase4/stream_worker.py"
code = SOURCE.read_text()
old = '''    row = {k: v for k, v in row.items() if k not in pins.EXCLUDED}
    physical.update(pins.encoded(row))
    count += 1
    emit(dict(kind="tick", physical=row, observation=last_observation))'''
new = '''    reporting = {k: row.get(k) for k in ("frequency_valid", "protection_configured")}
    row = {k: v for k, v in row.items()
           if k not in pins.EXCLUDED and k not in reporting}
    physical.update(pins.encoded(row))
    count += 1
    emit(dict(kind="tick", physical=row, reporting=reporting))'''
assert old in code
code = code.replace(old, new)
code = code.replace(
    "digest.update(pins.encoded(row))",
    'digest.update(pins.encoded({k: v for k, v in row.items() '
    'if k not in ("frequency_valid", "protection_configured")}))',
)
# The old observer retained full refusal event lists in summaries. Keep only
# count+hash so evidence is bounded, not a full per-tick export.
code = code.replace(
    '    emit(dict(kind="summary", physical_sha256=physical.hexdigest(), ticks=count,',
    '''    if isinstance(record, dict):
        detail = record.pop("stop_floor_refusals", None)
        if detail is not None:
            record["audit_stop_floor_refusals"] = dict(
                count=len(detail), sha256=hashlib.sha256(pins.encoded(detail)).hexdigest())
    emit(dict(kind="summary", physical_sha256=physical.hexdigest(), ticks=count,''',
)
exec(compile(code, str(SOURCE), "exec"))
