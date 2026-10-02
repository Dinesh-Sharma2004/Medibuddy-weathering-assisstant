from pathlib import Path
import pytest
from weather_advisor.sops import load_sops

FIXTURE = Path(__file__).parent / "fixtures" / "sops_fixture.yaml"

@pytest.fixture(scope="session")
def fixture_sops():
    return load_sops(FIXTURE)
