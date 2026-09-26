import hashlib
import json

import numpy as np
import pytest
from pydantic import ValidationError

from risk_platform.config import Settings
from risk_platform.contracts import Domain, ScoreRequest
from risk_platform.onnx_adapter import (
    OnnxManifest,
    OnnxRuntimeAdapter,
    load_onnx_adapters,
)


class TensorMetadata:
    def __init__(self, name, shape):
        self.name = name
        self.shape = shape
        self.type = "tensor(float)"


class FakeSession:
    def __init__(self, output=None, providers=None, input_shape=None):
        self.output = np.asarray([[0.2, 0.8]], dtype=np.float32) if output is None else output
        self.providers = providers or ["CPUExecutionProvider"]
        self.input_shape = input_shape or [None, 2]
        self.last_inputs = None

    def get_inputs(self):
        return [TensorMetadata("features", self.input_shape)]

    def get_outputs(self):
        return [TensorMetadata("probabilities", [None, 2])]

    def get_providers(self):
        return self.providers

    def run(self, output_names, inputs):
        assert output_names == ["probabilities"]
        self.last_inputs = inputs
        return [self.output]


def write_manifest(tmp_path, model_bytes=b"synthetic-onnx-fixture", **changes):
    model = tmp_path / "model.onnx"
    if model_bytes is not None:
        model.write_bytes(model_bytes)
    data = {
        "domain": "ieee_cis",
        "model_version": "fixture-v1",
        "input_schema_version": "features-v1",
        "model_path": "model.onnx",
        "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "feature_names": ["amount", "velocity"],
        "input_name": "features",
        "output_name": "probabilities",
        "output_kind": "class_probabilities",
        "positive_class": "fraud",
        "positive_class_index": 1,
        "providers": ["CPUExecutionProvider"],
        **changes,
    }
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    return manifest


async def test_adapter_verifies_contract_and_preserves_feature_order(tmp_path):
    session = FakeSession()
    adapter = OnnxRuntimeAdapter(write_manifest(tmp_path), lambda path, providers: session)
    availability = adapter.availability()
    assert availability.available is True
    assert availability.backend == "CPUExecutionProvider"
    result = await adapter.score(
        ScoreRequest(
            input_schema_version="features-v1",
            features={"velocity": 4, "amount": 10.5},
        )
    )
    assert result.domain == Domain.TRANSACTION
    assert result.probability == pytest.approx(0.8)
    tensor = session.last_inputs["features"]
    assert tensor.dtype == np.float32
    assert tensor.tolist() == [[10.5, 4.0]]


@pytest.mark.parametrize(
    "features",
    [
        {"amount": 1},
        {"amount": 1, "velocity": 2, "extra": 3},
        {"amount": "1", "velocity": 2},
        {"amount": True, "velocity": 2},
    ],
)
async def test_adapter_rejects_feature_drift_and_non_numeric_values(tmp_path, features):
    adapter = OnnxRuntimeAdapter(write_manifest(tmp_path), lambda path, providers: FakeSession())
    with pytest.raises(ValueError):
        await adapter.score(ScoreRequest(input_schema_version="features-v1", features=features))


async def test_adapter_rejects_schema_and_invalid_output(tmp_path):
    adapter = OnnxRuntimeAdapter(
        write_manifest(tmp_path),
        lambda path, providers: FakeSession(output=np.asarray([[0.2, np.nan]])),
    )
    with pytest.raises(ValueError, match="schema"):
        await adapter.score(
            ScoreRequest(
                input_schema_version="wrong",
                features={"amount": 1, "velocity": 2},
            )
        )
    with pytest.raises(ValidationError):
        await adapter.score(
            ScoreRequest(
                input_schema_version="features-v1",
                features={"amount": 1, "velocity": 2},
            )
        )


@pytest.mark.parametrize(
    "output",
    [
        np.asarray([], dtype=np.float32),
        np.asarray([[0.2, 0.8], [0.3, 0.7]], dtype=np.float32),
        np.asarray([[[0.2, 0.8]]], dtype=np.float32),
    ],
)
async def test_adapter_rejects_ambiguous_output_shapes(tmp_path, output):
    adapter = OnnxRuntimeAdapter(
        write_manifest(tmp_path),
        lambda path, providers: FakeSession(output=output),
    )
    with pytest.raises(ValueError, match="output|batch"):
        await adapter.score(
            ScoreRequest(
                input_schema_version="features-v1",
                features={"amount": 1, "velocity": 2},
            )
        )


def test_adapter_rejects_checksum_provider_and_tensor_shape_mismatches(tmp_path):
    with pytest.raises(ValueError, match="checksum"):
        OnnxRuntimeAdapter(
            write_manifest(tmp_path, sha256="0" * 64),
            lambda path, providers: FakeSession(),
        )
    with pytest.raises(ValueError, match="provider"):
        OnnxRuntimeAdapter(
            write_manifest(tmp_path),
            lambda path, providers: FakeSession(providers=["CUDAExecutionProvider"]),
        )
    with pytest.raises(ValueError, match="feature count"):
        OnnxRuntimeAdapter(
            write_manifest(tmp_path),
            lambda path, providers: FakeSession(input_shape=[None, 3]),
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"providers": ["InventedExecutionProvider"]},
        {"providers": ["CPUExecutionProvider", "CPUExecutionProvider"]},
        {"feature_names": ["amount", "amount"]},
        {"output_kind": "probability", "positive_class_index": 1},
    ],
)
def test_manifest_rejects_ambiguous_or_unsupported_contracts(changes):
    base = {
        "domain": "ieee_cis",
        "model_version": "v1",
        "input_schema_version": "v1",
        "model_path": "model.onnx",
        "sha256": "0" * 64,
        "feature_names": ["amount", "velocity"],
        "input_name": "features",
        "output_name": "probabilities",
        "output_kind": "class_probabilities",
        "positive_class": "fraud",
        "positive_class_index": 1,
        "providers": ["CPUExecutionProvider"],
    }
    with pytest.raises(ValidationError):
        OnnxManifest.model_validate({**base, **changes})


def test_invalid_configured_adapter_fails_closed_without_path_disclosure(tmp_path):
    path = write_manifest(tmp_path, sha256="0" * 64)
    adapters = load_onnx_adapters({"ieee_cis": path})
    availability = adapters[Domain.TRANSACTION].availability()
    assert availability.available is False
    assert availability.reason == "Configured ONNX model failed validation"
    assert str(tmp_path) not in availability.reason


def test_settings_reject_unknown_manifest_domain(tmp_path):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, onnx_manifests={"invented": tmp_path / "manifest.json"})


def write_real_sigmoid_model(tmp_path):
    import onnx
    from onnx import TensorProto, helper

    input_tensor = helper.make_tensor_value_info("features", TensorProto.FLOAT, [None, 2])
    output_tensor = helper.make_tensor_value_info("probabilities", TensorProto.FLOAT, [None, 2])
    graph = helper.make_graph(
        [helper.make_node("Sigmoid", ["features"], ["probabilities"])],
        "runtime-fixture",
        [input_tensor],
        [output_tensor],
    )
    model = helper.make_model(
        graph,
        producer_name="risk-platform-test",
        opset_imports=[helper.make_opsetid("", 13)],
    )
    model.ir_version = 10
    onnx.checker.check_model(model)
    model_path = tmp_path / "model.onnx"
    onnx.save(model, model_path)
    return model_path


async def test_real_onnxruntime_cpu_inference(tmp_path):
    pytest.importorskip("onnxruntime")
    model_path = write_real_sigmoid_model(tmp_path)
    manifest_path = write_manifest(
        tmp_path,
        model_bytes=None,
        sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
    )
    adapter = OnnxRuntimeAdapter(manifest_path)
    result = await adapter.score(
        ScoreRequest(
            input_schema_version="features-v1",
            features={"amount": 0, "velocity": 1},
        )
    )
    assert result.probability == pytest.approx(0.7310586, rel=1e-6)


async def test_real_openvino_execution_provider_inference(tmp_path):
    runtime = pytest.importorskip("onnxruntime")
    if "OpenVINOExecutionProvider" not in runtime.get_available_providers():
        pytest.skip("OpenVINO execution provider is not installed")
    model_path = write_real_sigmoid_model(tmp_path)
    manifest_path = write_manifest(
        tmp_path,
        model_bytes=None,
        sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
        providers=["OpenVINOExecutionProvider", "CPUExecutionProvider"],
    )
    adapter = OnnxRuntimeAdapter(manifest_path)
    assert adapter.availability().backend == "OpenVINOExecutionProvider"
    result = await adapter.score(
        ScoreRequest(
            input_schema_version="features-v1",
            features={"amount": 0, "velocity": 1},
        )
    )
    assert result.probability == pytest.approx(0.7310586, rel=1e-6)
