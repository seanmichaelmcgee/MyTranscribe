"""Settings suite (milestone 1): clinical-field scoring, references for incomplete clips, profiles."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import settings_suite as ss  # noqa: E402
from tuning import sets  # noqa: E402
from tuning.score import clinical_errors  # noqa: E402


def test_clinical_fields_count_numbers_negations_and_drugs():
    ref = "No fever. Start ramipril 5 mg daily, not 10."
    meds = {"ramipril"}
    assert clinical_errors(ref, ref, meds.__contains__) == {
        "numbers": 0, "numbers_of": 2, "negations": 0, "negations_of": 2, "medical": 0, "medical_of": 1}
    got = clinical_errors(ref, "Fever. Start ramipril 15 mg daily, not 10, no.", meds.__contains__)
    assert (got["numbers"], got["negations"], got["medical"]) == (1, 2, 0)   # 5 -> 15; "No" dropped; "no" added
    assert clinical_errors(ref, "No fever. Start rampart 5 mg daily, not 10.", meds.__contains__)["medical"] == 1


def test_every_style_has_a_wizard_answer_and_marks_share_one_decode():
    assert set(ss.MATCH) == set(sets.STYLES) and set(ss.MATCH.values()) <= set(ss.PROFILES)
    assert ss.PROFILES["every"]["group"] == ss.PROFILES["some"]["group"] != ss.PROFILES["talk"]["group"]
    assert ss.DEFAULT == "talk"


def test_final_text_applies_the_profiles_text_options():
    raw = "No fever comma no cough period New paragraph BP 138 over 78 period"
    assert ss.final_text(raw, ss.PROFILES["every"]) == "No fever, no cough.\n\nBP 138/78."
    assert "comma" in ss.final_text(raw, ss.PROFILES["talk"])


def test_an_incomplete_clip_is_scored_without_what_the_voice_skipped():
    item = {"reference": "Thank you for seeing him.\n\nKind regards,\nDr. Owen Gallagher"}
    assert ss.reference_for(item, None) == item["reference"]
    assert ss.reference_for(item, {"flagged": False}) == item["reference"]
    whole = {"flagged": True, "gaps": [["full stop new paragraph kind regards comma new line doctor owen gallagher", ""]]}
    assert ss.reference_for(item, whole) == "Thank you for seeing him."
    name = {"flagged": True, "gaps": [["doctor owen gallagher", ""]]}
    assert ss.reference_for(item, name) == "Thank you for seeing him.\n\nKind regards,"
    other = {"flagged": True, "gaps": [["no vitamin k is needed", ""]]}
    assert ss.reference_for(item, other) is None


def test_names_are_found_for_name_free_scoring():
    assert ss.names_in("Dear Dr. Mbeki,\n\nI saw Mr. Tomasz Wierzbicki today.") == ["Mbeki", "Tomasz Wierzbicki"]
