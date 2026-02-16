import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "libs/common-types/src"))
sys.path.insert(0, str(ROOT / "libs/exchange-adapters/src"))
sys.path.insert(0, str(ROOT / "libs/feature-store/src"))
