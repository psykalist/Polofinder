import os
import yaml

DEFAULT = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def load(path: str = None) -> dict:
    with open(path or os.getenv("POLOFINDER_CONFIG", DEFAULT)) as f:
        return yaml.safe_load(f)
