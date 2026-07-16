"""`sim.yml` configuration models. FROZEN — see PHASE1_SPEC.md.

The config is intentionally small for Phase 1 (one flow is enough to sell the CI
gate) but list-shaped everywhere a customer will later want many. Marketing
vocabulary is load-bearing: a `flow` (url + task + success), an `icp` (which
persona segments), and a per-flow `fail_under` that is either an absolute
completion bar or the string ``"last-passing"`` (regress-vs-baseline).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

FailUnder = Union[float, Literal["last-passing"]]


class Flow(BaseModel):
    """One behavioral test: point the swarm at a URL with a goal and a bar."""

    model_config = ConfigDict(extra="forbid")
    name: str = "default"
    url: str
    task: str
    fail_under: FailUnder = "last-passing"
    # Optional per-flow persona override; falls back to SimConfig.icp.personas.
    personas: list[str] | None = None

    @field_validator("fail_under")
    @classmethod
    def _valid_fail_under(cls, v: FailUnder) -> FailUnder:
        if isinstance(v, str) and v != "last-passing":
            raise ValueError('fail_under must be a number 0..1 or "last-passing"')
        if isinstance(v, (int, float)) and not (0.0 <= float(v) <= 1.0):
            raise ValueError("fail_under as a number must be between 0 and 1")
        return v


class IcpCfg(BaseModel):
    """Which behavioral segments to send. ``"auto"`` => the full bundled roster."""

    model_config = ConfigDict(extra="forbid")
    personas: Union[list[str], Literal["auto"]] = "auto"

    def persona_ids(self) -> list[str] | None:
        return None if self.personas == "auto" else list(self.personas)


class SwarmCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Shared Holo rate limit — the whole swarm shares this. Free tier is ~5 RPM.
    rpm: int = 5
    # Cap the swarm so a run stays inside the RPM budget in reasonable wall-clock.
    max_personas: int = 6


class OutputCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dir: str = ".sim"


class SafetyCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # SSRF guard. Off by default: refuse private/loopback targets unless opted in
    # (e.g. testing against localhost staging) or running --fixture.
    allow_private: bool = False
    # When non-empty, ONLY these hosts (exact or suffix match) are allowed.
    allowlist: list[str] = Field(default_factory=list)


class SimConfig(BaseModel):
    """Top-level `sim.yml`."""

    model_config = ConfigDict(extra="forbid")
    version: int = 1
    flows: list[Flow] = Field(default_factory=list)
    icp: IcpCfg = Field(default_factory=IcpCfg)
    swarm: SwarmCfg = Field(default_factory=SwarmCfg)
    output: OutputCfg = Field(default_factory=OutputCfg)
    safety: SafetyCfg = Field(default_factory=SafetyCfg)

    def flow(self, name: str | None = None) -> Flow:
        """Return the named flow, or the first flow when no name is given."""
        if not self.flows:
            raise ValueError("sim.yml declares no flows")
        if name is None:
            return self.flows[0]
        for f in self.flows:
            if f.name == name:
                return f
        raise ValueError(f"no flow named {name!r} in sim.yml")


def load_config(path: str | Path) -> SimConfig:
    """Parse and validate a `sim.yml`. Raises ValueError with a readable message."""
    p = Path(path)
    if not p.is_file():
        raise ValueError(f"config file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - passthrough of the parser msg
        raise ValueError(f"invalid YAML in {p}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{p} must be a YAML mapping")
    return SimConfig.model_validate(data)


DEFAULT_CONFIG_YAML: str = """\
# sim.yml — Simulation Labs behavioral test. Docs: https://github.com/SatyamDave/simulation-labs
version: 1

# Each flow is one behavioral test: a real goal on a real page.
flows:
  - name: signup
    url: https://staging.example.com/signup
    task: "Create an account with a work email and reach the dashboard"
    # "last-passing" blocks the merge if completion drops below the last green run.
    # Or set an absolute bar, e.g. 0.8 (80% of personas must finish).
    fail_under: last-passing

# Which behavioral segments to send. "auto" = the full bundled roster.
icp:
  personas: auto

swarm:
  rpm: 5           # shared Holo rate limit (free tier ~5 RPM)
  max_personas: 6  # keep the swarm inside the RPM budget

output:
  dir: .sim

safety:
  allow_private: false   # refuse localhost/private targets unless you opt in
  allowlist: []          # when set, ONLY these hosts are allowed
"""

__all__ = [
    "SimConfig", "Flow", "IcpCfg", "SwarmCfg", "OutputCfg", "SafetyCfg",
    "FailUnder", "load_config", "DEFAULT_CONFIG_YAML",
]
