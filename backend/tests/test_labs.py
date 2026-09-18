import uuid

from app.models.lab import Lab, LabAccreditation, LabTestCategory


def test_create_and_retrieve_lab(db_session):
    lab = Lab(id=str(uuid.uuid4()), name="Test Lab", city="Test City", state="Test State", contact="test@example.com")
    lab.accreditations = [LabAccreditation(accreditation="NABL")]
    lab.test_categories = [LabTestCategory(category="Electronics")]
    db_session.add(lab)
    db_session.commit()

    fetched = db_session.get(Lab, lab.id)
    assert fetched is not None
    assert fetched.accreditations[0].accreditation == "NABL"
    assert fetched.test_categories[0].category == "Electronics"


def test_labs_endpoint_empty_by_default(client):
    response = client.get("/api/labs")
    assert response.status_code == 200
    assert response.json() == []


def test_labs_search_by_city(client):
    from app.db.session import get_db
    from app.main import app

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    lab = Lab(id=str(uuid.uuid4()), name="Chennai Lab", city="Chennai", state="Tamil Nadu", contact="a@b.com")
    db.add(lab)
    db.commit()
    db.close()

    response = client.get("/api/labs?search=chennai")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["city"] == "Chennai"
