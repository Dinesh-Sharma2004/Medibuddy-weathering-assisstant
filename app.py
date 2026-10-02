"""Streamlit chat UI. Presentation only: every decision is made by the LangGraph in src/weather_advisor."""
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent / "src"))
from weather_advisor.factory import build_default_app  # noqa: E402
from weather_advisor.graph import ask  # noqa: E402

st.title("Weather-Advisory Support Bot")


@st.cache_resource
def get_app():
    return build_default_app()   # one graph + MemorySaver shared by all browser sessions; threads keep them apart


try:
    app = get_app()
except Exception as e:
    st.error(f"Could not start: {e}")
    st.stop()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.history = []   # [{"role", "content", "trace"?}]

if st.sidebar.button("New chat"):
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.history = []
    st.rerun()

for m in st.session_state.history:
    with st.chat_message(m["role"]):
        st.write(m["content"])
        if m.get("trace"):
            with st.expander("Why this answer"):
                st.json(m["trace"], expanded=False)

if prompt := st.chat_input("Ask about an outdoor activity and the weather"):
    st.session_state.history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Checking policies and weather..."):
            result = ask(app, st.session_state.thread_id, prompt)
        st.write(result["reply"])
        with st.expander("Why this answer"):
            st.json(result["trace"], expanded=False)
    st.session_state.history.append({"role": "assistant", "content": result["reply"], "trace": result["trace"]})
