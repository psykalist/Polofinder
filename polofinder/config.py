import os

import yaml

DEFAULT = os.path.join(os.path.dirname(__file__), "..", "config.yaml")


def load(path: str = None) -> dict:
    with open(path or os.getenv("POLOFINDER_CONFIG", DEFAULT)) as f:
        cfg = yaml.safe_load(f)

    # The self-hosted workflow sets POLOFINDER_LOCAL_MODE=1 so it can enable
    # local scraping without committing a different config.
    if os.getenv("POLOFINDER_LOCAL_MODE") in ("1", "true", "yes"):
        cfg.setdefault("sources", {})["local_mode"] = True

    profile = os.getenv("POLOFINDER_CHROME_PROFILE")
    if profile:
        cfg.setdefault("sources", {})["chrome_profile_dir"] = profile

    return cfg
