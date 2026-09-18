from app.db.seed import seed_labs, seed_schemes, seed_standards
from app.models.lab import Lab
from app.models.certification_scheme import CertificationScheme
from app.models.standard import Standard


def test_seed_creates_expected_counts(db_session):
    standards_created = seed_standards(db_session)
    schemes_created = seed_schemes(db_session)
    labs_created = seed_labs(db_session)

    assert standards_created == 8
    assert schemes_created == 4
    assert labs_created == 6


def test_seed_marks_all_rows_as_demo(db_session):
    seed_standards(db_session)
    seed_schemes(db_session)
    seed_labs(db_session)

    assert all(s.source_type == "demo" for s in db_session.query(Standard).all())
    assert all(s.source_type == "demo" for s in db_session.query(CertificationScheme).all())
    assert all(lab.source_type == "demo" for lab in db_session.query(Lab).all())


def test_seed_is_idempotent(db_session):
    seed_standards(db_session)
    second_run_created = seed_standards(db_session)
    assert second_run_created == 0
    assert db_session.query(Standard).count() == 8
