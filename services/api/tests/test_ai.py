"""AI adapter tests with a stub client (no network, no real key)."""

from types import SimpleNamespace

import pytest
from mlforge_api import ai
from mlforge_api.db import init_engine, session_factory
from mlforge_api.runtime import migrate
from pydantic import SecretStr

from tests.conftest import make_settings


class StubMessages:
    def __init__(self, reply="Подумай, что возвращает input().", stop="end_turn"):
        self.calls = []
        self.reply, self.stop = reply, stop

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            stop_reason=self.stop,
            model=kwargs["model"],
            content=[SimpleNamespace(type="text", text=self.reply)],
            usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0),
        )


def stub_client(**kw):
    msgs = StubMessages(**kw)
    return SimpleNamespace(beta=SimpleNamespace(messages=msgs)), msgs


@pytest.fixture
def db(tmp_path):
    settings = make_settings(tmp_path).model_copy(update={"anthropic_api_key": SecretStr("sk-test")})
    init_engine(settings.resolved_database_url)
    migrate(settings)
    with session_factory()() as s:
        yield settings, s


def ask(settings, s, client, question="почему ошибка?", data="<code>"):
    return ai.ask_mentor(
        settings,
        s,
        purpose="hint_coach",
        profile_id=None,
        locale="ru",
        learner_data=data,
        question=question,
        client=client,
    )


def test_reply_cost_and_logging(db):
    settings, s = db
    client, msgs = stub_client()
    reply = ask(settings, s, client)
    assert reply.text.startswith("Подумай")
    # $4/M input + $20/M output for the default model
    assert reply.estimated_cost == pytest.approx(1000 * 4 / 1e6 + 200 * 20 / 1e6)
    call = msgs.calls[0]
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "<learner_data>" in call["messages"][0]["content"]
    assert ai.usage_today(s)["requests"] == 1


def test_unknown_model_price_is_not_invented(db):
    settings, s = db
    settings = settings.model_copy(update={"ai_model": "some-future-model"})
    client, _ = stub_client()
    assert ask(settings, s, client).estimated_cost is None


def test_daily_request_limit_blocks_before_calling(db):
    settings, s = db
    s.add(ai.AppSetting(key="ai_daily_request_limit", value=1))
    s.commit()
    client, msgs = stub_client()
    ask(settings, s, client)
    with pytest.raises(ai.AIUnavailable) as exc:
        ask(settings, s, client)
    assert exc.value.code == "ai_budget_exceeded" and len(msgs.calls) == 1


def test_refusal_and_missing_key(db):
    settings, s = db
    client, _ = stub_client(stop="refusal")
    with pytest.raises(ai.AIUnavailable) as exc:
        ask(settings, s, client)
    assert exc.value.code == "ai_refused"
    with pytest.raises(ai.AIUnavailable) as exc:
        ask(settings.model_copy(update={"anthropic_api_key": None}), s, client)
    assert exc.value.code == "ai_unavailable"


def test_learner_text_is_truncated_to_context_limit(db):
    settings, s = db
    client, msgs = stub_client()
    ask(settings, s, client, data="x" * 50_000)
    assert len(msgs.calls[0]["messages"][0]["content"]) < 14_000
