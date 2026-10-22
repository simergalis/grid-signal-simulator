"""Use the existing Phase 5 streaming worker without changing its pinning."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parents[1] / "stream_worker.py"), run_name="__main__")
