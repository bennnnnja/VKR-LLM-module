from __future__ import annotations


def test_health_public(client):
    assert client.get("/health").status_code == 200


def test_config_public(client):
    r = client.get("/config")
    assert r.status_code == 200
    body = r.json()
    assert "tasks" in body
    assert "evaluate" in body["tasks"]
    assert body["tasks"]["evaluate"]["target_model"] == "qwen2.5:32b-instruct"
    # В тестовом окружении доступна только qwen2.5:32b-instruct
    assert body["tasks"]["testcases"]["model_resolution"] == "stub"
    assert "API_KEY" not in body
    assert "redis" not in body


def test_sandbox_public(client):
    r = client.get("/sandbox")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "POST /evaluate/task" in r.text
    assert "X-API-Key" in r.text


def test_ui_kit_public(client):
    r = client.get("/ui-kit")
    assert r.status_code == 200
    assert "<job-poller" in r.text
    assert "<evaluate-form" in r.text
    assert "<recommendations-list" in r.text


def test_static_styles(client):
    r = client.get("/static/styles.css")
    assert r.status_code == 200
    assert "text/css" in r.headers["content-type"]


def test_component_scripts(client):
    for name in ("job-poller", "evaluate-form", "recommendations-list"):
        r = client.get(f"/static/components/{name}.js")
        assert r.status_code == 200, name
        assert "customElements.define" in r.text
