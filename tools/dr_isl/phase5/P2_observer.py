"""Read-only Phase 4 P2 observer, reused verbatim in the Phase 5 evidence folder."""
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "phase4/P2_observer.py"
exec(compile(source.read_text(), str(source), "exec"))
