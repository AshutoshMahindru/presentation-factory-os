import json
from pathlib import Path
from jsonschema.validators import validator_for

SCHEMA_FILES = [
    "docs/06_SlideJobDefinition.schema.json",
    "docs/07_StandardContextPayload.schema.json",
    "docs/21_DesignTokens.schema.json",
    "docs/22_AudienceProfile.schema.json",
]

def main() -> None:
    for file_path in SCHEMA_FILES:
        path = Path(file_path)
        schema = json.loads(path.read_text())
        validator_cls = validator_for(schema)
        validator_cls.check_schema(schema)
        print(f"PASS JSON Schema: {file_path}")

if __name__ == "__main__":
    main()
