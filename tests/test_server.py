"""The web API (server.py), through FastAPI's test client."""
from fastapi.testclient import TestClient

from server import app
from src.i18n import TEXT

client = TestClient(app)


def test_health():
    assert client.get('/api/health').json() == {'ok': True}


def test_text_has_both_languages():
    body = client.get('/api/text').json()
    assert body['languages'] == {'en': 'English', 'ar': 'العربية'}
    assert body['text']['nav_live'] == list(TEXT['nav_live'])
    assert all(len(pair) == 2 for pair in body['text'].values())
