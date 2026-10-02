"""Wires the production graph (real Open-Meteo, real LLM). Used by the Streamlit app and the eval runner."""
from __future__ import annotations

import os
from pathlib import Path

from .graph import build_graph
from .llm import make_composer, make_llm, make_parser
from .weather import OpenMeteoClient

DEFAULT_SOP_FILE = Path(__file__).resolve().parents[2] / "sops" / "sops.yaml"


def build_default_app(sop_file: str | Path | None = None, client=None, llm=None):
    """sop_file: argument > SOP_FILE env var > sops/sops.yaml. Raises RuntimeError if OpenAI env is missing."""
    llm = llm or make_llm()
    return build_graph(sop_file or os.environ.get("SOP_FILE") or DEFAULT_SOP_FILE,
                       client or OpenMeteoClient(), make_parser(llm), make_composer(llm))
