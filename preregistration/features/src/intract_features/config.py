"""Configuration loading.

Every registered constant, seed and key string lives in config/, never in code, so
that the Feature Specification can cite one place for each value. Each stage keeps
its constants in its own file, config/stages/<stage>.toml, which spares parallel
edits to one shared file; pipeline.toml holds what every stage shares.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path


def load(config_dir: Path) -> dict:
    """Merge pipeline.toml, languages.toml, stages/*.toml and the model and resource locks."""
    config_dir = Path(config_dir)
    cfg: dict = {}
    base = config_dir / "pipeline.toml"
    if base.exists():
        cfg.update(tomllib.loads(base.read_text(encoding="utf-8")))
    langs = config_dir / "languages.toml"
    if langs.exists():
        cfg["languages"] = tomllib.loads(langs.read_text(encoding="utf-8"))
    stages = {}
    for path in sorted((config_dir / "stages").glob("*.toml")):
        stages[path.stem] = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg["stages"] = stages
    for name in ("models", "resources"):
        lock = config_dir / f"{name}.lock.json"
        cfg[name] = json.loads(lock.read_text(encoding="utf-8")) if lock.exists() else {}
    return cfg


def language(cfg: dict, lang: str) -> dict:
    """The languages.toml table for a locale, for example cfg['languages']['en-us']."""
    try:
        return cfg["languages"][lang]
    except KeyError as e:
        raise KeyError(f"language {lang!r} is not configured in languages.toml") from e
