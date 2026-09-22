"""Branch G (P1). Trigger protocol, detectors, matched schedules, value-of-computation gate.

The gate itself is deferred (module brief, agreed cut line); everything it will plug into — the
protocol, the wrappers, the trace, the feature-legality machinery — is here and tested.
"""

from collie.trigger.calibration import FROZEN, TriggerCalibration
from collie.trigger.detectors import (
    AlertOnly,
    AlertOrDetector,
    Cusum,
    PageHinkley,
    PeriodicEveryK,
    RandomMatched,
)
from collie.trigger.features import (
    FEATURE_DENYLIST,
    FEATURE_DENYLIST_SUBSTRINGS,
    FeatureLegalityError,
    OnlineFeatures,
    assert_features_legal,
)
from collie.trigger.protocol import (
    MaxProposalsWrapper,
    RefractoryWrapper,
    TraceableTrigger,
    TraceEntry,
    TriggerTrace,
)

__all__ = [
    "FEATURE_DENYLIST",
    "FEATURE_DENYLIST_SUBSTRINGS",
    "FROZEN",
    "AlertOnly",
    "AlertOrDetector",
    "Cusum",
    "FeatureLegalityError",
    "MaxProposalsWrapper",
    "OnlineFeatures",
    "PageHinkley",
    "PeriodicEveryK",
    "RandomMatched",
    "RefractoryWrapper",
    "TraceEntry",
    "TraceableTrigger",
    "TriggerCalibration",
    "TriggerTrace",
    "assert_features_legal",
]
