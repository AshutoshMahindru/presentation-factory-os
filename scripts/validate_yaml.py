from pathlib import Path
import yaml

def main() -> None:
    yaml_files = sorted(Path("docs").glob("*.yaml"))

    if not yaml_files:
        raise SystemExit("No YAML files found under docs/")

    for path in yaml_files:
        yaml.safe_load(path.read_text())
        print(f"PASS YAML: {path}")

if __name__ == "__main__":
    main()
