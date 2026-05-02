"""
StageRegistry — maps "type" string from policy JSON → stage class.

Java equivalent:
    @Component
    public class StageRegistry {
        private Map<String, Class<? extends BaseStage>> registry = new HashMap<>();
        public BaseStage create(String type, Map<String, Object> config, ...) { ... }
    }

In Spring this could be auto-populated by scanning @Stage("type-name") annotations.
"""
from __future__ import annotations
from typing import Any, Optional

from mkk_auth.exceptions import PolicyError
from mkk_auth.stages.base import BaseStage


class StageRegistry:
    """
    Holds the mapping from stage type strings to classes.
    Engine asks the registry to instantiate stages from policy.
    """

    def __init__(self):
        self._classes: dict[str, type[BaseStage]] = {}

    def register(self, stage_class: type[BaseStage]) -> None:
        if not stage_class.STAGE_TYPE:
            raise ValueError(
                f"{stage_class.__name__} must define STAGE_TYPE class attribute"
            )
        self._classes[stage_class.STAGE_TYPE] = stage_class

    def create(
        self,
        stage_type: str,
        config: dict[str, Any],
        providers: dict[str, Any],
    ) -> BaseStage:
        """
        Instantiate a stage by type name.

        `providers` is a dict like:
            {"lookup": ..., "sms": ..., "credentials": ..., ...}

        Each stage's constructor pulls what it needs by name.
        """
        cls = self._classes.get(stage_type)
        if cls is None:
            available = sorted(self._classes.keys())
            raise PolicyError(
                f"Unknown stage type {stage_type!r}. "
                f"Available: {available}"
            )
        return cls.from_config(config, providers)

    def types(self) -> list[str]:
        return sorted(self._classes.keys())


_default_registry: Optional[StageRegistry] = None


def get_default_registry() -> StageRegistry:
    """
    Returns the global default registry (lazy-initialized).
    Stages auto-register themselves with this on first import.
    """
    global _default_registry
    if _default_registry is None:
        _default_registry = StageRegistry()
    return _default_registry


def register(stage_class: type[BaseStage]) -> type[BaseStage]:
    """
    Decorator to auto-register a stage with the default registry.

    Usage:
        @register
        class MyStage(BaseStage):
            STAGE_TYPE = "my_stage"
            ...
    """
    get_default_registry().register(stage_class)
    return stage_class
