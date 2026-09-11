from fastapi.testclient import TestClient
from backend.main import app

def test_landing_site_serves_and_links_dashboard():
    with TestClient(app) as client:
        home=client.get("/")
        assert home.status_code==200
        assert "Karna OS" in home.text and "Interview Studio" in home.text
        assert 'href="/app"' in home.text

def test_dashboard_served_at_app_path():
    with TestClient(app) as client:
        dash=client.get("/app")
        assert dash.status_code==200
        assert 'data-view="home"' in dash.text and "Karna OS" in dash.text

def test_legal_pages_still_served():
    with TestClient(app) as client:
        for page in ("privacy","terms","limitations"):
            r=client.get(f"/static/{page}.html")
            assert r.status_code==200 and f"Karna OS" in r.text

def test_landing_assets_exist():
    for asset in ("landing/landing.css","landing/landing.js"):
        r=client_get(asset)
        assert r.status_code==200

def client_get(path):
    with TestClient(app) as client:
        return client.get(f"/static/{path}")
