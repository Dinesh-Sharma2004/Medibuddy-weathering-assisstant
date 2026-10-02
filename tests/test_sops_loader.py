import copy
from pathlib import Path

import pytest
import yaml

from weather_advisor.sops import SOPError, load_sops, validate_sops
from conftest import FIXTURE

ROOT = Path(__file__).parent.parent


def raw():
    return yaml.safe_load(FIXTURE.read_text())


def errors_for(mut):
    d = raw()
    mut(d)
    with pytest.raises(SOPError) as e:
        validate_sops(d)
    return "\n".join(e.value.errors)


def test_fixture_loads_and_meets_shape(fixture_sops):
    assert len(fixture_sops.sops) >= 10
    assert len({s.category for s in fixture_sops.sops}) >= 3
    assert len({s.severity for s in fixture_sops.sops}) >= 3
    assert any(s.override for s in fixture_sops.sops)
    assert any("score" in s.condition for s in fixture_sops.sops)


def test_required_fields_union(fixture_sops):
    rf = fixture_sops.required_fields()
    assert "uv_index" in rf["hourly"] and "precipitation_sum" in rf["daily"]


def test_real_sops_file_loads_and_meets_shape():
    """The production SOP file must pass the same validator and the assignment's minimum shape."""
    sops = load_sops(ROOT / "sops" / "sops.yaml")
    assert len(sops.sops) >= 10
    assert len({s.category for s in sops.sops}) >= 3
    assert len({s.severity for s in sops.sops}) >= 2
    assert any(s.override for s in sops.sops)


def test_incomplete_todo_skeleton_is_rejected():
    """An unfinished SOP file (TODO placeholders, as in the original skeleton) is rejected, never silently accepted."""
    d = raw()
    sop = d["sops"][0]
    sop["id"] = "TODO_ID"
    sop["severity"] = "TODO_lowest"
    sop["applies_to"]["activities"] = ["TODO_activity_tag"]
    with pytest.raises(SOPError) as e:
        validate_sops(d)
    msg = "\n".join(e.value.errors)
    assert "id does not match meta.id_pattern" in msg
    assert "severity 'TODO_lowest' not in meta.severities" in msg
    assert "unknown tag 'TODO_activity_tag'" in msg


def test_duplicate_id():
    assert "duplicate id" in errors_for(lambda d: d["sops"][1].update(id=d["sops"][0]["id"]))


def test_unknown_field_and_operator():
    assert "unknown field 'colour'" in errors_for(lambda d: d["sops"][0].update(colour="x"))
    def bad_op(d):
        d["sops"][1]["condition"]["compare"]["op"] = "~"
    assert "unknown operator" in errors_for(bad_op)


def test_missing_advice():
    def f(d): del d["sops"][0]["advice"]
    assert "missing 'advice'" in errors_for(f)


def test_unknown_tag_and_bad_applies_to():
    def f(d): d["sops"][0]["applies_to"]["activities"] = ["flying"]
    assert "unknown tag 'flying'" in errors_for(f)
    def g(d): d["sops"][0]["applies_to"]["groups"] = []
    assert "non-empty tag list or 'any'" in errors_for(g)
    def h(d): del d["sops"][0]["applies_to"]["groups"]
    assert "applies_to.groups" in errors_for(h)


def test_condition_field_must_be_in_requires():
    def f(d): d["sops"][1]["requires"] = [{"field": "temperature_2m", "source": "current"}]
    assert "not listed in requires" in errors_for(f)


def test_unknown_placeholder():
    def f(d): d["sops"][1]["advice"] = "wind is {gust}"
    assert "placeholder {gust}" in errors_for(f)


def test_bad_severity_and_disclose():
    def f(d): d["sops"][0]["severity"] = "apocalyptic"
    assert "not in meta.severities" in errors_for(f)
    def g(d): d["meta"]["disclose_unknown_from"] = "nope"
    assert "disclose_unknown_from" in errors_for(g)


def test_bad_window_and_score():
    def f(d): d["sops"][0]["condition"]["window_agg"]["window"] = {"fixed_local": {"start": "16:00", "end": "11:00"}}
    assert "start must be before end" in errors_for(f)
    def g(d): d["sops"][9]["condition"]["score"]["terms"][0]["bands"][0]["points"] = 2
    assert "points must be" in errors_for(g)
    def h(d): d["sops"][9]["condition"]["score"]["terms"][0]["agg"] = "max"
    assert "only valid with source: hourly" in errors_for(h)


def test_missing_message():
    def f(d): del d["messages"]["data_unavailable"]
    assert "messages.data_unavailable" in errors_for(f)


def test_default_time_reference_must_have_window():
    def f(d): d["meta"]["default_time_reference"] = "nonexistent"
    assert "default_time_reference" in errors_for(f)


def test_only_disclosure_message_may_have_placeholders():
    def f(d): d["messages"]["no_guidance"] = "no {thing}"
    assert "placeholder {thing} not allowed" in errors_for(f)


def test_id_pattern_enforced():
    def f(d): d["meta"]["id_pattern"] = "ZZ-[0-9]+"
    assert "does not match meta.id_pattern" in errors_for(f)
    def g(d): d["meta"]["id_pattern"] = "(unclosed"
    assert "not a valid regex" in errors_for(g)
    def h(d): del d["meta"]["id_pattern"]
    assert "missing 'id_pattern'" in errors_for(h)
