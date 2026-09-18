"""
Plain-chat answer safety: standard-number comparison and off-corpus trimming.

Two failures are covered here. The guardrail compared raw matched text, so
evidence reading "IS 456" did not match an answer saying "IS 456:2000" — the
correctly cited standard was reported as fabricated and every real answer
was replaced with a bare list of filenames. Separately, when retrieval has
nothing on topic, the model states that honestly and then supplies remembered
standards and laboratory names anyway; the prompt does not stop it, so the
continuation is cut here.
"""

from app.product.response_safety import (
    append_unverified_standards_warning,
    check_plain_chat_response_safety,
    trim_off_corpus_speculation,
)
from app.schemas.retrieval import RetrievedChunk


def _chunk(text: str, name: str = "IS_456_2000.pdf") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="c",
        document_id="d",
        document_name=name,
        document_type=None,
        page_number=1,
        section=None,
        text=text,
        similarity_score=0.85,
    )


EVIDENCE = [_chunk("Concrete shall conform to IS 456 and reinforcement to IS 1786.")]


def test_year_and_part_suffixes_do_not_make_a_real_standard_look_fabricated():
    for citation in ("IS 456", "IS 456:2000", "IS 456-2000", "IS456", "IS 456 (Part 1)"):
        assert check_plain_chat_response_safety(f"As per {citation}, use M20.", EVIDENCE) == []


def test_standard_named_only_by_the_source_filename_is_known():
    """Filenames use underscores and dots (IS_456_2000.pdf,
    gov.in.is.302.2.201.2008.pdf), which the standard-number pattern does not
    match, so document names contributed nothing to the known set."""
    evidence = [_chunk("Particular requirements for fans.", name="gov.in.is.302.2.21.2011.pdf")]
    assert check_plain_chat_response_safety("See IS 302 for appliance safety.", evidence) == []


def test_genuinely_absent_standard_is_still_reported():
    flagged = check_plain_chat_response_safety(
        "You need IS 4561:2012 for fans and IS 16436:2020 for energy labels.", EVIDENCE
    )
    assert flagged == ["IS 16436:2020", "IS 4561:2012"]


def test_only_the_absent_standard_is_reported_from_a_mixed_answer():
    flagged = check_plain_chat_response_safety("IS 456:2000 applies here, as does IS 9999:2011.", EVIDENCE)
    assert flagged == ["IS 9999:2011"]


def test_warning_preserves_the_original_answer():
    warned = append_unverified_standards_warning("Grade M20 is required. See IS 9999.", ["IS 9999"])
    assert "Grade M20 is required." in warned
    assert "IS 9999" in warned
    assert "Unverified" in warned


def test_speculation_after_a_refusal_is_removed():
    """Told to stop after saying a topic is not covered, qwen2.5:7b still
    appended invented BIS marks and laboratory names. The cut is mechanical
    because the instruction alone does not hold."""
    answer = (
        "The retrieved documents do not cover standards for wooden chairs. They are from IS 456:2000, "
        "which concerns concrete.\n\n"
        "For wooden chair standards, you would typically refer to IS 4311:2003 (Wooden Furniture)."
    )
    trimmed = trim_off_corpus_speculation(answer)
    assert "IS 456:2000" in trimmed
    assert "IS 4311" not in trimmed
    assert "stopped there" in trimmed


def test_speculation_opening_a_new_sentence_mid_paragraph_is_removed():
    answer = (
        "The documents do not cover electric fan certification. "
        "To obtain these certifications you would send the product to an accredited BIS laboratory."
    )
    trimmed = trim_off_corpus_speculation(answer)
    assert "do not cover" in trimmed
    assert "laboratory" not in trimmed


def test_an_honest_refusal_is_left_alone():
    answer = (
        "The retrieved documents do not cover laptops. The content is from IS 456:2000, which concerns "
        "concrete structures."
    )
    assert trim_off_corpus_speculation(answer) == answer


def test_description_of_what_the_corpus_covers_is_kept():
    """The list of what the documents do contain comes before the pivot and
    is grounded, so it must survive."""
    answer = (
        "The documents do not cover shampoo certification.\n\n"
        "The documents do cover:\n"
        "- BIS certification marking\n"
        "- Routine inspection procedures\n"
    )
    trimmed = trim_off_corpus_speculation(answer)
    assert "BIS certification marking" in trimmed


def test_reaching_for_an_outside_standards_body_is_removed():
    """A sentence naming IEC/ISO/UL in an off-corpus answer is remembered
    fact regardless of how it is phrased, so it is cut even when it does not
    open with a speculation marker."""
    answer = (
        "The retrieved documents do not cover laptops. The content is from IS 456:2000, which concerns "
        "concrete. Laptops fall under the IEC and IEEE series instead."
    )
    trimmed = trim_off_corpus_speculation(answer)
    assert "IS 456:2000" in trimmed
    assert "IEC" not in trimmed
