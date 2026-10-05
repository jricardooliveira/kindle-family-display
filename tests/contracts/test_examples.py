import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema import ValidationError as SchemaValidationError
from pydantic import ValidationError

from app.contracts.models import (
    DisplayContext,
    DisplayDecision,
    Event,
    NewsItem,
    Status,
    WeatherSnapshot,
)

ROOT = Path(__file__).parents[2]
SCHEMAS = ROOT / "contracts" / "schemas"
EXAMPLES = ROOT / "contracts" / "examples"


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("display-context", DisplayContext),
        ("display-decision", DisplayDecision),
        ("event", Event),
        ("news", NewsItem),
        ("status", Status),
        ("weather", WeatherSnapshot),
    ],
)
def test_example_payload_matches_json_schema_and_model(name, model):
    schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text())
    payload = json.loads((EXAMPLES / f"{name}.json").read_text())

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)
    model.model_validate(payload)


def test_schemas_reject_invalid_severity_and_layout():
    context_schema = json.loads((SCHEMAS / "display-context.schema.json").read_text())
    decision_schema = json.loads((SCHEMAS / "display-decision.schema.json").read_text())
    context = json.loads((EXAMPLES / "display-context.json").read_text())
    context["items"][0]["severity"] = "emergency"
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(context_schema).validate(context)
    with pytest.raises(ValidationError):
        DisplayContext.model_validate(context)

    decision = json.loads((EXAMPLES / "display-decision.json").read_text())
    decision["layout"] = "free-form-html"
    with pytest.raises(SchemaValidationError):
        Draft202012Validator(decision_schema).validate(decision)
    with pytest.raises(ValidationError):
        DisplayDecision.model_validate(decision)
