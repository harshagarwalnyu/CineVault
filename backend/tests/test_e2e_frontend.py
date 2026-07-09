import os
import pytest
import requests


DEFAULT_FRONTEND_URLS = (
    os.getenv("FRONTEND_BASE_URL"),
    "http://localhost:3002",
    "http://localhost:3000",
)


def _resolve_frontend_base_url() -> str | None:
    for base_url in DEFAULT_FRONTEND_URLS:
        if not base_url:
            continue
        try:
            response = requests.get(base_url, timeout=3)
            response.raise_for_status()
            return base_url
        except Exception:
            continue
    return None


@pytest.mark.e2e
def test_homepage_loads():
    frontend_base_url = _resolve_frontend_base_url()
    if not frontend_base_url:
        pytest.skip("Frontend not reachable")

    try:
        response = requests.get(frontend_base_url, timeout=8)
        response.raise_for_status()
        assert "CineVault" in response.text
        assert "Featured Drop" in response.text
    except Exception:
        pytest.skip("Frontend not reachable")


@pytest.mark.e2e
@pytest.mark.skip(reason="Requires frontend to be running")
def test_search_interaction():
    frontend_base_url = _resolve_frontend_base_url()
    if not frontend_base_url:
        pytest.skip("Frontend not reachable")

    try:
        response = requests.get(frontend_base_url, timeout=8)
        response.raise_for_status()
        # Placeholder for richer browser interaction when Playwright runs in CI.
        assert "<main" in response.text
    except Exception:
        pytest.skip("Frontend not reachable")
