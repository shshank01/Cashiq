"""
CashIQ Machine Learning Architecture Package.
Implements the 11-component ML System Architecture:
1. Data Collector
2. Ground-Truth Collector
3. Labelizer
4. Data Preprocessor & Feature Transformer
5. ML Orchestrator
6. Model Builder
7. Evaluator
8. Model Registry
9. Monitoring & Drift Detector
10. Model Serving
11. Frontend Integration
"""

from app.ml.architecture.data_collector import DataCollector, data_collector
from app.ml.architecture.ground_truth import GroundTruthCollector, ground_truth_collector
from app.ml.architecture.labelizer import Labelizer, labelizer, LabelStatus
from app.ml.architecture.feature_transformer import FeatureTransformer, feature_transformer
from app.ml.architecture.model_builder import ModelBuilder, model_builder
from app.ml.architecture.evaluator import MLEvaluator, evaluator
from app.ml.architecture.registry import ModelRegistry, model_registry
from app.ml.architecture.monitoring import MLMonitor, ml_monitor
from app.ml.architecture.orchestrator import MLOrchestrator, ml_orchestrator
from app.ml.architecture.serving import ModelServing, model_serving

__all__ = [
    "DataCollector", "data_collector",
    "GroundTruthCollector", "ground_truth_collector",
    "Labelizer", "labelizer", "LabelStatus",
    "FeatureTransformer", "feature_transformer",
    "ModelBuilder", "model_builder",
    "MLEvaluator", "evaluator",
    "ModelRegistry", "model_registry",
    "MLMonitor", "ml_monitor",
    "MLOrchestrator", "ml_orchestrator",
    "ModelServing", "model_serving",
]
