"""Tests for cli/config.py — the sim.yml models + loader. Foundation module,
implemented and frozen, so these should pass now (no xfail guard)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ghostpanel.cli.config import (
    DEFAULT_CONFIG_YAML,
    Flow,
    IcpCfg,
    SimConfig,
    load_config,
)


def test_default_yaml_parses_into_valid_config(tmp_path):
    p = tmp_path / "sim.yml"
    p.write_text(DEFAULT_CONFIG_YAML, encoding="utf-8")
    cfg = load_config(p)
    assert isinstance(cfg, SimConfig)
    assert cfg.version == 1
    assert cfg.flows  # at least one flow
    flow = cfg.flow()  # first flow, no name
    assert flow.name == "signup"
    assert flow.url.startswith("https://")
    assert flow.fail_under == "last-passing"
    assert cfg.swarm.rpm == 5
    assert cfg.output.dir == ".sim"


def test_load_config_missing_file_raises_readable_valueerror(tmp_path):
    missing = tmp_path / "nope.yml"
    with pytest.raises(ValueError) as exc:
        load_config(missing)
    assert "not found" in str(exc.value).lower()


def test_load_config_non_mapping_raises_valueerror(tmp_path):
    p = tmp_path / "sim.yml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        load_config(p)
    assert "mapping" in str(exc.value).lower()


def test_load_config_bad_fail_under_raises(tmp_path):
    p = tmp_path / "sim.yml"
    p.write_text(
        "version: 1\n"
        "flows:\n"
        "  - name: signup\n"
        "    url: https://example.com/signup\n"
        "    task: sign up\n"
        "    fail_under: 1.5\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_config(p)


def test_flow_fail_under_accepts_float_and_last_passing():
    assert Flow(url="https://x.com", task="t", fail_under=0.8).fail_under == 0.8
    assert (
        Flow(url="https://x.com", task="t", fail_under="last-passing").fail_under
        == "last-passing"
    )


def test_flow_fail_under_rejects_out_of_range_and_bogus_string():
    with pytest.raises(ValidationError):
        Flow(url="https://x.com", task="t", fail_under=1.5)
    with pytest.raises(ValidationError):
        Flow(url="https://x.com", task="t", fail_under="bogus")


def test_icp_persona_ids_auto_returns_none():
    assert IcpCfg(personas="auto").persona_ids() is None


def test_icp_persona_ids_list_returns_list():
    ids = IcpCfg(personas=["grandma-72", "power-user"]).persona_ids()
    assert ids == ["grandma-72", "power-user"]


def test_simconfig_flow_resolves_by_name_and_default():
    cfg = SimConfig(
        flows=[
            Flow(name="a", url="https://x.com", task="ta"),
            Flow(name="b", url="https://y.com", task="tb"),
        ]
    )
    assert cfg.flow("b").url == "https://y.com"
    assert cfg.flow().name == "a"  # first when unnamed


def test_simconfig_flow_unknown_name_raises():
    cfg = SimConfig(flows=[Flow(name="a", url="https://x.com", task="t")])
    with pytest.raises(ValueError):
        cfg.flow("does-not-exist")


def test_simconfig_flow_no_flows_raises():
    with pytest.raises(ValueError):
        SimConfig(flows=[]).flow()
