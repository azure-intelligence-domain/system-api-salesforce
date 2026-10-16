"""The contract is the validator: request bodies are checked against openapi.yaml itself."""

from pathlib import Path

import yaml
from jsonschema import Draft7Validator

SPEC = yaml.safe_load(Path(__file__).with_name("openapi.yaml").read_text())
CORRELATION_ID = SPEC["components"]["parameters"]["correlationId"]["schema"]


def _validator(schema: dict) -> Draft7Validator:
    # $refs point at #/components/..., so the schema travels with the spec's components.
    return Draft7Validator({**schema, "components": SPEC["components"]}, format_checker=Draft7Validator.FORMAT_CHECKER)


NEW_ORDER = _validator(SPEC["components"]["schemas"]["newOrder"])
CORRELATION = _validator(CORRELATION_ID)


def violations(validator: Draft7Validator, document) -> list[str]:
    """Human-readable contract violations, empty when the document is valid."""
    return [
        f"{'/'.join(map(str, error.absolute_path)) or 'body'}: {error.message}"
        for error in sorted(validator.iter_errors(document), key=lambda e: list(map(str, e.absolute_path)))
    ]
