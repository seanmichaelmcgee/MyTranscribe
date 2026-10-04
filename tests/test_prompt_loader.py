"""prompt_loader: bundled medical prompt, overrides, truncation."""

from prompt_loader import DEFAULT_PROMPT_FILE, MAX_PROMPT_CHARS, fit_text_budget, load_prompt


def test_default_prompt_is_medical_and_fits_budget():
    text = load_prompt(env={})
    assert DEFAULT_PROMPT_FILE.exists()
    assert "apixaban" in text and "\n" not in text
    assert 200 < len(text) <= MAX_PROMPT_CHARS


def test_env_override(tmp_path):
    f = tmp_path / "mine.txt"
    f.write_text("Dear Dr. Smith,\n  metoprolol  ", encoding="utf-8")
    assert load_prompt(env={"MYTRANSCRIBE_PROMPT_FILE": str(f)}) == "Dear Dr. Smith, metoprolol"


def test_missing_file_returns_empty(tmp_path):
    assert load_prompt(path=str(tmp_path / "nope.txt"), env={}) == ""


def test_long_prompt_keeps_the_end_on_a_word_boundary(tmp_path):
    f = tmp_path / "long.txt"
    f.write_text("word " * 600 + "IMPORTANT_TERM", encoding="utf-8")
    text = load_prompt(path=str(f), env={})
    assert len(text) <= MAX_PROMPT_CHARS
    assert text.endswith("IMPORTANT_TERM") and text.startswith("word")


def test_token_fit_preserves_normal_text_and_whole_word_suffix():
    count = lambda text: len(text.split())
    assert fit_text_budget("  preserved spacing  ", count, 3) == "  preserved spacing  "
    assert fit_text_budget("opening words important clinical terms", count, 3) == "important clinical terms"
    assert fit_text_budget("one", count, 0) == ""
    assert fit_text_budget("", count, 0) == ""


def test_token_fit_reserves_space_for_other_prompt_content():
    count = lambda text: len((text + " recent dictated context").split())
    assert fit_text_budget("old example important terms", count, 5) == "important terms"
