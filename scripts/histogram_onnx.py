"""Narrow skl2onnx compatibility adapter: missing-direction flags are ONNX integers."""

from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import FloatTensorType
from skl2onnx.operator_converters.random_forest import convert_sklearn_random_forest_classifier
from sklearn.ensemble import HistGradientBoostingClassifier


class IntegerMissingFlags:
    def __init__(self, container):
        self.container = container

    def __getattr__(self, name):
        return getattr(self.container, name)

    def add_node(self, op_type, *args, **kwargs):
        if op_type == "TreeEnsembleClassifier" and "nodes_missing_value_tracks_true" in kwargs:
            kwargs["nodes_missing_value_tracks_true"] = [
                int(value) for value in kwargs["nodes_missing_value_tracks_true"]
            ]
        return self.container.add_node(op_type, *args, **kwargs)


def convert_histogram(scope, operator, container):
    convert_sklearn_random_forest_classifier(scope, operator, IntegerMissingFlags(container))


def export_histogram(model, feature_count):
    return convert_sklearn(
        model,
        initial_types=[("features", FloatTensorType([None, feature_count]))],
        target_opset=17,
        options={id(model): {"zipmap": False}},
        custom_conversion_functions={HistGradientBoostingClassifier: convert_histogram},
    )
