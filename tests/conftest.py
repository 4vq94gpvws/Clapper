import pytest


@pytest.fixture(autouse=True)
def work(tmp_path, monkeypatch):
    """Every test gets its own work directory and no real API keys."""
    monkeypatch.setenv("CLAPPER_WORK", str(tmp_path / "work"))
    (tmp_path / "work").mkdir()
    for key in ("GROQ_API_KEY", "PEXELS_API_KEY", "UNSPLASH_ACCESS_KEY", "GROQ_TTS_MODEL"):
        monkeypatch.delenv(key, raising=False)
    return tmp_path / "work"
