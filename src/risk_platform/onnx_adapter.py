"""Checksum-pinned ONNX inference adapter with strict input/output contracts."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Annotated, Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from risk_platform.adapters import ModelAdapter
from risk_platform.contracts import Domain, ModelAvailability, ScoreRequest, ScoreResult

ALLOWED_PROVIDERS = frozenset(
    {"CPUExecutionProvider", "CUDAExecutionProvider", "OpenVINOExecutionProvider"}
)
FeatureName = Annotated[
    str,
    Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_.-]+$"),
]


class SessionLike(Protocol):
    def get_inputs(self) -> Sequence[Any]: ...

    def get_outputs(self) -> Sequence[Any]: ...

    def get_providers(self) -> Sequence[str]: ...

    def run(self, output_names: list[str], inputs: Mapping[str, Any]) -> list[Any]: ...


class OnnxManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    domain: Domain
    model_version: str = Field(min_length=1, max_length=128)
    input_schema_version: str = Field(min_length=1, max_length=128)
    model_path: str = Field(min_length=1, max_length=1024)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    feature_names: list[FeatureName] = Field(min_length=1, max_length=512)
    input_name: str = Field(min_length=1, max_length=128)
    output_name: str = Field(min_length=1, max_length=128)
    output_kind: Literal["probability", "class_probabilities"]
    positive_class: str = Field(min_length=1, max_length=128)
    positive_class_index: int = Field(default=1, ge=0, le=1000)
    providers: list[str] = Field(default_factory=lambda: ["CPUExecutionProvider"])

    @field_validator("feature_names")
    @classmethod
    def unique_features(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("Feature names must be unique")
        return value

    @field_validator("providers")
    @classmethod
    def supported_providers(cls, value: list[str]) -> list[str]:
        if not value or len(value) != len(set(value)):
            raise ValueError("Providers must be a nonempty ordered set")
        if not set(value) <= ALLOWED_PROVIDERS:
            raise ValueError("Unsupported execution provider")
        return value

    @model_validator(mode="after")
    def valid_output_index(self) -> OnnxManifest:
        if self.output_kind == "probability" and self.positive_class_index != 0:
            raise ValueError("Scalar probability output requires positive_class_index=0")
        return self


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def default_session_factory(model_path: Path, providers: list[str]) -> SessionLike:
    if "OpenVINOExecutionProvider" in providers:
        try:
            # On Windows, importing the wheel registers its native DLL directories.
            import openvino  # noqa: F401
        except ImportError as error:
            raise RuntimeError("OpenVINO runtime is required for its execution provider") from error
    try:
        import onnxruntime as ort
    except ImportError as error:
        raise RuntimeError(
            "Install either the onnx-cpu or onnx-openvino optional dependency"
        ) from error
    available = set(ort.get_available_providers())
    missing = set(providers) - available
    if missing:
        raise RuntimeError("Configured ONNX execution provider is unavailable")
    options = ort.SessionOptions()
    options.enable_profiling = False
    options.log_severity_level = 3
    return ort.InferenceSession(str(model_path), sess_options=options, providers=providers)


class OnnxRuntimeAdapter(ModelAdapter):
    def __init__(
        self,
        manifest_path: Path,
        session_factory: Callable[[Path, list[str]], SessionLike] = default_session_factory,
    ) -> None:
        self.manifest_path = manifest_path.resolve(strict=True)
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.manifest = OnnxManifest.model_validate(raw)
        candidate = Path(self.manifest.model_path)
        self.model_path = (
            candidate if candidate.is_absolute() else self.manifest_path.parent / candidate
        ).resolve(strict=True)
        if not self.model_path.is_file() or self.model_path.suffix.lower() != ".onnx":
            raise ValueError("Model artifact must be an ONNX file")
        if sha256_file(self.model_path) != self.manifest.sha256:
            raise ValueError("ONNX artifact checksum mismatch")
        self.session = session_factory(self.model_path, self.manifest.providers)
        self._validate_session_contract()

    def _validate_session_contract(self) -> None:
        inputs = {item.name: item for item in self.session.get_inputs()}
        outputs = {item.name: item for item in self.session.get_outputs()}
        if self.manifest.input_name not in inputs or self.manifest.output_name not in outputs:
            raise ValueError("ONNX manifest does not match model input/output names")
        input_type = getattr(inputs[self.manifest.input_name], "type", "tensor(float)")
        output_type = getattr(outputs[self.manifest.output_name], "type", "tensor(float)")
        if input_type != "tensor(float)" or output_type != "tensor(float)":
            raise ValueError("ONNX adapter requires float32 input and output tensors")
        actual = list(self.session.get_providers())
        if not actual or actual[0] != self.manifest.providers[0]:
            raise ValueError("Requested primary ONNX execution provider was not activated")
        shape = getattr(inputs[self.manifest.input_name], "shape", None)
        if shape and len(shape) == 2 and isinstance(shape[1], int):
            if shape[1] != len(self.manifest.feature_names):
                raise ValueError("ONNX feature count does not match input tensor shape")

    def availability(self) -> ModelAvailability:
        return ModelAvailability(
            domain=self.manifest.domain,
            available=True,
            reason="Checksum-verified ONNX artifact and runtime contract loaded",
            backend=self.manifest.providers[0],
            model_version=self.manifest.model_version,
        )

    async def score(self, request: ScoreRequest) -> ScoreResult:
        if request.input_schema_version != self.manifest.input_schema_version:
            raise ValueError("Input schema version mismatch")
        expected = set(self.manifest.feature_names)
        if set(request.features) != expected:
            raise ValueError("Features do not exactly match the ONNX manifest")
        values: list[float] = []
        for name in self.manifest.feature_names:
            value = request.features[name]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("ONNX tensor features must be numeric")
            values.append(float(value))
        try:
            import numpy as np
        except ImportError as error:
            raise RuntimeError("NumPy is required for ONNX inference") from error
        tensor = np.asarray([values], dtype=np.float32)
        output = await asyncio.to_thread(
            self.session.run,
            [self.manifest.output_name],
            {self.manifest.input_name: tensor},
        )
        if len(output) != 1:
            raise ValueError("ONNX runtime returned an unexpected output count")
        array = np.asarray(output[0])
        if array.ndim > 2 or array.size == 0:
            raise ValueError("ONNX runtime returned an invalid output shape")
        if array.ndim == 2 and array.shape[0] != 1:
            raise ValueError("ONNX runtime returned an invalid batch size")
        flattened = array.reshape(-1)
        if self.manifest.output_kind == "probability" and flattened.size != 1:
            raise ValueError("Scalar probability output must contain one value")
        index = (
            0 if self.manifest.output_kind == "probability" else self.manifest.positive_class_index
        )
        if index >= flattened.size:
            raise ValueError("Positive class index is outside the ONNX output")
        probability = float(flattened[index])
        return ScoreResult(
            domain=self.manifest.domain,
            model_version=self.manifest.model_version,
            input_schema_version=self.manifest.input_schema_version,
            positive_class=self.manifest.positive_class,
            probability=probability,
        )


class InvalidConfiguredAdapter:
    def __init__(self, domain: Domain):
        self.domain = domain

    def availability(self) -> ModelAvailability:
        return ModelAvailability(
            domain=self.domain,
            available=False,
            reason="Configured ONNX model failed validation",
            backend="onnxruntime",
        )

    async def score(self, request: ScoreRequest) -> ScoreResult:
        raise RuntimeError("Configured ONNX model failed validation")


def load_onnx_adapters(manifests: Mapping[str, Path]) -> dict[Domain, ModelAdapter]:
    configured: dict[Domain, ModelAdapter] = {}
    for raw_domain, path in manifests.items():
        domain = Domain(raw_domain)
        try:
            adapter = OnnxRuntimeAdapter(path)
            if adapter.manifest.domain != domain:
                raise ValueError("Manifest domain does not match configuration key")
            configured[domain] = adapter
        except Exception:
            # Fail closed and avoid exposing paths, hashes, runtime internals, or parser errors.
            configured[domain] = InvalidConfiguredAdapter(domain)
    return configured
