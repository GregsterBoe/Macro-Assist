"""Add .macro-assist/ to sys.path so test modules can import pipeline code."""
import sys
from pathlib import Path

_MACRO_ASSIST = Path(__file__).resolve().parent.parent
if str(_MACRO_ASSIST) not in sys.path:
    sys.path.insert(0, str(_MACRO_ASSIST))

# Load .env from the repo root so integration tests (FRED_API_KEY, ANTHROPIC_API_KEY)
# work locally without having to export env vars manually.
try:
    from dotenv import load_dotenv
    load_dotenv(_MACRO_ASSIST.parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on shell env vars
