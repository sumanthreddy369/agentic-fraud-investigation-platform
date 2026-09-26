# ONNX Runtime and OpenVINO inference

The platform supports ONNX as an optional deployment format. This does not convert, replace, or retrain the existing IEEE-CIS, Home Credit, or Elliptic models.

Use ONNX Runtime CPU as the portable baseline. Use its CUDA provider when NVIDIA deployment is required. Use the OpenVINO provider for a measured Intel CPU, GPU, or NPU deployment. The configured primary provider must actually activate; silent provider fallback is rejected.

## Why both

- **ONNX** is the portable graph and weight format.
- **ONNX Runtime** loads the graph and selects a hardware execution provider.
- **OpenVINO** is an optional Intel-optimized provider. It is useful only after parity and latency benchmarks on the target hardware.

For this project, portability and verified parity matter more than an assumed speedup. Tree models, preprocessing operators, and graph workflows may not all export cleanly. The Elliptic graph pipeline should export only its final fixed-shape classifier; graph construction and feature engineering remain outside ONNX.

## Installation

The CPU and OpenVINO extras are intentionally mutually exclusive because their Python distributions provide the same `onnxruntime` module.

```powershell
# Portable CPU runtime
uv sync --extra onnx-cpu --python 3.11

# Intel OpenVINO execution provider
uv sync --extra onnx-openvino --python 3.11
```

The OpenVINO extra pins a documented compatible pair: ONNX Runtime OpenVINO 1.24.1 and OpenVINO 2025.4.1. On Windows, the companion OpenVINO wheel is installed and imported to register its native DLL directories. On Linux, the ONNX Runtime OpenVINO wheel supplies its matching provider libraries; preloading a second OpenVINO runtime can cause an ABI conflict. Upgrade the pair together only after checking the provider compatibility table and rerunning parity and hardware tests.

CUDA deployments should use a separately locked environment containing the official GPU runtime compatible with the deployment CUDA/cuDNN versions. Do not install multiple ONNX Runtime distributions into one environment.

## Manifest contract

Model files remain outside Git. A checked and approved manifest points to one `.onnx` artifact and pins its SHA-256 digest, feature order, schema version, output interpretation, and execution providers.

Load manifests and model artifacts only from a trusted release process. A matching checksum prevents post-approval substitution; it does not prove that a model is safe, accurate, or authorized for production use.

```json
{
  "domain": "ieee_cis",
  "model_version": "fraud-xgb-2026-09",
  "input_schema_version": "ieee-cis-features-v1",
  "model_path": "fraud-xgb.onnx",
  "sha256": "64-lowercase-hex-characters",
  "feature_names": ["feature_a", "feature_b"],
  "input_name": "features",
  "output_name": "probabilities",
  "output_kind": "class_probabilities",
  "positive_class": "fraud",
  "positive_class_index": 1,
  "providers": ["CPUExecutionProvider"]
}
```

Configure manifests by domain:

```powershell
$env:RISK_ONNX_MANIFESTS='{"ieee_cis":"C:/secure-models/ieee/manifest.json"}'
uv run risk-platform
```

Startup behavior is fail closed. A missing runtime, invalid JSON, domain mismatch, unsupported provider, wrong tensor name or feature count, missing artifact, or checksum mismatch leaves that model unavailable. API responses do not reveal private artifact paths or validation internals.

## Required conversion and acceptance workflow

1. Recover the authoritative source model, preprocessing pipeline, feature order, dependency versions, positive-class mapping, and trusted test split.
2. Export the complete supported preprocessing-plus-model pipeline when possible. If preprocessing cannot be represented in ONNX, version and test the external preprocessing adapter separately.
3. Pin the converter and target opset. Scikit-learn models normally use `skl2onnx`; LightGBM/XGBoost commonly use `onnxmltools`. Confirm that every operator is supported by the selected runtime/provider.
   For classifiers, export a tensor probability output (for example, disable `ZipMap` when the converter supports that option) so the manifest can validate one deterministic class index.
4. Validate the ONNX model with the ONNX checker before deployment.
5. Compare source and ONNX outputs on golden fixtures and a representative held-out set. Define tolerances before looking at results.
6. Re-run business metrics, including ROC-AUC/PR-AUC, threshold precision/recall, calibration, and the exact positive-class semantics.
7. Benchmark warm-up, p50/p95/p99 latency, throughput, memory, cold-start time, and concurrency on the actual target hardware.
8. Record artifact hash, converter/runtime versions, opset, provider, hardware, parity results, metrics, and approval. Roll out behind the existing scoring kill switch.

OpenVINO should be selected only if it passes the same parity suite and materially improves the deployment objective. Quantization or precision changes require a separate approval and accuracy/calibration evaluation.

## Current status

The adapter, manifest validation, provider activation check, checksum verification, strict feature ordering, asynchronous blocking-runtime boundary, and output contract validation are implemented. No real model is configured because the authoritative artifacts and preprocessing contracts have not been supplied. Consequently, the public API continues to report all three original models as unavailable by default.

Official references:

- [ONNX Runtime Python API](https://onnxruntime.ai/docs/api/python/api_summary)
- [ONNX Runtime execution providers](https://onnxruntime.ai/docs/execution-providers/)
- [OpenVINO execution provider](https://onnxruntime.ai/docs/api/python/ReadMeOV.html)
- [scikit-learn ONNX conversion](https://onnx.ai/sklearn-onnx/)
- [OpenVINO ONNX conversion](https://docs.openvino.ai/nightly/openvino-workflow/model-preparation/convert-model-onnx.html)
