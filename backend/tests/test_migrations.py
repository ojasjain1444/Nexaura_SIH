"""
Verifies the database initializes correctly: all expected tables exist
after Base.metadata.create_all() (used for test isolation — see
docs/DATABASE.md for why Alembic, not create_all, is used for real
dev/production migrations).
"""

from sqlalchemy import inspect

EXPECTED_TABLES = {
    "conversations",
    "messages",
    "standards",
    "standard_related_codes",
    "certification_schemes",
    "certification_steps",
    "scheme_eligibility_items",
    "labs",
    "lab_accreditations",
    "lab_test_categories",
    "user_preferences",
}


def test_all_expected_tables_exist(test_db_engine):
    inspector = inspect(test_db_engine)
    actual_tables = set(inspector.get_table_names())
    assert EXPECTED_TABLES.issubset(actual_tables)
