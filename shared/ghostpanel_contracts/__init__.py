"""Ghostpanel frozen shared contracts. Import from here, e.g.::

    from ghostpanel_contracts import PersonaConfig, Action, RunEvent, HoloClient

DO NOT edit contracts.py — see the warning at the top of that module.
"""

from ghostpanel_contracts.contracts import (  # noqa: F401
    CONTRACT_VERSION,
    # enums
    PerturbationKind,
    CVDType,
    ActionType,
    ScrollDirection,
    PersonaOutcome,
    EventType,
    # data models
    Viewport,
    PersonaConfig,
    Observation,
    Action,
    StepRecord,
    PersonaResult,
    HeatPoint,
    SurvivalPoint,
    RunReport,
    # events
    RunStarted,
    PersonaStarted,
    StepEvent,
    PersonaFinished,
    RunFinished,
    RunEvent,
    # protocols
    HoloClient,
    PersonaAgent,
    EventSink,
    SessionRunner,
    VoiceEngine,
    ReportBuilder,
)

__all__ = [
    "CONTRACT_VERSION",
    "PerturbationKind",
    "CVDType",
    "ActionType",
    "ScrollDirection",
    "PersonaOutcome",
    "EventType",
    "Viewport",
    "PersonaConfig",
    "Observation",
    "Action",
    "StepRecord",
    "PersonaResult",
    "HeatPoint",
    "SurvivalPoint",
    "RunReport",
    "RunStarted",
    "PersonaStarted",
    "StepEvent",
    "PersonaFinished",
    "RunFinished",
    "RunEvent",
    "HoloClient",
    "PersonaAgent",
    "EventSink",
    "SessionRunner",
    "VoiceEngine",
    "ReportBuilder",
]
