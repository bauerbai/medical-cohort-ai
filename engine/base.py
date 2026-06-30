from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, ClassVar, Generic, TypeVar

import pandas as pd
from pydantic import BaseModel, Field


class AnalysisValidationError(ValueError):
    """Raised when an analysis receives invalid or insufficient data."""


class AnalysisExecutionError(RuntimeError):
    """Raised when an analysis fails during statistical execution."""


class AnalysisSpec(BaseModel):
    analysis_id: str = Field(..., description="Registry key, e.g. survival.cox")
    title: str
    description: str
    required_columns: list[str] = Field(default_factory=list)
    optional_columns: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    bias_checks: list[str] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    analysis_id: str
    title: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    n_input: int
    n_used: int
    parameters: dict[str, Any] = Field(default_factory=dict)
    estimates: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    plots: dict[str, Any] = Field(default_factory=dict)
    tables: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    interpretation: str | None = None


AnalysisT = TypeVar("AnalysisT", bound="BaseAnalysis")


class AnalysisRegistry:
    _registry: ClassVar[dict[str, type[BaseAnalysis]]] = {}

    @classmethod
    def register(cls, analysis_id: str, analysis_cls: type[AnalysisT]) -> type[AnalysisT]:
        if analysis_id in cls._registry:
            raise KeyError(f"Analysis already registered: {analysis_id}")
        cls._registry[analysis_id] = analysis_cls
        return analysis_cls

    @classmethod
    def get(cls, analysis_id: str) -> type[BaseAnalysis]:
        try:
            return cls._registry[analysis_id]
        except KeyError as exc:
            raise KeyError(f"Unknown analysis: {analysis_id}") from exc

    @classmethod
    def create(cls, analysis_id: str, **kwargs: Any) -> BaseAnalysis:
        return cls.get(analysis_id)(**kwargs)

    @classmethod
    def list_specs(cls) -> list[AnalysisSpec]:
        return [analysis_cls.spec() for analysis_cls in cls._registry.values()]


def register_analysis(analysis_id: str):
    def decorator(analysis_cls: type[AnalysisT]) -> type[AnalysisT]:
        return AnalysisRegistry.register(analysis_id, analysis_cls)

    return decorator


@dataclass(slots=True)
class BaseAnalysis(ABC, Generic[AnalysisT]):
    data: pd.DataFrame
    parameters: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    analysis_id: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str]
    required_columns: ClassVar[list[str]] = []
    optional_columns: ClassVar[list[str]] = []
    assumptions: ClassVar[list[str]] = []
    bias_checks: ClassVar[list[str]] = []

    @classmethod
    def spec(cls) -> AnalysisSpec:
        return AnalysisSpec(
            analysis_id=cls.analysis_id,
            title=cls.title,
            description=cls.description,
            required_columns=cls.required_columns,
            optional_columns=cls.optional_columns,
            assumptions=cls.assumptions,
            bias_checks=cls.bias_checks,
        )

    def validate_data(self) -> None:
        missing = [col for col in self.required_columns if col not in self.data.columns]
        if missing:
            raise AnalysisValidationError(f"Missing required columns: {missing}")
        if self.data.empty:
            raise AnalysisValidationError("Input data is empty")

    async def execute(self) -> AnalysisResult:
        self.validate_data()
        try:
            return await asyncio.to_thread(self._execute_sync)
        except AnalysisValidationError:
            raise
        except Exception as exc:
            raise AnalysisExecutionError(f"{self.analysis_id} failed: {exc}") from exc

    @abstractmethod
    def _execute_sync(self) -> AnalysisResult:
        raise NotImplementedError

    @abstractmethod
    def generate_report(self, result: AnalysisResult) -> dict[str, Any]:
        raise NotImplementedError

    def _base_result(self, n_used: int) -> AnalysisResult:
        return AnalysisResult(
            analysis_id=self.analysis_id,
            title=self.title,
            n_input=len(self.data),
            n_used=n_used,
            parameters=self.parameters,
            warnings=list(self.warnings),
        )
