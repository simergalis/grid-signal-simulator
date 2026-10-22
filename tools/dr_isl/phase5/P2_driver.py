"""Phase 5 GPU classification using the already established Phase 4 P2 protocol."""
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "phase4/P2_driver.py"
code = source.read_text().replace('"base": "ae49aaa"', '"base": "fd87fc7"')
code = code.replace("working-tree Phase 4 C2(c) + approved TC18", "working-tree Phase 5 D3 reporting")
code = code.replace('"P1": "51 passed"', '"focused": "48 passed"')
exec(compile(code, str(source), "exec"))
