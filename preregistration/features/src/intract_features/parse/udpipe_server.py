"""UDPipe 2's own REST server, run locally and deterministically, and the launcher the parse_udpipe stage uses.

Promoted from presub/error_model/scripts/udpipe2_det_server.py, which served EM-2 (gold parses) and TU-4u (the
translated benchmark). Supplementary S3 registers "UDPipe 2 with its models of release 2.17" and that "UDPipe 2 runs
on a GPU with deterministic operations, and it moves to a CPU if a rerun of the pilot on 1 per cent of the catalogue
does not reproduce identical output". On L40S, fresh-server reruns under these settings gave byte-identical parses
for 46 of 46 gold files (EM-2, error_model/parses/determinism_gpu.json).

Server (inside the udpipe environment):

    python -I -m intract_features.parse.udpipe_server --udpipe-src SRC --models-dir DIR --model NAME
        --port PORT --threads N --seed SEED [-- upstream arguments, such as --batch_size 32]

Pins (to fill models.lock.json on the machine that holds the verified archive, checkout and encoder snapshot):

    python -I -m intract_features.parse.udpipe_server --print-pins --udpipe-src SRC --models-dir DIR --model NAME
        [--archive PATH --archive-sha256 HEX] [--hf-hub-cache DIR --embedding-repo ID --embedding-commit SHA]

The upstream server, udpipe2_server.py of ufal/udpipe at the pinned commit, runs unmodified through runpy. The
changes are around it:
* it binds to 127.0.0.1 only (upstream binds every interface), so no text leaves the node;
* TensorFlow op determinism on, TF32 off, and the global seeds set before any network is built (each UDPipe 2 graph
  also carries its own graph seed); legacy Keras (TF_USE_LEGACY_KERAS=1) for the TensorFlow transformers model that
  computes the mBERT embeddings;
* it serves only the named models, with the paths, treebank variants and acknowledgements of the archive's
  MODELS.txt, and a model's network loads on the first request for it;
* when a GPU is allocated, the environment's own CUDA libraries go on LD_LIBRARY_PATH before TensorFlow loads, and
  the server exits if TensorFlow still sees no GPU (below);
* it logs, as JSON lines on stderr, the versions and devices when it starts ("udpipe_server: versions") and, when
  upstream returns after its SIGINT shutdown, its own CPU time, peak memory and each GPU's peak allocation
  ("udpipe_server: resources"), because the stage's timing record measures only the parent process.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import runpy
import signal
import socket
import socketserver
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

# The module must import with the standard library alone: it runs in the udpipe environment before TensorFlow
# loads, and the shared helpers below are the only intract_features imports.
from intract_features.parse import PinError, sha256_file

# ------------------------------------------------------------------------------------------------ GPU and CUDA


def gpu_allocated(environ: Mapping[str, str]) -> bool:
    """Whether the job holds a GPU: CUDA_VISIBLE_DEVICES names one, or Slurm GPU variables are set without it.

    A caller that hides the GPU with CUDA_VISIBLE_DEVICES="" (as EM-3 did for the CPU timing) runs on the CPU.
    """
    cvd = environ.get("CUDA_VISIBLE_DEVICES")
    if cvd is not None:
        return cvd.strip() not in ("", "-1", "NoDevFiles")
    return bool(environ.get("SLURM_JOB_GPUS") or environ.get("SLURM_STEP_GPUS"))


def cuda_library_dirs(prefix: str, version: Sequence[int]) -> list[str]:
    """The environment's pip-installed CUDA library directories (site-packages/nvidia/*/lib)."""
    pattern = os.path.join(prefix, "lib", f"python{version[0]}.{version[1]}", "site-packages", "nvidia", "*", "lib")
    return sorted(glob.glob(pattern))


def library_path_for_reexec(environ: Mapping[str, str], dirs: Sequence[str]) -> str | None:
    """The LD_LIBRARY_PATH to re-execute with, or None when every CUDA directory is already on it.

    TensorFlow 2.21's libtensorflow_framework.so.2, which loads the CUDA libraries, lists no nvidia/cusolver/lib in
    its RUNPATH, so without these directories libcusolver.so.11 is not found and TensorFlow silently skips the GPU
    (diagnosis job 9150967; the TU-4u smoke 9150946 logged "gpus []"). The dynamic loader reads LD_LIBRARY_PATH only
    when a process starts, hence the re-execution.
    """
    current = [d for d in environ.get("LD_LIBRARY_PATH", "").split(":") if d]
    if dirs and not set(dirs) <= set(current):
        return ":".join([*dirs, *current])
    return None


def _maybe_reexec() -> None:
    if os.name != "posix" or not gpu_allocated(os.environ):
        return
    new = library_path_for_reexec(os.environ, cuda_library_dirs(sys.prefix, sys.version_info))
    if new is None:
        return
    os.environ["LD_LIBRARY_PATH"] = new
    sys.stderr.write("udpipe_server: re-executing with the environment's CUDA libraries on LD_LIBRARY_PATH\n")
    sys.stderr.flush()
    # Same PID, same interpreter flags and arguments (sys.orig_argv keeps -I and -m), so a caller that tracks the
    # process keeps the right one.
    os.execv(sys.executable, [sys.executable, *sys.orig_argv[1:]])


def configure_tensorflow(seed: int) -> dict:
    """Deterministic TensorFlow before any network is built; returns the versions and devices for the log.

    A job that holds a GPU must not fall back to the CPU: at the CPU rate (about 136 words per CPU-second for
    English, EM-3) a GPU-sized job cannot finish in its time limit, so the server exits at once, freeing the GPU and
    leaving the cause in its log.
    """
    os.environ["TF_USE_LEGACY_KERAS"] = "1"
    os.environ["TF_DETERMINISTIC_OPS"] = "1"
    os.environ["NVIDIA_TF32_OVERRIDE"] = "0"
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "1")
    import numpy as np  # lazy: only the udpipe environment has them
    import tensorflow as tf

    tf.config.experimental.enable_op_determinism()
    gpus = tf.config.list_physical_devices("GPU")
    if gpu_allocated(os.environ) and not gpus:
        sys.exit(f"udpipe_server: a GPU is allocated (CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}) "
                 "but TensorFlow sees none; exiting instead of running on the CPU")
    tf.config.experimental.enable_tensor_float_32_execution(False)
    tf.keras.utils.set_random_seed(seed)
    np.random.seed(seed)
    import transformers

    return {"tensorflow": tf.__version__, "transformers": transformers.__version__, "numpy": np.__version__,
            "gpus": [d.name for d in gpus], "op_determinism": op_determinism_enabled(),
            "tf32": tf.config.experimental.tensor_float_32_execution_enabled(),
            "gpu_allocated": gpu_allocated(os.environ), "seed": seed}


def op_determinism_enabled() -> bool | None:
    """Whether TensorFlow holds op determinism on, read back from TensorFlow itself (None if it cannot be read).

    TensorFlow 2.21 exports enable_op_determinism but no getter: is_op_determinism_enabled in
    tensorflow/python/framework/config.py carries no tf_export decorator, so it is read from that module.
    """
    try:
        from tensorflow.python.framework import config as tf_framework_config  # lazy: udpipe environment only
    except ImportError:
        return None
    getter = getattr(tf_framework_config, "is_op_determinism_enabled", None)
    return bool(getter()) if getter is not None else None


def resource_record(started: float) -> dict:
    """This process's cost when upstream returns: serving seconds, CPU seconds, peak memory, GPU peak allocations.

    CPU time and peak resident memory come from getrusage (Unix); each GPU's peak comes from TensorFlow's allocator
    (tf.config.experimental.get_memory_info, keys "current" and "peak" in bytes), read only if TensorFlow is loaded.
    """
    out: dict = {"serve_seconds": time.monotonic() - started}
    try:
        import resource  # Unix only
    except ImportError:
        resource = None
    if resource is not None:
        ru = resource.getrusage(resource.RUSAGE_SELF)
        out.update(cpu_seconds=ru.ru_utime + ru.ru_stime, peak_rss_mb=ru.ru_maxrss / 1024.0)
    tf = sys.modules.get("tensorflow")
    if tf is not None:
        gpus = {}
        for i, _ in enumerate(tf.config.list_logical_devices("GPU")):
            try:
                info = tf.config.experimental.get_memory_info(f"GPU:{i}")
            except (ValueError, RuntimeError):  # a diagnostic must not hide the server's own exit
                continue
            gpus[f"GPU:{i}"] = {"peak_mb": info["peak"] / 2**20, "current_mb": info["current"] / 2**20}
        out["gpu_memory"] = gpus
    return out


def bind_localhost_only() -> None:
    """Make every socketserver.TCPServer bind 127.0.0.1 where upstream asks for all interfaces."""
    original = socketserver.TCPServer.__init__

    def _init(self, addr, handler, bind_and_activate=True):
        if addr[0] in ("", "0.0.0.0"):
            addr = ("127.0.0.1", addr[1])
        original(self, addr, handler, bind_and_activate)

    socketserver.TCPServer.__init__ = _init


# ------------------------------------------------------------------------------------- models and upstream argv


def read_models_table(path: Path) -> dict[str, list[str]]:
    """MODELS.txt of the 2.17 archive: first model name -> [names, path, variant, acknowledgements].

    Each line holds four whitespace-separated fields; the first is a colon-separated list of names, of which the
    first is the model's name in requests. Lines with another field count are not model lines.
    """
    table = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) == 4:
            table[parts[0].split(":")[0]] = parts
    return table


def upstream_argv(src: Path, models_dir: Path, table: Mapping[str, list[str]], wanted: Sequence[str], port: int,
                  threads: int, extra: Sequence[str]) -> list[str]:
    """sys.argv for udpipe2_server.py: port, default model, then names, path, variant and acknowledgements per model."""
    args = []
    for name in wanted:
        if name not in table:
            raise KeyError(f"model {name!r} is not in MODELS.txt")
        names, path, variant, ack = table[name]
        args += [names, str(Path(models_dir) / path), variant, ack]
    return [str(Path(src) / "udpipe2_server.py"), str(port), wanted[0], *args, "--threads", str(threads), *extra]


def tree_hashes(root: Path, pattern: str = "**/*") -> dict[str, str]:
    """SHA-256 of every regular file under `root` matching `pattern`, keyed by POSIX path relative to `root`.

    Version-control metadata is left out, so a checkout and a copy of it hash alike.
    """
    root = Path(root)
    out = {}
    for p in sorted(root.glob(pattern)):
        rel = p.relative_to(root)
        if p.is_file() and ".git" not in rel.parts:
            out[rel.as_posix()] = sha256_file(p)
    return out


def verify_tree(root: Path, pinned: Mapping[str, str], what: str, pattern: str = "**/*") -> int:
    """Check that the files under `root` are exactly the pinned ones with the pinned SHA-256; return their number.

    An extra file is an error too, because the server could load it.
    """
    if not pinned:
        raise PinError(f"no SHA-256 pins for {what}; record them in models.lock.json (see --print-pins)")
    got = tree_hashes(root, pattern)
    bad = [f"{rel} missing" for rel in sorted(set(pinned) - set(got))]
    bad += [f"{rel} not pinned" for rel in sorted(set(got) - set(pinned))]
    bad += [f"{rel} has SHA-256 {got[rel]}, pinned {pinned[rel]}" for rel in sorted(set(got) & set(pinned))
            if got[rel] != pinned[rel].lower()]
    if bad:
        raise PinError(f"{what} under {root} fails its pins: " + "; ".join(bad[:10]))
    return len(got)


def model_path(models_dir: Path, table: Mapping[str, list[str]], name: str) -> Path:
    """Directory of a model, as MODELS.txt places it in the extracted archive."""
    if name not in table:
        raise KeyError(f"model {name!r} is not in MODELS.txt")
    return Path(models_dir) / table[name][1]


def _hub_repo_dir(hub_cache: Path, repo: str) -> Path:
    return Path(hub_cache) / f"models--{repo.replace('/', '--')}"


def verify_embedding_snapshot(hub_cache: Path | None, snap: Mapping | None) -> dict:
    """Check the multilingual BERT that UDPipe 2 loads for its word embeddings.

    UDPipe 2's wembeddings module loads the encoder by its legacy id with no revision, so offline the transformers
    library resolves it through refs/main of the cache folder named after the id (presub error_model get_mbert.py).
    That reference must name the pinned commit, and the snapshot's files must match their SHA-256 pins.
    """
    if not snap:
        raise PinError("models.lock.json pins no embedding snapshot for UDPipe 2 (embedding_snapshot)")
    if hub_cache is None:
        raise PinError("the Hugging Face hub cache is not set, so the embedding snapshot cannot be verified")
    repo, commit = snap["repo"], snap["commit"]
    ref = _hub_repo_dir(hub_cache, repo) / "refs" / "main"
    found = ref.read_text(encoding="utf-8").strip() if ref.is_file() else None
    if found != commit:
        raise PinError(f"{ref} names {found!r}; UDPipe 2 would not load the pinned {repo}@{commit}")
    n = verify_tree(_hub_repo_dir(hub_cache, repo) / "snapshots" / commit, snap.get("files") or {},
                    f"the embedding model {repo}@{commit[:8]}")
    return {"repo": repo, "commit": commit, "files": n}


def verify_server_files(src: Path, models_dir: Path, model: str, pin: Mapping, hub_cache: Path | None = None) -> dict:
    """Verify everything the server will load against the pin before it starts.

    The pin holds `source_files` (SHA-256 of every Python file of the checkout, wembedding_service included),
    `models_txt_sha256`, `model_files` {model name: {relative path: SHA-256}} and `embedding_snapshot` {repo,
    commit, files}. They are derived from the archive verified against its own SHA-256 (models.lock.json,
    "archive_sha256"), from the checkout at the pinned commit and from the staged encoder snapshot.
    """
    n_src = verify_tree(src, pin.get("source_files") or {}, "the UDPipe 2 source", "**/*.py")
    models_txt = Path(models_dir) / "MODELS.txt"
    want = pin.get("models_txt_sha256")
    if not want or not models_txt.is_file() or sha256_file(models_txt) != want.lower():
        raise PinError(f"{models_txt} is missing or differs from its pin ({want})")
    table = read_models_table(models_txt)
    files = (pin.get("model_files") or {}).get(model) or {}
    n_model = verify_tree(model_path(models_dir, table, model), files, f"the UDPipe model {model}")
    embedding = verify_embedding_snapshot(hub_cache, pin.get("embedding_snapshot"))
    return {"source_files": n_src, "model_files": n_model, "models_txt_sha256": want.lower(),
            "source_commit": pin.get("source_commit"), "archive_sha256": pin.get("archive_sha256"), "model": model,
            "embedding_snapshot": embedding}


def print_pins(src: Path, models_dir: Path, models: Sequence[str], archive: Path | None = None,
               archive_sha256: str | None = None, hub_cache: Path | None = None, embedding_repo: str | None = None,
               embedding_commit: str | None = None) -> dict:
    """The models.lock.json fields for a verified archive, checkout and encoder snapshot (run once, where staged).

    When an archive path is given, its SHA-256 is checked against the pinned value first, so the per-file pins
    descend from the archive's own pin; the encoder snapshot is pinned only if refs/main already names its commit.
    """
    if archive is not None:
        got = sha256_file(archive)
        if not archive_sha256 or got != archive_sha256.lower():
            raise PinError(f"{archive} has SHA-256 {got}, pinned {archive_sha256}")
    table = read_models_table(Path(models_dir) / "MODELS.txt")
    out = {"source_files": tree_hashes(src, "**/*.py"),
           "models_txt_sha256": sha256_file(Path(models_dir) / "MODELS.txt"),
           "model_files": {m: tree_hashes(model_path(models_dir, table, m)) for m in models}}
    if archive is not None:
        out["archive_sha256"] = archive_sha256.lower()
    if hub_cache is not None and embedding_repo and embedding_commit:
        ref = _hub_repo_dir(hub_cache, embedding_repo) / "refs" / "main"
        if not ref.is_file() or ref.read_text(encoding="utf-8").strip() != embedding_commit:
            raise PinError(f"{ref} does not name {embedding_commit}")
        snapshot = _hub_repo_dir(hub_cache, embedding_repo) / "snapshots" / embedding_commit
        out["embedding_snapshot"] = {"repo": embedding_repo, "commit": embedding_commit,
                                     "files": tree_hashes(snapshot)}
    return out


# ------------------------------------------------------------------------------------------------------ launcher


def free_port() -> int:
    """A free TCP port on 127.0.0.1 (the operating system picks it, so two servers on one node never collide)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_command(*, python: str, src: Path, models_dir: Path, model: str, port: int, threads: int, seed: int,
                   batch_size: int, max_request_size: int) -> list[str]:
    """The command that starts the deterministic server for one model (isolated mode, as in every presub job).

    The upstream batch and request-size limits are passed explicitly, so the client's size check and the server
    agree whatever upstream's defaults (32 and 4 MiB at the pinned commit).
    """
    return [python, "-I", "-m", "intract_features.parse.udpipe_server", "--udpipe-src", str(src),
            "--models-dir", str(models_dir), "--model", model, "--port", str(port), "--threads", str(threads),
            "--seed", str(seed), "--", "--batch_size", str(batch_size), "--max_request_size", str(max_request_size)]


def children_usage() -> dict | None:
    """CPU seconds and peak resident memory of this process's finished children (getrusage; None off Unix).

    ru_maxrss of RUSAGE_CHILDREN is the largest finished child's peak, not a sum.
    """
    try:
        import resource  # Unix only
    except ImportError:
        return None
    ru = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {"cpu_seconds": ru.ru_utime + ru.ru_stime, "peak_rss_mb": ru.ru_maxrss / 1024.0}


class ServerProcess:
    """Start a server as a child process, wait until it answers, and stop it on exit.

    Replaces the start_server and stop_server shell functions of the presub jobs: poll /models until it answers,
    fail at once if the process dies (with the end of its log), stop with SIGINT and kill only if it lingers. Every
    timing comes from config/stages/parse_udpipe.toml. After it stops, `usage` holds the child's CPU seconds (the
    change in RUSAGE_CHILDREN across its life) and the largest peak memory of any finished child so far, because
    the stage's own timing record measures the parent process only.
    """

    def __init__(self, cmd: Sequence[str], base_url: str, log_path: Path, *, startup_timeout: float,
                 poll_interval: float, stop_timeout: float, probe_timeout: float,
                 env: Mapping[str, str] | None = None):
        self.cmd, self.base_url, self.log_path = list(cmd), base_url, Path(log_path)
        self.env = dict(env) if env is not None else None
        self.startup_timeout, self.poll_interval, self.stop_timeout = startup_timeout, poll_interval, stop_timeout
        self.probe_timeout = probe_timeout
        self.proc: subprocess.Popen | None = None
        self.startup_seconds: float | None = None
        self.usage: dict | None = None
        self._usage_before: dict | None = None
        self._log = None

    def __enter__(self) -> ServerProcess:
        from intract_features.parse.udpipe_client import wait_for_server

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log = open(self.log_path, "wb")
        self._usage_before = children_usage()
        self.proc = subprocess.Popen(self.cmd, stdout=self._log, stderr=subprocess.STDOUT, env=self.env)
        try:
            self.startup_seconds = wait_for_server(self.base_url, self.startup_timeout, self.poll_interval,
                                                   probe_timeout=self.probe_timeout,
                                                   alive=lambda: self.proc.poll() is None)
        except Exception as e:
            self.stop()
            raise RuntimeError(f"UDPipe server did not start: {e}\n{self.log_tail()}") from e
        except BaseException:  # an interrupt must not leave the server running
            self.stop()
            raise
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def stop(self) -> int | None:
        """Interrupt the server, wait, and kill it if it does not exit; return its exit code."""
        if self.proc is None:
            return None
        if self.proc.poll() is None:
            if os.name == "posix":
                self.proc.send_signal(signal.SIGINT)
            else:
                self.proc.terminate()
            try:
                self.proc.wait(self.stop_timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self._log is not None and not self._log.closed:
            self._log.close()
        after = children_usage()
        if self.usage is None and after is not None and self._usage_before is not None:
            self.usage = {"cpu_seconds": after["cpu_seconds"] - self._usage_before["cpu_seconds"],
                          "peak_rss_mb_largest_child": after["peak_rss_mb"]}
        return self.proc.returncode

    def log_tail(self, lines: int = 50) -> str:
        """The last lines of the server log."""
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(text.splitlines()[-lines:])

    def log_record(self, tag: str) -> dict | None:
        """The JSON the server logged on its line "udpipe_server: <tag> {...}", or None."""
        prefix = f"udpipe_server: {tag} "
        try:
            text = self.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        for line in text.splitlines():
            if line.startswith(prefix):
                try:
                    return json.loads(line[len(prefix):])
                except ValueError:
                    return None
        return None

    def versions(self) -> dict | None:
        """The versions and devices the server logged at start."""
        return self.log_record("versions")

    def resources(self) -> dict | None:
        """The server's own CPU time, peak memory and GPU peak allocations, logged when upstream returned."""
        return self.log_record("resources")


# ---------------------------------------------------------------------------------------------------------- main


def _args(argv: Sequence[str] | None) -> tuple[argparse.Namespace, list[str]]:
    argv = list(sys.argv[1:] if argv is None else argv)
    extra = []
    if "--" in argv:
        i = argv.index("--")
        argv, extra = argv[:i], argv[i + 1:]
    p = argparse.ArgumentParser(prog="intract_features.parse.udpipe_server")
    p.add_argument("--udpipe-src", type=Path, required=True)
    p.add_argument("--models-dir", type=Path, required=True)
    p.add_argument("--model", action="append", required=True)
    p.add_argument("--port", type=int)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--seed", type=int)
    p.add_argument("--print-pins", action="store_true")
    p.add_argument("--archive", type=Path)
    p.add_argument("--archive-sha256")
    p.add_argument("--hf-hub-cache", type=Path)
    p.add_argument("--embedding-repo")
    p.add_argument("--embedding-commit")
    args = p.parse_args(argv)
    if not args.print_pins and (args.port is None or args.seed is None):
        p.error("--port and --seed are required to serve")
    return args, extra


def main(argv: Sequence[str] | None = None) -> int:
    """Serve the named models deterministically on 127.0.0.1, or print their pins."""
    args, extra = _args(argv)
    if args.print_pins:
        pins = print_pins(args.udpipe_src, args.models_dir, args.model, args.archive, args.archive_sha256,
                          args.hf_hub_cache, args.embedding_repo, args.embedding_commit)
        print(json.dumps(pins, indent=1, sort_keys=True))
        return 0
    _maybe_reexec()
    record = configure_tensorflow(args.seed)
    record["ld_library_path_cuda_dirs"] = sum(1 for d in os.environ.get("LD_LIBRARY_PATH", "").split(":")
                                              if "/site-packages/nvidia/" in d)
    print("udpipe_server: versions " + json.dumps(record, sort_keys=True), file=sys.stderr, flush=True)
    bind_localhost_only()
    table = read_models_table(args.models_dir / "MODELS.txt")
    upstream = args.udpipe_src / "udpipe2_server.py"
    # Upstream imports its sibling modules (udpipe2, wembedding_service) as a script run from its own directory
    # would; isolated mode (-I) leaves that directory off sys.path, so it is put there for this process alone.
    sys.path.insert(0, str(args.udpipe_src))
    sys.argv = upstream_argv(args.udpipe_src, args.models_dir, table, args.model, args.port, args.threads, extra)
    started = time.monotonic()
    try:
        # Upstream blocks SIGINT and SIGUSR1, waits for one with sigwait, shuts down and falls off the end of its
        # script, so run_path returns; the finally clause also covers an upstream exception.
        runpy.run_path(str(upstream), run_name="__main__")
    finally:
        print("udpipe_server: resources " + json.dumps(resource_record(started), sort_keys=True), file=sys.stderr,
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
