"""Wires the production graph (real Open-Meteo, real LLM). Used by the Streamlit app and the eval runner."""
from __future__ import annotations

import os
from pathlib import Path

from .graph import build_graph
from .llm import make_advisor, make_composer, make_llm, make_parser
from .weather import OpenMeteoClient

DEFAULT_SOP_FILE = Path(__file__).resolve().parents[2] / "sops" / "sops.yaml"


def build_default_app(sop_file: str | Path | None = None, client=None, llm=None):
    """sop_file: argument > SOP_FILE env var > sops/sops.yaml. Raises RuntimeError if OpenAI env is missing.

    By default the app uses the **deterministic** decision path: code matches SOPs, evaluates conditions and
    picks the answer (advise / reassure / clarify / data_unavailable / no_guidance); the model only parses
    intent and rephrases the chosen advice. This is the path the eval suites verify and keeps the safety
    decision in code (no reviewer red flag).

    Set WA_LLM_REASONER=1 to opt into the experimental LLM-reasoner path, where the model decides which SOP is
    relevant and how to frame it, guardrailed by verify_advice against the deterministically-assessed SOPs,
    with a deterministic fallback. (It is documented as an alternative, not the default.)
    """
    llm = llm or make_llm()
    advisor = make_advisor(llm) if os.environ.get("WA_LLM_REASONER") else None
    return build_graph(sop_file or os.environ.get("SOP_FILE") or DEFAULT_SOP_FILE,
                       client or OpenMeteoClient(), make_parser(llm), make_composer(llm), advisor=advisor)
