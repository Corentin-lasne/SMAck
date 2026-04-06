"""Factory for selecting an agent policy by color and strategy profile."""

from __future__ import annotations

from config import DEFAULT_MODEL_PARAMS

from .green import GreenNoCommunicationPolicy, GreenWidespreadCommunicationPolicy
from .red import RedNoCommunicationPolicy, RedWidespreadCommunicationPolicy
from .yellow import YellowNoCommunicationPolicy, YellowWidespreadCommunicationPolicy

POLICY_REGISTRY = {
    "green": {
        "no_communication": GreenNoCommunicationPolicy,
        "widespread": GreenWidespreadCommunicationPolicy,
    },
    "yellow": {
        "no_communication": YellowNoCommunicationPolicy,
        "widespread": YellowWidespreadCommunicationPolicy,
    },
    "red": {
        "no_communication": RedNoCommunicationPolicy,
        "widespread": RedWidespreadCommunicationPolicy,
    },
}

def build_policy(color: str, policy_profile: str | None = None):
    if policy_profile is None:
        policy_profile = DEFAULT_MODEL_PARAMS[f"policy_profile_{color}"]

    try:
        policy_cls = POLICY_REGISTRY[color][policy_profile]
    except KeyError as exc:
        available_colors = ", ".join(sorted(POLICY_REGISTRY))
        available_profiles = ", ".join(sorted(POLICY_REGISTRY.get(color, {})))
        raise ValueError(
            f"Unknown policy selection: color={color!r}, profile={policy_profile!r}. "
            f"Available colors: {available_colors}. Available profiles for {color!r}: {available_profiles or 'none'}."
        ) from exc

    return policy_cls()