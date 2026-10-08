from src.core.models import ValidationRecord
from src.core.validation import validation_metrics


def test_validation_ignores_unjudged_values():
    records = [ValidationRecord(comment_id="1", text_accepted=True), ValidationRecord(comment_id="2", text_accepted=False), ValidationRecord(comment_id="3")]
    metric = validation_metrics(records)["text_accepted"]
    assert metric == {"accepted": 1, "judged": 2, "rate": 0.5}

