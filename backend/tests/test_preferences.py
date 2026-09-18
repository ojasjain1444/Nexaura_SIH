def test_default_preferences(client):
    response = client.get("/api/preferences")
    assert response.status_code == 200
    assert response.json() == {"language": "en"}


def test_update_language_persists(client):
    update_response = client.put("/api/preferences", json={"language": "hi"})
    assert update_response.status_code == 200
    assert update_response.json() == {"language": "hi"}

    get_response = client.get("/api/preferences")
    assert get_response.json() == {"language": "hi"}
