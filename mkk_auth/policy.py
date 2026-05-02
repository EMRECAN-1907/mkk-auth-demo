"""
Policy — represents a parsed JSON policy file.

Java equivalent:
    @Component
    public class PolicyLoader {
        public Policy fromFile(String path) { ... }
        public Policy fromJson(String json) { ... }
    }

    public record Policy(
        String policyName, String displayName, String appLabel,
        int sessionMinutes, List<Step> steps
    ) { ... }

    public record Step(
        int stepNumber, boolean parallel,
        TimingConfig timing, List<StageConfig> items
    ) { ... }
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mkk_auth.exceptions import PolicyError


@dataclass
class StageConfig:
    """A single stage's configuration as loaded from JSON.
    
    sub_steps: When this stage is the chosen alternative (in any-semantics
    step), additional sub-steps run inline after this stage succeeds.
    Empty list = nothing extra (e.g. e-Devlet route is single-step).
    Non-empty = TCKN-route style: TCKN → SMS → Email all happen
    only if the user chose this branch.
    """
    type: str
    config: dict[str, Any] = field(default_factory=dict)
    sub_steps: list["Step"] = field(default_factory=list)


@dataclass
class TimingConfig:
    """Per-step timing configuration."""
    mode: str = "perStage"               # "perStage" or "shared"
    shared_timeout: int | None = None    # only meaningful if mode == "shared"


@dataclass
class Step:
    """One step (row) in the flow. May contain 1+ parallel stages.
    
    semantics:
      - "all": every stage in this step must succeed (default — paralel/ardışık)
      - "any": user picks ONE stage; first success completes the step
               (e-Nabız tarzı: TCKN+Şifre VEYA e-Devlet VEYA e-İmza)
    """
    step_number: int
    parallel: bool
    timing: TimingConfig
    items: list[StageConfig]
    semantics: str = "all"  # "all" | "any"

    def is_parallel(self) -> bool:
        return self.parallel and len(self.items) > 1

    def is_alternative(self) -> bool:
        return self.semantics == "any" and len(self.items) > 1


@dataclass
class Policy:
    """A complete parsed policy."""
    policy_name: str
    display_name: str
    app_label: str
    session_minutes: int
    steps: list[Step]
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    # ----- Constructors -----

    @classmethod
    def from_file(cls, path: str | Path) -> "Policy":
        path = Path(path)
        if not path.exists():
            raise PolicyError(f"Policy file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())

    @classmethod
    def from_json(cls, json_text: str) -> "Policy":
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError as e:
            raise PolicyError(f"Invalid JSON: {e}")
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict) -> "Policy":
        try:
            policy_name = data["policyName"]
            stages_raw = data["stages"]
        except KeyError as e:
            raise PolicyError(f"Missing required field in policy: {e}")

        def _parse_step(step_data: dict, step_number: int) -> Step:
            items_raw = step_data.get("items", [])
            items = []
            for item in items_raw:
                # Recurse: if this item has subSteps, parse them too
                sub_steps_raw = item.get("subSteps") or []
                sub_steps = [_parse_step(s, idx + 1) for idx, s in enumerate(sub_steps_raw)]
                items.append(StageConfig(
                    type=item["type"],
                    config=dict(item.get("config") or {}),
                    sub_steps=sub_steps,
                ))
            timing_raw = step_data.get("timing") or {}
            timing = TimingConfig(
                mode=timing_raw.get("mode", "perStage"),
                shared_timeout=timing_raw.get("sharedTimeout"),
            )
            return Step(
                step_number=step_number,
                parallel=step_data.get("parallel", len(items) > 1),
                timing=timing,
                items=items,
                semantics=step_data.get("semantics", "all"),
            )

        steps = []
        for step_data in stages_raw:
            try:
                steps.append(_parse_step(step_data, step_data["step"]))
            except KeyError as e:
                raise PolicyError(f"Invalid step structure: missing {e}")

        return cls(
            policy_name=policy_name,
            display_name=data.get("displayName", policy_name),
            app_label=data.get("appLabel", ""),
            session_minutes=data.get("sessionMinutes", 30),
            steps=steps,
            description=data.get("description", ""),
            metadata=data.get("metadata", {}),
        )

    # ----- Validation -----

    def validate(self) -> list[str]:
        """
        Returns list of warnings. Empty list = no issues.
        Strict errors raise during from_dict.
        """
        warnings = []
        if not self.steps:
            warnings.append("Policy has no steps")
        for step in self.steps:
            if not step.items:
                warnings.append(f"Step {step.step_number} has no stages")
            if step.timing.mode == "shared" and not step.timing.shared_timeout:
                warnings.append(
                    f"Step {step.step_number} uses shared timing but has no sharedTimeout"
                )
        return warnings
