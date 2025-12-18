import sys
from pathlib import Path

# Ensure repository root is on the import path for local package imports during tests.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
