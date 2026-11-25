import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

WEIGHTS_FILE = Path(__file__).with_name("weights.toml")


class FusionConfig(BaseModel):
    method: Literal["rrf", "weighted"] = "rrf"
    rrf_k: int = Field(60, ge=1)
    semantic_weight: float = Field(1.0, ge=0)
    keyword_weight: float = Field(1.0, ge=0)


class RerankConfig(BaseModel):
    relevance: float = Field(ge=0)
    skills: float = Field(ge=0)
    preferences: float = Field(ge=0)
    profile: float = Field(ge=0)
    urgency: float = Field(ge=0)
    urgency_window_days: int = Field(14, ge=1)
    similarity_floor: float = 0.5
    similarity_ceiling: float = 0.85

    @model_validator(mode="after")
    def _urgency_is_smallest(self) -> "RerankConfig":
        others = [w for w in (self.relevance, self.skills, self.preferences, self.profile) if w > 0]
        if self.urgency and any(self.urgency >= w for w in others):
            raise ValueError("urgency must stay below the other weights")
        return self


class SearchConfig(BaseModel):
    candidates: int = Field(50, ge=1, le=200)
    min_similarity: float = 0.0
    weak_similarity: float = 0.58
    fusion: FusionConfig
    rerank: RerankConfig

    def override(self, changes: dict[str, Any]) -> "SearchConfig":
        """Copy with dotted-key changes, for example {"fusion.rrf_k": 30}."""
        data = self.model_dump()
        for key, value in changes.items():
            target = data
            *parents, leaf = key.split(".")
            for parent in parents:
                target = target[parent]
            if leaf not in target:
                raise KeyError(key)
            target[leaf] = value
        return SearchConfig.model_validate(data)


@lru_cache
def get_search_config() -> SearchConfig:
    return SearchConfig.model_validate(tomllib.loads(WEIGHTS_FILE.read_text("utf-8")))
