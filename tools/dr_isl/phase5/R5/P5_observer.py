"""Reuse the incremental observer, writing into the R5 evidence directory."""
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "P5_observer.py"
exec(compile(source.read_text(), str(source), "exec"))
