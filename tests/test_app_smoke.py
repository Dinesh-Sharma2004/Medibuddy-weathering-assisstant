"""Streamlit AppTest: the UI starts, shows a clear error without credentials, and wires thread/new-chat state."""
from pathlib import Path

import dotenv
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from helpers import GEO, ScriptedParser, full_snapshot, intent
from conftest import FIXTURE

APP = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture(autouse=True)
def isolate(monkeypatch):
    """Tests must not depend on (or spend) the developer's real .env: ignore it and drop cached apps."""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def test_app_shows_error_without_credentials(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.chdir(tmp_path)   # no .env here
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    assert at.error and "OPENAI_API_KEY" in at.error[0].value


def test_app_chat_flow_with_stubbed_graph(monkeypatch):
    from weather_advisor import factory
    from weather_advisor.graph import build_graph
    from weather_advisor.weather import FixtureClient
    monkeypatch.setattr(factory, "build_default_app", lambda *a, **k: build_graph(
        FIXTURE, FixtureClient(full_snapshot(current={"wind_speed_10m": 50}), GEO),
        ScriptedParser(intent(location_text="Bhopal", activities=["cycling"], question_types=["safety_check"]),
                       intent(location_text="Bhopal", activities=["cycling"], question_types=["safety_check"]))))
    at = AppTest.from_file(str(APP), default_timeout=120).run()
    first_thread = at.session_state.thread_id
    at.chat_input[0].set_value("bike?").run()
    assert any("FX-WIND-01" in m.value for m in at.markdown) or any("FX-WIND-01" in str(x) for x in at.main)
    assert len(at.session_state.history) == 2 and at.expander[0].label == "Why this answer"
    at.sidebar.button[0].click().run()
    assert at.session_state.thread_id != first_thread and at.session_state.history == []
