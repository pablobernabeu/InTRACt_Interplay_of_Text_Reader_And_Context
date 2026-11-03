"""Command line and stage runner.

    python -m intract_features list-stages
    python -m intract_features run <stage> --config config --work WORK --lang en-us [--input PATH]
                                   [--shard I --nshards N] [--limit K]

Each run writes a timing record beside its outputs (<work>/<lang>/_timing/), because
measuring what every stage costs on ARC is the point of the dry run on the stand-in.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import pkgutil
import platform
import sys
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from intract_features import __version__, records
from intract_features import config as config_mod


@dataclass(frozen=True)
class Stage:
    """What a stage reads, writes and needs.

    `env` names the pinned environment in envs/ that runs it, since CorPipe and
    MetricX pin library versions that cannot share one environment with the rest.
    """

    name: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    device: str = "cpu"
    env: str = "core"
    description: str = ""


@dataclass
class StageContext:
    """One run of a stage: its configuration, language, work folder and shard.

    `extra` carries what the command line never sets: test fakes (`sat_backend`, `scorers`, `encoder`), local model
    folders (`stanza_model_dir`) and, for the catalogue lock, a test's `config_dir` (DESIGN.md, Configuration).
    """

    stage: Stage
    config: dict
    lang: str
    work: Path
    shard: int = 0
    nshards: int = 1
    input: Path | None = None
    limit: int | None = None
    extra: dict = field(default_factory=dict)

    def stage_config(self) -> dict:
        """This stage's table of config/stages/<stage>.toml."""
        return self.config.get("stages", {}).get(self.stage.name, {})

    def path(self, artefact: str, ext: str = "jsonl.gz") -> Path:
        """The path of this shard's file of an artefact."""
        return records.artefact_path(self.work, self.lang, artefact, self.shard, self.nshards, ext)

    def read(self, artefact: str) -> Iterator[dict]:
        """The records of this shard's file of a JSON Lines artefact."""
        yield from records.read_jsonl(self.path(artefact))

    def write(self, artefact: str, recs: Iterable[dict]) -> int:
        """Write this shard's file of a JSON Lines artefact atomically; return the number of records."""
        return records.write_jsonl(self.path(artefact), recs)

    def documents(self) -> Iterator[records.Document]:
        """This shard's documents, the first `limit` of them when a limit is set."""
        for i, obj in enumerate(self.read("documents")):
            if self.limit is not None and i >= self.limit:
                return
            yield records.Document.from_json(obj)


def discover() -> dict[str, object]:
    """Import every module in intract_features.stages that defines STAGE and run."""
    from intract_features import stages

    found = {}
    for info in pkgutil.iter_modules(stages.__path__):
        mod = importlib.import_module(f"intract_features.stages.{info.name}")
        if hasattr(mod, "STAGE") and hasattr(mod, "run"):
            found[mod.STAGE.name] = mod
    return found


def _peak_rss_mb() -> float | None:
    try:
        import resource  # Unix only; the dry run's numbers come from ARC

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except ImportError:
        return None


def _children_usage() -> tuple[float, float] | None:
    """CPU seconds and peak RSS (MB) of the waited-for child processes so far (Unix only).

    Some stages do part of their work in child processes, the UDPipe server and the phonemizer program among them,
    which process_time and RUSAGE_SELF leave out.
    """
    try:
        import resource

        ru = resource.getrusage(resource.RUSAGE_CHILDREN)
        return ru.ru_utime + ru.ru_stime, ru.ru_maxrss / 1024.0
    except ImportError:
        return None


def _gpu_record() -> dict:
    torch = sys.modules.get("torch")  # only if the stage itself imported torch
    if torch is None or not torch.cuda.is_available():
        return {}
    return {"gpu_name": torch.cuda.get_device_name(0),
            "gpu_peak_allocated_mb": torch.cuda.max_memory_allocated() / 2**20,
            "gpu_peak_reserved_mb": torch.cuda.max_memory_reserved() / 2**20}


def run_stage(mod, ctx: StageContext) -> dict:
    """Run one stage on one shard and write its timing record beside the outputs; return the record."""
    t0, c0, k0 = time.perf_counter(), time.process_time(), _children_usage()
    counts = mod.run(ctx) or {}
    wall, cpu, k1 = time.perf_counter() - t0, time.process_time() - c0, _children_usage()
    rec = {
        "stage": ctx.stage.name, "lang": ctx.lang, "shard": ctx.shard, "nshards": ctx.nshards,
        "device": ctx.stage.device, "env": ctx.stage.env, "package_version": __version__,
        # The environment that actually ran, which a run may choose against the stage's declaration (run_stage.sh).
        "virtual_env": os.environ.get("VIRTUAL_ENV"),
        "code_commit": os.environ.get("INTRACT_CODE_COMMIT", "unknown"),
        "slurm_job_id": os.environ.get("SLURM_JOB_ID"), "slurm_array_task_id": os.environ.get("SLURM_ARRAY_TASK_ID"),
        "host": platform.node(), "python": platform.python_version(),
        "wall_seconds": wall, "cpu_seconds": cpu, "peak_rss_mb": _peak_rss_mb(),
        "children_cpu_seconds": k1[0] - k0[0] if k0 and k1 else None,
        "children_peak_rss_mb": k1[1] if k1 else None,
        "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "counts": counts, **_gpu_record(),
    }
    out = records.artefact_path(ctx.work, ctx.lang, "_timing", ctx.shard, ctx.nshards, ext="json")
    out = out.with_name(f"{ctx.stage.name}-{out.name}")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rec, indent=1, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return rec


def main(argv: list[str] | None = None) -> int:
    """The command line; see the module docstring."""
    p = argparse.ArgumentParser(prog="intract_features")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list-stages")
    r = sub.add_parser("run")
    r.add_argument("stage")
    r.add_argument("--config", type=Path, default=Path(__file__).resolve().parents[2] / "config")
    r.add_argument("--work", type=Path, required=True)
    r.add_argument("--lang", default="en-us")
    r.add_argument("--input", type=Path)
    r.add_argument("--shard", type=int, default=0)
    r.add_argument("--nshards", type=int, default=1)
    r.add_argument("--limit", type=int)
    args = p.parse_args(argv)

    stages = discover()
    if args.cmd == "list-stages":
        for name, mod in sorted(stages.items()):
            s = mod.STAGE
            flow = f"{','.join(s.inputs)} -> {','.join(s.outputs)}"
            print(f"{name:20s} {s.device:4s} env={s.env:8s} {flow}  {s.description}")
        return 0
    if args.stage not in stages:
        p.error(f"unknown stage {args.stage!r}; known: {', '.join(sorted(stages))}")
    if not 0 <= args.shard < args.nshards:
        p.error("--shard must lie in [0, --nshards)")
    cfg = config_mod.load(args.config)
    mod = stages[args.stage]
    ctx = StageContext(stage=mod.STAGE, config=cfg, lang=args.lang, work=args.work, shard=args.shard,
                       nshards=args.nshards, input=args.input, limit=args.limit)
    rec = run_stage(mod, ctx)
    print(json.dumps({k: rec[k] for k in ("stage", "lang", "shard", "wall_seconds", "counts")}, sort_keys=True))
    return 0
