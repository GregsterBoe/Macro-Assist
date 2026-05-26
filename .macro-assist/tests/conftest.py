"""Add .macro-assist/ to sys.path so test modules can import pipeline code."""
import sys
from pathlib import Path

_MACRO_ASSIST = Path(__file__).resolve().parent.parent
if str(_MACRO_ASSIST) not in sys.path:
    sys.path.insert(0, str(_MACRO_ASSIST))
