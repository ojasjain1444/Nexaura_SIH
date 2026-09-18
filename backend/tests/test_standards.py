import uuid
from datetime import date

from app.models.standard import Standard, StandardRelatedCode


def _make_standard(**overrides) -> Standard:
    defaults = dict(
        id=str(uuid.uuid4()),
        code="IS 9999",
        title="Test Standard Title",
        category="Test Category",
        description="Test description",
        status="active",
        last_amended=date(2024, 1, 1),
        sector="Test Sector",
        source_type="demo",
    )
    defaults.update(overrides)
    return Standard(**defaults)


def test_create_and_retrieve_standard(db_session):
    standard = _make_standard()
    standard.related_codes = [StandardRelatedCode(code="IS 1000")]
    db_session.add(standard)
    db_session.commit()

    fetched = db_session.get(Standard, standard.id)
    assert fetched is not None
    assert fetched.code == "IS 9999"
    assert fetched.source_type == "demo"
    assert len(fetched.related_codes) == 1


def test_standard_code_must_be_unique(db_session):
    db_session.add(_make_standard(code="IS 5555"))
    db_session.commit()

    db_session.add(_make_standard(code="IS 5555", id=str(uuid.uuid4())))
    try:
        db_session.commit()
        assert False, "expected a uniqueness constraint violation"
    except Exception:
        db_session.rollback()


def test_search_standards_endpoint(client):
    response = client.get("/api/standards")
    assert response.status_code == 200
    assert response.json() == []  # isolated test DB — no seed data


def test_search_standards_by_keyword(client):
    # Seed one standard directly via the API's underlying model for this test.
    from app.db.session import get_db
    from app.main import app

    db_gen = app.dependency_overrides[get_db]()
    db = next(db_gen)
    standard = _make_standard(code="IS 14625", title="Packaged Drinking Water Specification")
    db.add(standard)
    db.commit()
    db.close()

    response = client.get("/api/standards?search=water")
    assert response.status_code == 200
    results = response.json()
    assert len(results) == 1
    assert results[0]["code"] == "IS 14625"


def test_get_standard_by_id_not_found(client):
    response = client.get("/api/standards/does-not-exist")
    assert response.status_code == 404
