import uuid

from app.models.certification_scheme import CertificationScheme, CertificationStep, SchemeEligibility


def test_create_and_retrieve_scheme_with_steps(db_session):
    scheme = CertificationScheme(
        id=str(uuid.uuid4()),
        name="Test Scheme",
        type="product-certification",
        summary="Test summary",
        average_duration_days=30,
        fees="Test fees",
    )
    scheme.steps = [CertificationStep(order=1, title="Step One", description="Do the first thing")]
    scheme.eligibility_items = [SchemeEligibility(order=1, requirement="Must be eligible")]
    db_session.add(scheme)
    db_session.commit()

    fetched = db_session.get(CertificationScheme, scheme.id)
    assert fetched is not None
    assert fetched.steps[0].title == "Step One"
    assert fetched.eligibility_items[0].requirement == "Must be eligible"


def test_scheme_name_must_be_unique(db_session):
    db_session.add(
        CertificationScheme(
            id=str(uuid.uuid4()), name="Unique Scheme", type="hallmarking", summary="s", average_duration_days=1, fees="f"
        )
    )
    db_session.commit()

    db_session.add(
        CertificationScheme(
            id=str(uuid.uuid4()), name="Unique Scheme", type="hallmarking", summary="s", average_duration_days=1, fees="f"
        )
    )
    try:
        db_session.commit()
        assert False, "expected a uniqueness constraint violation"
    except Exception:
        db_session.rollback()


def test_certification_list_endpoint_empty_by_default(client):
    response = client.get("/api/certification")
    assert response.status_code == 200
    assert response.json() == []


def test_get_certification_scheme_not_found(client):
    response = client.get("/api/certification/does-not-exist")
    assert response.status_code == 404
