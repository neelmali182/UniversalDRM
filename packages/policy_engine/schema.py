"""Policy schema for UniversalDRM (§10.1).

Every policy field is tagged with its enforcement class so SDK users
can distinguish server-enforced controls from browser-side deterrence
(§2.3, §10.1):

    enforced    — server refuses the request; holds against a hostile client
    best_effort — client-side deterrence; bypassable by a determined user
    traceability — does not prevent capture; identifies the leaker
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VisibleWatermarkConfig:
    type: str = "tiled"
    fields: list[str] = field(default_factory=lambda: ["user", "session", "timestamp"])
    opacity: float = 0.15


@dataclass
class ForensicWatermarkConfig:
    enabled: bool = True


@dataclass
class WatermarkPolicy:
    visible: VisibleWatermarkConfig = field(default_factory=VisibleWatermarkConfig)
    forensic: ForensicWatermarkConfig = field(default_factory=ForensicWatermarkConfig)


@dataclass
class RateLimits:
    pages_per_minute: int = 20
    max_pages_total: int = 200


@dataclass
class EnforcedPolicy:
    """Server-enforced access controls (§2.3 class: enforced)."""
    view: bool = True
    download: bool = False          # If False, NO plaintext download endpoint exists
    expires_in: int = 3600          # Seconds; 0 = no expiry
    one_time: bool = False
    max_sessions: int = 0           # 0 = unlimited
    max_devices: int = 0            # 0 = unlimited
    recipients: list[str] = field(default_factory=list)  # Email allowlist; [] = any authenticated
    rate_limits: RateLimits = field(default_factory=RateLimits)
    min_drm_security_level: str = "L1"  # Relevant for media engine only


@dataclass
class BestEffortPolicy:
    """Browser-side deterrence controls (§2.3 class: best_effort).

    These are deterrence measures only — they can be bypassed by a
    determined user with browser dev tools.  The API always labels them
    as best_effort so customers cannot mistake them for enforcement.
    """
    copy: bool = False
    cut: bool = False
    paste: bool = False
    selection: bool = False
    print: bool = False
    context_menu: bool = False
    blur_on_focus_loss: bool = True


@dataclass
class TraceabilityPolicy:
    """Traceability controls (§2.3 class: traceability).

    These do NOT prevent capture — they enable identification of
    the source of a leak after the fact.
    """
    watermark: WatermarkPolicy = field(default_factory=WatermarkPolicy)


@dataclass
class Policy:
    """Complete policy (§10.1).

    Serialised as JSON and stored in protection_policies.policy_json.
    """
    version: int = 1
    enforced: EnforcedPolicy = field(default_factory=EnforcedPolicy)
    best_effort: BestEffortPolicy = field(default_factory=BestEffortPolicy)
    traceability: TraceabilityPolicy = field(default_factory=TraceabilityPolicy)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Policy":
        """Deserialize from a plain dict (e.g., from JSON storage)."""
        enforced_data = data.get("enforced", {})
        rate_data = enforced_data.pop("rate_limits", {})
        enforced = EnforcedPolicy(
            **{k: v for k, v in enforced_data.items() if k in EnforcedPolicy.__dataclass_fields__},
            rate_limits=RateLimits(**rate_data) if rate_data else RateLimits(),
        )
        best_effort_data = data.get("best_effort", {})
        best_effort = BestEffortPolicy(
            **{k: v for k, v in best_effort_data.items() if k in BestEffortPolicy.__dataclass_fields__}
        )
        traceability_data = data.get("traceability", {})
        wm_data = traceability_data.get("watermark", {})
        visible_data = wm_data.get("visible", {})
        forensic_data = wm_data.get("forensic", {})
        traceability = TraceabilityPolicy(
            watermark=WatermarkPolicy(
                visible=VisibleWatermarkConfig(**visible_data) if visible_data else VisibleWatermarkConfig(),
                forensic=ForensicWatermarkConfig(**forensic_data) if forensic_data else ForensicWatermarkConfig(),
            )
        )
        return cls(
            version=data.get("version", 1),
            enforced=enforced,
            best_effort=best_effort,
            traceability=traceability,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for JSON storage."""
        import dataclasses
        return dataclasses.asdict(self)
