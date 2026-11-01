"""Les tests utilisent des dossiers temporaires : ils ne touchent jamais à tes vraies données."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="fusee-tests-"))
os.environ["FUSEE_DATA_DIR"] = str(_tmp / "data")
os.environ["FUSEE_WORKSPACE"] = str(_tmp / "workspace")
os.environ["NTFY_TOPIC"] = ""
os.environ.pop("PUBLIC_URL", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def no_real_notifications(monkeypatch):
    from fusee_agents import notify
    monkeypatch.setattr(notify, "_deliver", lambda *a, **k: None)
