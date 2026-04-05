import sys
from pathlib import Path


def ensure_src_in_path() -> None:
    src_path = Path(__file__).resolve().parent.parent / "src"
    src = str(src_path)
    if src not in sys.path:
        sys.path.insert(0, src)
