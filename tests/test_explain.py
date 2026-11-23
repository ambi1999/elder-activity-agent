"""The LLM explanation and its template fallback (story E-4): the alert never depends on the LLM."""

from datetime import UTC, datetime

from app import explain
from app.rules import INACTIVITY, Finding

FINDING = Finding(INACTIVITY, since=datetime(2026, 11, 22, 23, 5, tzinfo=UTC))
FACTS = explain.Facts(since_local="9:05 am", hours=4, steps_today=120, battery=0.58, minutes_since_data=3)


class FakeModels:
    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.prompts = answer, error, []

    def generate_content(self, model, contents, config):
        self.prompts.append(contents)
        if self.error:
            raise self.error
        return type("Response", (), {"text": self.answer})()


def use_fake_llm(monkeypatch, models):
    monkeypatch.setenv("GEMINI_API_KEY", "key-for-tests")
    monkeypatch.setattr(explain.genai, "Client", lambda **kwargs: type("Client", (), {"models": models})())


def test_without_an_api_key_the_template_is_used(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert explain.explain(FINDING, FACTS, "Template.", 10) == explain.Explanation("Template.", "template")


def test_llm_answer_is_used_and_sees_summaries_only(monkeypatch):
    models = FakeModels(answer="  They have not moved since 9:05 am.  ")
    use_fake_llm(monkeypatch, models)
    assert explain.explain(FINDING, FACTS, "Template.", 10) == explain.Explanation(
        "They have not moved since 9:05 am.", "llm"
    )
    [prompt] = models.prompts
    assert "Steps today: 120" in prompt and "58%" in prompt
    assert "Mum" not in prompt


def test_llm_failure_or_empty_answer_falls_back_to_the_template(monkeypatch):
    use_fake_llm(monkeypatch, FakeModels(error=TimeoutError("slow")))
    assert explain.explain(FINDING, FACTS, "Template.", 10).source == "template"
    use_fake_llm(monkeypatch, FakeModels(answer=""))
    assert explain.explain(FINDING, FACTS, "Template.", 10).source == "template"


def test_long_answers_are_cut_at_a_sentence():
    text = "First sentence. " + "word " * 200
    assert explain._trim(text) == "First sentence."
