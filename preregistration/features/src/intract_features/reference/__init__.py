"""English-source references: coreference chains, translation-quality estimates and word alignment.

None of these tools computes a feature value. Materials (preregistration.qmd): "Every feature value is computed on
the text as served. The English source of the same story version may decide masks and validation gates [...]". The
three modules serve that role:

- corpipe_run: CorPipe 26 resolves coreference on every English source (supplementary.qmd S3, referential overlap
  row: "CorPipe 26 [...], with its umT5-xl one-stage model, instead resolves coreference on every English source as
  a validation reference").
- metricx_qe: MetricX-24-Hybrid-XL scores every translated page against its English page without a reference
  (Sensitivity analyses, ninth family; S3, "Every translated page is scored against its English source by
  MetricX-24-Hybrid-XL in its reference-free quality-estimation mode").
- align: SimAlign-style word alignment with multilingual BERT, which projects English names and coreference chains
  onto a translation (Materials, the names paragraph and the English-source rule; S3, "word alignment with
  multilingual BERT").

This module holds what the three share: verification of pinned files before anything loads them (DESIGN.md,
Configuration: "Code verifies a pin before it loads the file"), the Hugging Face cache layout, and the torch settings
that DESIGN.md fixes for determinism ("Language models and encoders run in fp32 with TF32 off"). torch is imported
only inside TorchRuntime.apply(), so the module loads with the standard library alone.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from intract_features.parse import PinError, model_pin
from intract_features.records import sha256_file

__all__ = ["PinError", "TorchRuntime", "hf_cache_ref", "hf_snapshot_dir", "model_pin", "pin_files",
           "pinned_folder", "verify_pinned_files"]


def pin_files(entry: Mapping) -> list[tuple[str, str]]:
    """The (relative path, SHA-256) pairs a models.lock.json entry lists under "files".

    The same shapes segment/sat.py accepts: a mapping of path to SHA-256, a mapping of path to {"sha256": ...}, or a
    list of {"path": ..., "sha256": ...}. An entry without files cannot be verified, so it stops the stage.
    """
    files = entry.get("files")
    if isinstance(files, Mapping):
        out = [(str(name), str(v["sha256"] if isinstance(v, Mapping) else v)) for name, v in files.items()]
    elif isinstance(files, list):
        out = [(str(f.get("path") or f.get("name")), str(f["sha256"])) for f in files]
    else:
        out = []
    if not out:
        raise PinError(f"the pin {entry.get('repo') or entry.get('repository')!r} lists no file hashes to verify")
    return out


def verify_pinned_files(folder: Path, entry: Mapping, *, what: str) -> list[dict]:
    """Check every pinned file under `folder` against its SHA-256 and return them for the run record.

    Every missing or differing file is named in one PinError, so a broken snapshot is diagnosed in one run.
    """
    folder = Path(folder)
    verified, bad = [], []
    for name, sha in pin_files(entry):
        target = folder / name
        if not target.is_file():
            bad.append(f"{name} is missing")
            continue
        got = sha256_file(target)
        if got.lower() != sha.lower():
            bad.append(f"{name} has SHA-256 {got}, pinned {sha}")
            continue
        verified.append({"file": name, "sha256": got, "bytes": target.stat().st_size})
    if bad:
        raise PinError(f"{what} under {folder} fails its pins: " + "; ".join(bad))
    return verified


def _hub_root(environ: Mapping[str, str]) -> Path:
    hub = environ.get("HF_HUB_CACHE")
    if hub:
        return Path(hub)
    home = environ.get("HF_HOME") or str(Path.home() / ".cache" / "huggingface")
    return Path(home) / "hub"


def hf_snapshot_dir(repo: str, revision: str, environ: Mapping[str, str] | None = None) -> Path:
    """The Hugging Face cache's snapshot folder of a pinned revision (HF_HUB_CACHE, else HF_HOME/hub)."""
    environ = os.environ if environ is None else environ
    return _hub_root(environ) / f"models--{repo.replace('/', '--')}" / "snapshots" / revision


def hf_cache_ref(repo: str, ref: str = "main", environ: Mapping[str, str] | None = None) -> str | None:
    """The revision a cache ref points at, or None if the cache holds no such ref.

    Code that loads a model by its hub name in offline mode reads the snapshot named in refs/<ref>, so a pin on
    such a load must also check that the ref names the pinned revision.
    """
    environ = os.environ if environ is None else environ
    path = _hub_root(environ) / f"models--{repo.replace('/', '--')}" / "refs" / ref
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


def pinned_folder(entry: Mapping, *, env_name: str | None = None, environ: Mapping[str, str] | None = None) -> Path:
    """The folder holding a pinned snapshot, before verification.

    In order: the entry's "path"; the folder named by the environment variable `env_name`; the Hugging Face cache's
    snapshot of the entry's repository at its revision. No path is written in code (DESIGN.md, Configuration).
    """
    environ = os.environ if environ is None else environ
    if entry.get("path"):
        return Path(entry["path"])
    if env_name and environ.get(env_name):
        return Path(environ[env_name])
    repo = entry.get("repo") or entry.get("repository") or entry.get("repo_id")
    revision = entry.get("revision") or entry.get("commit")
    if not repo or not revision:
        raise PinError(f"the pin {repo!r} names no repository and revision, and ${env_name} is not set")
    return hf_snapshot_dir(str(repo), str(revision), environ)


@dataclass(frozen=True)
class TorchRuntime:
    """The torch settings of a GPU stage, from a [runtime] table of its config.

    DESIGN.md, Determinism: "Language models and encoders run in fp32 with TF32 off. bf16 is used only where the
    budget guard allows it, and the bf16 check reports agreement with fp32." Deterministic kernels need cuBLAS's
    workspace setting in the environment before CUDA starts, so apply() sets it before torch is imported.
    """

    dtype: str = "float32"
    allow_tf32: bool = False
    deterministic_algorithms: bool = True
    deterministic_warn_only: bool = True
    cublas_workspace_config: str = ":4096:8"
    device: str = "cuda"
    threads: int = 0
    offline: bool = True

    DTYPES = ("float32", "bfloat16")

    @classmethod
    def from_config(cls, table: Mapping) -> TorchRuntime:
        """Read a [runtime] table; unknown dtypes and devices stop the stage."""
        rt = cls(dtype=str(table.get("dtype", "float32")), allow_tf32=bool(table.get("allow_tf32", False)),
                 deterministic_algorithms=bool(table.get("deterministic_algorithms", True)),
                 deterministic_warn_only=bool(table.get("deterministic_warn_only", True)),
                 cublas_workspace_config=str(table.get("cublas_workspace_config", ":4096:8")),
                 device=str(table.get("device", "cuda")), threads=int(table.get("threads", 0)),
                 offline=bool(table.get("offline", True)))
        if rt.dtype not in cls.DTYPES:
            raise ValueError(f"dtype must be one of {cls.DTYPES}, not {rt.dtype!r}")
        if rt.device not in ("cuda", "cpu", "auto") and not rt.device.startswith("cuda:"):
            raise ValueError(f"device must be 'cuda', 'cuda:<n>', 'cpu' or 'auto', not {rt.device!r}")
        return rt

    def environment(self) -> dict[str, str]:
        """Environment variables to set before torch starts CUDA (and before any hub lookup)."""
        env = {}
        if self.deterministic_algorithms:
            env["CUBLAS_WORKSPACE_CONFIG"] = self.cublas_workspace_config
        if self.offline:
            # Nothing is fetched at run time: every file comes from a verified snapshot.
            env["HF_HUB_OFFLINE"] = "1"
            env["TRANSFORMERS_OFFLINE"] = "1"
        return env

    def apply(self) -> dict:
        """Set the environment and torch's global flags; return what was set, for the run record."""
        for key, value in self.environment().items():
            os.environ.setdefault(key, value)
        import torch  # lazy: unit tests run without it

        torch.backends.cuda.matmul.allow_tf32 = self.allow_tf32
        torch.backends.cudnn.allow_tf32 = self.allow_tf32
        if self.deterministic_algorithms:
            torch.use_deterministic_algorithms(True, warn_only=self.deterministic_warn_only)
            torch.backends.cudnn.benchmark = False
        if self.threads > 0:
            torch.set_num_threads(self.threads)
        return {"torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
                "allow_tf32": torch.backends.cuda.matmul.allow_tf32,
                "deterministic_algorithms": torch.are_deterministic_algorithms_enabled(),
                "cublas_workspace_config": os.environ.get("CUBLAS_WORKSPACE_CONFIG"), "dtype": self.dtype,
                "threads": torch.get_num_threads()}

    def torch_device(self):
        """The torch.device to run on; a configured CUDA device without a visible GPU stops the stage."""
        import torch

        if self.device == "auto":
            return torch.device("cuda" if torch.cuda.is_available() else "cpu")
        if self.device.startswith("cuda") and not torch.cuda.is_available():
            raise RuntimeError(f"the stage is configured for {self.device}, but no GPU is visible")
        return torch.device(self.device)

    def torch_dtype(self):
        """The torch dtype named by `dtype`."""
        import torch

        return getattr(torch, self.dtype)
