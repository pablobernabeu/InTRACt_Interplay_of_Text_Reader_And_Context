"""Stage and verify every pinned model, code checkout and resource on ARC, and write each run's config.

DESIGN.md, Configuration: "Model and resource pins (repository, revision, file SHA-256, licence) are in
config/models.lock.json and config/resources.lock.json. Code verifies a pin before it loads the file." This helper
fetches what the locks pin, at full commits only, checks every file's SHA-256, converts pickled weights to
safetensors where a lock entry asks for it, and records what it did under $INTRACT_RECORDS/staging/.

    python -I staging.py models [--only KEY ...] [--skip-convert] [--include-optional]
                                                 fetch, verify, convert (j0_build, online)
    python -I staging.py resources [--only KEY ...]                  fetch and verify resources (j0_build, online)
    python -I staging.py verify [--include-optional]                 check everything again, offline
    python -I staging.py disk-plan [--include-optional]              bytes still to download and convert
    python -I staging.py run-config --out DIR [--set STAGE.TABLE.KEY=VALUE ...]
                                                 a run's config: committed + conversion pins (+ overrides)
    python -I staging.py resume-plan --stage S --work W --lang L --nshards N --shards "0 1" [--input P]
                                                 the shards a resubmission must run again
    python -I staging.py qe-pairs --mt FILE [--mt FILE] --lang L --out FILE [--limit N]
    python -I staging.py espeak-plan                                  shell assignments for the eSpeak NG build
    python -I staging.py espeak-check                                 the built eSpeak NG against its pin

Folders come from the variables jobs/arc/env.sh exports (INTRACT_CODE, HF_HUB_CACHE, INTRACT_MODELS,
INTRACT_RESOURCES, INTRACT_SRC, INTRACT_OPT, STANZA_RESOURCES_DIR, INTRACT_UDPIPE_SRC, INTRACT_UDPIPE_MODELS,
INTRACT_RECORDS); no path is written here. Nothing is fetched by branch name, so a shared cache's refs never move,
and no e-mail address or token is sent anywhere. The catalogue's story texts are never read: every input here is a
public model, public code or a public dataset.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import time
import tomllib
import urllib.request
import zlib
from collections.abc import Callable, Iterable, Iterator, Mapping
from pathlib import Path

from intract_features import records

COMMIT = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A plain agent string: nothing that identifies a person (no e-mail address, no token).
USER_AGENT = "intract-features-staging/0.1"


class StagingError(RuntimeError):
    """A pin is missing, a file differs from its pin, or a fetch failed."""


# ------------------------------------------------------------------------------------------------ locks


def env_dir(name: str, environ: Mapping[str, str] | None = None) -> Path:
    """The folder an environment variable names; a missing variable stops the run (no default path)."""
    environ = os.environ if environ is None else environ
    value = environ.get(name, "")
    if not value:
        raise StagingError(f"${name} is not set; source jobs/arc/env.sh first")
    return Path(value)


def config_dir(environ: Mapping[str, str] | None = None) -> Path:
    """The committed config folder, $INTRACT_CODE/config."""
    return env_dir("INTRACT_CODE", environ) / "config"


def load_lock(path: Path, table: str) -> dict:
    """The entries of a lock file, which sit under `table` ("models" or "resources")."""
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = obj.get(table)
    if not isinstance(entries, dict):
        raise StagingError(f"{path} has no {table!r} table")
    return entries


def file_pins(files: Mapping) -> dict[str, str | None]:
    """{relative path: SHA-256 or None} from a "files" table whose values are hashes or {"sha256": ...}."""
    out = {}
    for name, value in files.items():
        out[name] = value.get("sha256") if isinstance(value, Mapping) else value
    return out


def validate_models_lock(entries: Mapping) -> list[str]:
    """Problems with the shape of models.lock.json: revisions must be full commits and hashes full SHA-256.

    A SHA-256 of None is allowed only for a file a "conversion" produces (it is pending until a conversion has
    been recorded and transcribed).
    """
    problems = []
    for key, e in entries.items():
        if not isinstance(e, Mapping):
            problems.append(f"{key}: not a table")
            continue
        for field in ("revision", "source_commit", "models_revision"):
            if field in e and not COMMIT.match(str(e[field])):
                problems.append(f"{key}: {field} {e[field]!r} is not a full commit")
        produced = set((e.get("conversion") or {}).get("map", {}).values())
        if e.get("conversion", {}).get("index"):
            produced.add(e["conversion"]["index"])
        tables = [("files", e.get("files")), ("hub_files", e.get("hub_files")),
                  ("source_files", e.get("source_files"))]
        tables += [(f"model_files.{m}", t) for m, t in (e.get("model_files") or {}).items()]
        if isinstance(e.get("embedding_snapshot"), Mapping):
            tables.append(("embedding_snapshot.files", e["embedding_snapshot"].get("files")))
        if not any(t for _, t in tables) and "resources_json_sha256" not in e:
            problems.append(f"{key}: no file is pinned")
        for label, table in tables:
            if table is None:
                continue
            for name, sha in file_pins(table).items():
                if sha is None:
                    if label != "files" or name not in produced:
                        problems.append(f"{key}: {label}/{name} has no SHA-256")
                elif not SHA256.match(str(sha)):
                    problems.append(f"{key}: {label}/{name} SHA-256 {sha!r} is malformed")
        for field in ("resources_json_sha256", "archive_sha256", "models_txt_sha256"):
            if field in e and not SHA256.match(str(e[field])):
                problems.append(f"{key}: {field} is malformed")
        conv = e.get("conversion")
        if conv is not None:
            if not conv.get("dir") or not conv.get("map"):
                problems.append(f"{key}: conversion needs 'dir' and 'map'")
            missing = set(conv.get("map", {})) - set(file_pins(e.get("hub_files") or {}))
            if missing:
                problems.append(f"{key}: conversion sources {sorted(missing)} are not in hub_files")
    return problems


def validate_resources_lock(entries: Mapping) -> list[str]:
    """Problems with the shape of resources.lock.json."""
    problems = []
    for key, e in entries.items():
        if "sha256" in e and not SHA256.match(str(e["sha256"])):
            problems.append(f"{key}: sha256 is malformed")
        for name, sha in file_pins(e.get("files") or {}).items():
            if not SHA256.match(str(sha or "")):
                problems.append(f"{key}: files/{name} SHA-256 is missing or malformed")
        for field in ("revision", "commit"):
            if field in e and not COMMIT.match(str(e[field])):
                problems.append(f"{key}: {field} is not a full commit")
    return problems


# ------------------------------------------------------------------------------------------- verification


def verify_files(folder: Path, files: Mapping, *, exact: bool = False) -> list[str]:
    """Problems with the pinned files under `folder`; with `exact`, an unpinned file is a problem too."""
    folder = Path(folder)
    problems = []
    pins = file_pins(files)
    for name, sha in sorted(pins.items()):
        target = folder / name
        if not target.is_file():
            problems.append(f"{name} is missing")
        elif sha is None:
            continue
        elif records.sha256_file(target) != str(sha).lower():
            problems.append(f"{name} differs from its pin")
    if exact and folder.is_dir():
        extra = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*")
                       if p.is_file() and p.relative_to(folder).as_posix() not in pins)
        problems += [f"{name} is not pinned" for name in extra]
    return problems


def hub_snapshot(repo: str, revision: str, environ: Mapping[str, str] | None = None) -> Path:
    """The Hugging Face cache's snapshot folder of a commit (HF_HUB_CACHE)."""
    return env_dir("HF_HUB_CACHE", environ) / f"models--{repo.replace('/', '--')}" / "snapshots" / revision


def hub_ref(repo: str, ref: str = "main", environ: Mapping[str, str] | None = None) -> Path:
    """The cache file that names the commit a ref points at."""
    return env_dir("HF_HUB_CACHE", environ) / f"models--{repo.replace('/', '--')}" / "refs" / ref


def ensure_ref_main(repo: str, revision: str, environ: Mapping[str, str] | None = None, *, write: bool = True) -> str:
    """Make refs/main name the pinned commit, for code that loads a snapshot by name offline.

    A ref that already names another commit is left alone and stops the run: the cache is shared with the
    pre-submission strands, so moving it silently could change what their code loads. Without `write`, a missing
    ref is an error instead of being written.
    """
    path = hub_ref(repo, "main", environ)
    if path.is_file():
        found = path.read_text(encoding="utf-8").strip()
        if found != revision:
            raise StagingError(f"{path} names {found}, not the pinned {revision}; resolve it by hand")
        return "present"
    if not write:
        raise StagingError(f"{path} is missing; run staging.py models to write it")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name("main.tmp")
    tmp.write_text(revision, encoding="utf-8")
    tmp.replace(path)
    return "written"


# --------------------------------------------------------------------------------------------- fetching


def _request(url: str, headers: Mapping[str, str] | None = None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    return urllib.request.urlopen(req, timeout=600)


def http_range(url: str) -> Callable[[int, int], bytes]:
    """A function that returns bytes [start, end] of a URL through HTTP range requests."""
    def get(start: int, end: int) -> bytes:
        with _request(url, {"Range": f"bytes={start}-{end}"}) as r:
            if r.status != 206:
                raise StagingError(f"{url} did not honour a range request ({r.status})")
            return r.read()
    return get


def http_size(url: str) -> int:
    """The size of a remote file, from the Content-Range of a one-byte request."""
    with _request(url, {"Range": "bytes=0-0"}) as r:
        return int(r.headers["Content-Range"].rsplit("/", 1)[1])


def zip_entries(get: Callable[[int, int], bytes], size: int) -> list[dict]:
    """The central directory of a ZIP archive (ZIP64 included) read through `get(start, end)`."""
    tail = get(max(0, size - 65536), size - 1)
    i = tail.rfind(b"PK\x05\x06")
    if i < 0:
        raise StagingError("no end-of-central-directory record")
    _, _, _, _, n_total, cd_size, cd_offset, _ = struct.unpack("<IHHHHIIH", tail[i:i + 22])
    if cd_offset == 0xFFFFFFFF or n_total == 0xFFFF:
        j = tail.rfind(b"PK\x06\x07", 0, i)
        if j < 0 or len(tail) < j + 20:
            # Without the locator the 0xFFFFFFFF fields would be read as real offsets, so stop here.
            raise StagingError("the archive marks ZIP64 fields but has no ZIP64 end-of-central-directory locator")
        loc = struct.unpack("<IIQI", tail[j:j + 20])
        z64 = get(loc[2], loc[2] + 55)
        if z64[:4] != b"PK\x06\x06":
            raise StagingError("the ZIP64 locator does not point at a ZIP64 end-of-central-directory record")
        n_total, cd_size, cd_offset = struct.unpack("<IQHHIIQQQQ", z64[:56])[7:10]
    cd = get(cd_offset, cd_offset + cd_size - 1)
    out, p = [], 0
    while p < len(cd) and cd[p:p + 4] == b"PK\x01\x02":
        h = struct.unpack("<IHHHHHHIIIHHHHHII", cd[p:p + 46])
        method, crc, csize, usize, nlen, elen, clen, lho = h[4], h[7], h[8], h[9], h[10], h[11], h[12], h[16]
        name = cd[p + 46:p + 46 + nlen].decode("utf-8")
        extra, q = cd[p + 46 + nlen:p + 46 + nlen + elen], 0
        while q + 4 <= len(extra):
            tag, sz = struct.unpack("<HH", extra[q:q + 4])
            if tag == 1:
                data, k = extra[q + 4:q + 4 + sz], 0
                if usize == 0xFFFFFFFF:
                    usize, k = struct.unpack("<Q", data[k:k + 8])[0], k + 8
                if csize == 0xFFFFFFFF:
                    csize, k = struct.unpack("<Q", data[k:k + 8])[0], k + 8
                if lho == 0xFFFFFFFF:
                    lho = struct.unpack("<Q", data[k:k + 8])[0]
            q += 4 + sz
        out.append({"name": name, "method": method, "crc32": crc, "csize": csize, "usize": usize, "lho": lho})
        p += 46 + nlen + elen + clen
    return out


def zip_member_stream(get: Callable[[int, int], bytes], entry: Mapping, step: int = 8 << 20) -> Iterator[bytes]:
    """The decompressed bytes of one ZIP member, fetched in ranges; its CRC-32 and size are checked at the end."""
    lh = get(entry["lho"], entry["lho"] + 29)
    nlen, elen = struct.unpack("<HH", lh[26:30])
    pos = entry["lho"] + 30 + nlen + elen
    end = pos + entry["csize"]
    if entry["method"] not in (0, 8):
        raise StagingError(f"{entry['name']}: compression method {entry['method']} is not supported")
    d = zlib.decompressobj(-15) if entry["method"] == 8 else None
    crc, n = 0, 0
    while pos < end:
        chunk = get(pos, min(pos + step, end) - 1)
        pos += len(chunk)
        data = d.decompress(chunk) if d else chunk
        crc, n = zlib.crc32(data, crc), n + len(data)
        yield data
    if d:
        rest = d.flush()
        crc, n = zlib.crc32(rest, crc), n + len(rest)
        yield rest
    if (crc & 0xFFFFFFFF) != entry["crc32"] or n != entry["usize"]:
        raise StagingError(f"{entry['name']}: CRC-32 or size differs from the archive's central directory")


def write_verified(dest: Path, chunks: Iterable[bytes], sha256: str) -> Path:
    """Write chunks to a temporary file, check its SHA-256 and rename it into place."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    h = hashlib.sha256()
    try:
        with open(tmp, "wb") as fh:
            for chunk in chunks:
                h.update(chunk)
                fh.write(chunk)
        if h.hexdigest() != sha256:
            raise StagingError(f"{dest.name}: SHA-256 {h.hexdigest()} differs from the pin {sha256}")
        tmp.replace(dest)
    finally:
        tmp.unlink(missing_ok=True)
    return dest


def http_chunks(url: str, chunk: int = 1 << 20) -> Iterator[bytes]:
    """A whole remote file in chunks."""
    with _request(url) as r:
        while True:
            b = r.read(chunk)
            if not b:
                return
            yield b


# ---------------------------------------------------------------------------------------------- models


def git_checkout(url: str, commit: str, dest: Path) -> str:
    """Clone `url` into `dest` and check out `commit`, or check an existing checkout; returns what was done."""
    dest = Path(dest)
    if (dest / ".git").exists():
        head = subprocess.run(["git", "-C", str(dest), "rev-parse", "HEAD"], check=True, capture_output=True,
                              text=True).stdout.strip()
        if head != commit:
            raise StagingError(f"{dest} is at {head}, not the pinned {commit}")
        return "present"
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".clone")
    shutil.rmtree(tmp, ignore_errors=True)
    subprocess.run(["git", "clone", "--quiet", "--no-checkout", url, str(tmp)], check=True)
    subprocess.run(["git", "-C", str(tmp), "-c", "advice.detachedHead=false", "checkout", "--quiet", commit],
                   check=True)
    tmp.rename(dest)
    return "cloned"


def stage_hub_entry(key: str, e: Mapping, *, download: bool, log: Callable[[str], None]) -> dict:
    """Fetch (when `download`) and verify a Hugging Face entry's files at its commit.

    An entry's "cache_id" is the id its consumer loads it by, such as UDPipe 2's legacy
    "bert-base-multilingual-uncased", so the snapshot sits in the cache folder that consumer reads.
    """
    repo, revision = e.get("cache_id") or e["repo"], e["revision"]
    if not COMMIT.match(revision):
        raise StagingError(f"{key}: revision {revision!r} is not a full commit")
    files = e.get("hub_files") or e["files"]
    folder = hub_snapshot(repo, revision)
    missing = [n for n in files if not (folder / n).is_file()]
    if missing and download:
        from huggingface_hub import hf_hub_download  # lazy: only the core environment has it

        for name in missing:
            log(f"{key}: fetching {name}")
            hf_hub_download(repo_id=repo, filename=name, revision=revision, cache_dir=str(env_dir("HF_HUB_CACHE")))
    problems = verify_files(folder, files)
    if problems:
        raise StagingError(f"{key} at {folder}: " + "; ".join(problems))
    rec = {"repo": repo, "revision": revision, "folder": str(folder), "files_verified": len(files)}
    if e.get("hub_ref_main"):
        rec["refs_main"] = ensure_ref_main(repo, revision, write=download)
    return rec


def stage_code_entry(key: str, e: Mapping, *, download: bool) -> dict:
    """Clone (when `download`) and verify a pinned code checkout."""
    co = e["checkout"]
    dest = env_dir(co["dir_env"]) / co["dir"]
    if download:
        done = git_checkout(e["source"], e["revision"], dest)
    elif not dest.is_dir():
        raise StagingError(f"{key}: {dest} is missing")
    else:
        done = "present"
    problems = verify_files(dest, e["files"])
    if problems:
        raise StagingError(f"{key} at {dest}: " + "; ".join(problems))
    return {"repo": e["repo"], "revision": e["revision"], "folder": str(dest), "checkout": done}


def stage_stanza_entry(key: str, e: Mapping) -> dict:
    """Verify the frozen resources.json and the English packages; nothing is downloaded.

    resources.json must never be fetched again: Stanza's default source now serves a different file
    (models.lock.json, resources_json_source).
    """
    root = env_dir(e.get("dir_env", "STANZA_RESOURCES_DIR"))
    rj = root / "resources.json"
    if not rj.is_file() or records.sha256_file(rj) != e["resources_json_sha256"]:
        raise StagingError(f"{rj} is missing or differs from the pinned resources.json")
    problems = verify_files(root, e["files"])
    md5_bad = []
    for name, pin in e["files"].items():
        if (root / name).is_file() and pin.get("md5"):
            h = hashlib.md5(usedforsecurity=False)
            with open(root / name, "rb") as fh:
                for block in iter(lambda f=fh: f.read(1 << 20), b""):
                    h.update(block)
            if h.hexdigest() != pin["md5"]:
                md5_bad.append(name)
    if problems or md5_bad:
        raise StagingError(f"{key}: " + "; ".join(problems + [f"{n} differs from its MD5" for n in md5_bad]))
    return {"folder": str(root), "files_verified": len(e["files"]), "resources_json": "verified"}


def stage_udpipe_entry(key: str, e: Mapping) -> dict:
    """Verify the UDPipe 2 checkout, MODELS.txt, each pinned model and the mBERT snapshot with the stage's own check.

    The 9.5 GB archive is not hashed again here: its SHA-256 was recorded when it was fetched, and every file the
    server loads is checked against the pins derived from it.
    """
    from intract_features.parse.udpipe_server import verify_server_files

    src, models = env_dir("INTRACT_UDPIPE_SRC"), env_dir("INTRACT_UDPIPE_MODELS")
    out = {}
    for model in e["model_files"]:
        out[model] = verify_server_files(src, models, model, e, env_dir("HF_HUB_CACHE"))
    return {"models": out}


def conversion_parameters(e: Mapping, cfg_dir: Path) -> tuple[list[str], dict[str, str]]:
    """The drop patterns and tied keys of a conversion: from the entry, or from the stage config it names."""
    conv = e["conversion"]
    if "parameters" in conv:
        p = conv["parameters"]
        table = tomllib.loads((cfg_dir / p["file"]).read_text(encoding="utf-8"))[p["table"]]
        return list(table[p["drop_key"]]), dict(table[p["tied_key"]])
    return list(conv.get("drop", [])), dict(conv.get("tied", {}))


def check_conversion(original: Mapping, converted: Mapping, drop: list[str], tied: Mapping[str, str]) -> dict:
    """Compare a converted state dict with its source: every tensor equal, every omission explained.

    A key may be missing from the converted file only if a drop pattern matches it, or if it is tied to a key
    whose tensor it equals (as convert_pickled_checkpoint omits them). No key may be added.
    """
    import torch

    dropped, tied_out, bad = [], [], []
    for key, value in original.items():
        if key in converted:
            other = converted[key]
            if other.dtype != value.dtype or other.shape != value.shape or not torch.equal(other, value):
                bad.append(f"{key} differs")
        elif any(re.search(p, key) for p in drop):
            dropped.append(key)
        elif key in tied and tied[key] in original and torch.equal(value, original[tied[key]]):
            tied_out.append(key)
        else:
            bad.append(f"{key} is missing")
    bad += [f"{key} was added" for key in converted if key not in original]
    if bad:
        raise StagingError("the converted weights differ from the source: " + "; ".join(bad[:10]))
    return {"tensors": len(converted), "dropped": sorted(dropped), "tied_omitted": sorted(tied_out)}


def safetensors_index(weight_maps: Mapping[str, Iterable[str]], total_size: int) -> dict:
    """model.safetensors.index.json for converted shards, keys sorted so the file is byte-identical on rerun."""
    weight_map = {}
    for shard, keys in weight_maps.items():
        for k in keys:
            if k in weight_map:
                raise StagingError(f"tensor {k} appears in two shards")
            weight_map[k] = shard
    return {"metadata": {"total_size": total_size}, "weight_map": dict(sorted(weight_map.items()))}


def copy_files(src: Path, dest: Path, names: Iterable[str]) -> None:
    """Copy snapshot files by relative path, creating subfolders (BGE-M3 copies 1_Pooling/config.json)."""
    for name in names:
        (Path(dest) / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(src) / name, Path(dest) / name)


def convert_entry(key: str, e: Mapping, cfg_dir: Path, conversions: dict, log: Callable[[str], None]) -> dict:
    """Build $INTRACT_MODELS/<dir> from the hub snapshot: copied files plus safetensors converted from the pickles.

    The folder is built under a temporary name and renamed when complete and verified, so a job killed half way
    never leaves a folder that looks finished. An existing folder whose files match the recorded hashes is kept.
    """
    import safetensors
    import torch
    from safetensors.torch import load_file

    from intract_features.features.surprisal import convert_pickled_checkpoint

    conv = e["conversion"]
    src = hub_snapshot(e["repo"], e["revision"])
    out = env_dir(conv.get("dir_env", "INTRACT_MODELS")) / conv["dir"]
    pins = file_pins(e["files"])

    def against_pins(hashes: Mapping[str, str]) -> None:
        differ = [n for n, s in pins.items() if s is not None and hashes.get(n) != s]
        if differ:
            raise StagingError(f"{key}: converted files {differ} differ from their committed pins")
        if set(hashes) != set(pins):
            raise StagingError(f"{key}: the converted folder holds {sorted(hashes)}, the pin lists {sorted(pins)}")

    prior = conversions.get(key)
    if out.is_dir() and prior and not verify_files(out, prior["files"], exact=True):
        against_pins(prior["files"])
        log(f"{key}: {out} already matches its recorded conversion")
        return prior
    drop, tied = conversion_parameters(e, cfg_dir)
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        hub_pins = file_pins(e["hub_files"])
        copy_files(src, tmp, conv["copy"])
        checks, weight_maps, total = {}, {}, 0
        for source_name, target_name in sorted(conv["map"].items()):
            log(f"{key}: converting {source_name} to {target_name}")
            if records.sha256_file(src / source_name) != hub_pins[source_name]:
                raise StagingError(f"{key}: {source_name} differs from its pin")
            info = convert_pickled_checkpoint(src / source_name, tmp / target_name, drop=drop, tied=tied)
            original = torch.load(src / source_name, map_location="cpu", weights_only=True)
            converted = load_file(str(tmp / target_name))
            checks[target_name] = {**check_conversion(original, converted, drop, tied), "source": source_name,
                                   "source_sha256": info["source_sha256"]}
            weight_maps[target_name] = sorted(converted)
            total += sum(t.numel() * t.element_size() for t in converted.values())
            del original, converted
        if conv.get("index"):
            index = safetensors_index(weight_maps, total)
            (tmp / conv["index"]).write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        hashes = {p.relative_to(tmp).as_posix(): records.sha256_file(p) for p in sorted(tmp.rglob("*"))
                  if p.is_file()}
        against_pins(hashes)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    rec = {"dir": conv["dir"], "files": hashes, "checks": checks, "drop": drop, "tied": tied,
           "versions": {"torch": torch.__version__, "safetensors": safetensors.__version__},
           "converted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    conversions[key] = rec
    return rec


# ------------------------------------------------------------------------------------------- run config


def overlay_models_lock(lock: dict, conversions: Mapping, models_dir: Path) -> tuple[dict, list[str]]:
    """The committed models.lock.json with each converted entry's folder and its recorded hashes filled in.

    Only a hash that is null in the committed lock is filled; a committed hash that differs from the recorded
    conversion stops the run, because the folder no longer matches what was pinned.
    """
    out = json.loads(json.dumps(lock))
    changes = []
    for key, e in out.get("models", {}).items():
        conv = e.get("conversion")
        if not conv:
            continue
        rec = conversions.get(key)
        folder = Path(models_dir) / conv["dir"]
        if rec is None or not folder.is_dir():
            changes.append(f"{key}: no recorded conversion; its stage cannot verify the weights yet")
            continue
        e["path"] = str(folder)
        changes.append(f"{key}: path {folder}")
        for name, value in e["files"].items():
            recorded = rec["files"].get(name)
            committed = value.get("sha256") if isinstance(value, Mapping) else value
            if committed is None:
                if recorded is None:
                    raise StagingError(f"{key}: the conversion record has no hash for {name}")
                e["files"][name] = {"sha256": recorded, "status": "recorded by this run's conversion, not committed"}
                changes.append(f"{key}: {name} {recorded} (recorded, not committed)")
            elif recorded != committed:
                raise StagingError(f"{key}: {name} is pinned {committed} but the conversion recorded {recorded}")
    return out, changes


OVERRIDE_PART = re.compile(r"^[A-Za-z0-9_-]+$")


def parse_override(text: str) -> tuple[str, list[str], str, str, object]:
    """'<stage>.<table>[.<subtable>].<key>=<TOML value>' as (stage, table path, key, literal, value)."""
    target, sep, literal = text.partition("=")
    parts = target.strip().split(".")
    literal = literal.strip()
    if not sep or len(parts) < 3 or not all(OVERRIDE_PART.match(p) for p in parts):
        raise StagingError(f"--set {text!r}: expected STAGE.TABLE.KEY=VALUE, the value written as in TOML")
    try:
        value = tomllib.loads(f"v = {literal}")["v"]
    except tomllib.TOMLDecodeError as exc:
        raise StagingError(f"--set {text!r}: {literal!r} is not a TOML value ({exc})") from exc
    return parts[0], parts[1:-1], parts[-1], literal, value


def apply_override(toml_text: str, table: list[str], key: str, literal: str, value: object) -> str:
    """The TOML text with `key` of `[table]` set to `literal`; only a key already set on one line is replaced.

    The bf16 check (gpu_bf16.sbatch) changes a stage's precision this way in its run's own copy of config/, so the
    committed files never change. The edited text is parsed again and must give the requested value, so a key whose
    value spans several lines, or a table that is missing, stops the run instead of producing a different config.
    """
    header = "[" + ".".join(table) + "]"
    lines = toml_text.splitlines(keepends=True)
    current = None
    for i, line in enumerate(lines):
        stripped = line.split("#", 1)[0].strip().replace(" ", "")
        if stripped.startswith("[") and not stripped.startswith("[["):
            current = stripped
            continue
        if current == header and re.match(rf"^\s*{re.escape(key)}\s*=", line):
            indent = line[:len(line) - len(line.lstrip())]
            lines[i] = f"{indent}{key} = {literal}\n"
            break
    else:
        raise StagingError(f"{header} has no key {key!r}; --set only replaces a value that is already set")
    new_text = "".join(lines)
    try:
        node = tomllib.loads(new_text)
        for part in table:
            node = node[part]
        found = node[key]
    except (tomllib.TOMLDecodeError, KeyError, TypeError) as exc:
        raise StagingError(f"setting {header} {key} = {literal} breaks the file ({exc})") from exc
    if found != value:
        raise StagingError(f"{header} {key} reads {found!r} after the change, not {value!r}")
    return new_text


def write_run_config(out: Path, cfg_dir: Path, models_dir: Path, overrides: Iterable[str] = ()) -> dict:
    """Copy the committed config to `out`, overlay the conversion pins and any overrides; return the record."""
    out = Path(out)
    lock_path = cfg_dir / "models.lock.json"
    conv_path = Path(models_dir) / "conversions.json"
    conversions = json.loads(conv_path.read_text(encoding="utf-8")) if conv_path.is_file() else {}
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    new_lock, changes = overlay_models_lock(lock, conversions, Path(models_dir))
    tmp = out.with_name(out.name + ".tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.copytree(cfg_dir, tmp, ignore=shutil.ignore_patterns("__pycache__"))
    (tmp / "models.lock.json").write_text(json.dumps(new_lock, indent=1, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    applied = []
    try:
        for text in overrides:
            stage, table, key, literal, value = parse_override(text)
            path = tmp / "stages" / f"{stage}.toml"
            if not path.is_file():
                raise StagingError(f"--set {text!r}: config/stages/{stage}.toml does not exist")
            path.write_text(apply_override(path.read_text(encoding="utf-8"), table, key, literal, value),
                            encoding="utf-8", newline="\n")
            applied.append({"stage": stage, "table": ".".join(table), "key": key, "value": value})
            changes.append(f"override: stages/{stage}.toml [{'.'.join(table)}] {key} = {literal}")
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    record = {"source_config": str(cfg_dir), "models_lock_sha256": records.sha256_file(lock_path),
              "conversions_sha256": records.sha256_file(conv_path) if conv_path.is_file() else None,
              "overrides": applied, "changes": changes,
              "written_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    (tmp / "OVERLAY.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8")
    shutil.rmtree(out, ignore_errors=True)
    tmp.rename(out)
    return record


# ------------------------------------------------------------------------------------------- resuming


def shard_files(work: Path, lang: str, artefacts: Iterable[str], shard: int, nshards: int) -> dict[str, list[Path]]:
    """The finished files of each artefact for one shard ({artefact: [paths]}, temporary files left out)."""
    out = {}
    for artefact in artefacts:
        folder = Path(work) / lang / artefact
        out[artefact] = sorted(p for p in folder.glob(f"shard-{shard}-of-{nshards}.*")
                               if p.is_file() and not p.name.endswith(".tmp"))
    return out


def resume_reason(record: Path, commit: str, inputs: Mapping[str, list[Path]], outputs: Mapping[str, list[Path]],
                  extra_inputs: Iterable[Path] = ()) -> str | None:
    """None when a finished shard may be skipped on resubmission, else why it must run again.

    cli.py writes the timing record only after a stage's outputs are complete, so a record shows the shard
    finished. It is trusted only when it was written by the code that would run now (the commit, or the tree hash
    env.sh computes, which covers config/ too; a dirty or unknown version is never trusted), when the shard's
    outputs are still there, and when every input is older than the record, so a rerun upstream reruns this shard.
    """
    record = Path(record)
    if not record.is_file() or record.stat().st_size == 0:
        return "no timing record"
    try:
        rec = json.loads(record.read_text(encoding="utf-8"))
    except ValueError:
        return "the timing record is not valid JSON"
    if not commit or commit == "unknown" or commit.endswith("-dirty"):
        return f"the code version {commit!r} cannot identify the code that wrote the record"
    if not isinstance(rec, dict) or rec.get("code_commit") != commit:
        found = rec.get("code_commit") if isinstance(rec, dict) else None
        return f"the record was written by code {found!r}, and the code is now {commit!r}"
    missing = [a for a, paths in outputs.items() if not paths]
    if missing:
        return f"output {', '.join(missing)} is missing"
    when = record.stat().st_mtime
    for artefact, paths in inputs.items():
        if not paths:
            return f"input {artefact} is missing"
        newer = [p.name for p in paths if p.stat().st_mtime > when]
        if newer:
            return f"input {artefact}/{newer[0]} is newer than the record"
    for path in extra_inputs:
        path = Path(path)
        if not path.exists():
            return f"input {path} is missing"
        if path.stat().st_mtime > when:
            return f"input {path.name} is newer than the record"
    return None


def resume_plan(stage, work: Path, lang: str, nshards: int, shards: Iterable[int], commit: str,
                extra_inputs: Iterable[Path] = (), log: Callable[[str], None] = print) -> list[int]:
    """The shards of `shards` that must run, given each one's timing record (resume_reason)."""
    run = []
    for shard in shards:
        record = Path(work) / lang / "_timing" / f"{stage.name}-shard-{shard}-of-{nshards}.json"
        reason = resume_reason(record, commit, shard_files(work, lang, stage.inputs, shard, nshards),
                               shard_files(work, lang, stage.outputs, shard, nshards), extra_inputs)
        if reason is None:
            log(f"{stage.name} shard {shard} of {nshards}: done before by this code, skipped")
        else:
            log(f"{stage.name} shard {shard} of {nshards}: runs ({reason})")
            run.append(shard)
    return run


# ------------------------------------------------------------------------------------------- resources


def stage_resource(key: str, e: Mapping, *, download: bool, log: Callable[[str], None]) -> dict:
    """Fetch (when `download`) and verify one resources.lock.json entry that names a file or a folder."""
    if "files" in e:  # read in place, for instance the translated benchmark's outputs
        folder = env_dir(e["dir_env"]) / e["path"]
        problems = verify_files(folder, e["files"])
        if problems:
            raise StagingError(f"{key} at {folder}: " + "; ".join(problems))
        return {"folder": str(folder), "files_verified": len(e["files"])}
    dest = env_dir(e["dir_env"]) / e["path"]
    if dest.is_file() and records.sha256_file(dest) == e["sha256"]:
        return {"file": str(dest), "status": "present"}
    if not download:
        raise StagingError(f"{key}: {dest} is missing or differs from its pin")
    reuse = e.get("reuse")
    if reuse:
        src = env_dir(reuse["dir_env"]) / reuse["path"]
        if src.is_file() and records.sha256_file(src) == e["sha256"]:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest)
            return {"file": str(dest), "status": f"copied from {src}"}
    source = e.get("source") or {}
    if source.get("member"):
        url = source["url"]
        get = http_range(url)
        entry = next((z for z in zip_entries(get, http_size(url)) if z["name"].split("/")[-1] == source["member"]),
                     None)
        if entry is None:
            raise StagingError(f"{key}: {source['member']} is not in {url}")
        log(f"{key}: fetching {source['member']} ({entry['csize']} bytes compressed) by range requests")
        write_verified(dest, zip_member_stream(get, entry), e["sha256"])
        return {"file": str(dest), "status": "fetched (zip member, CRC-32 and SHA-256 checked)"}
    if e.get("url"):
        log(f"{key}: fetching {e['url']}")
        write_verified(dest, http_chunks(e["url"]), e["sha256"])
        return {"file": str(dest), "status": "fetched"}
    raise StagingError(f"{key}: no way to fetch {dest}")


def wordfreq_file_check(key: str, e: Mapping) -> dict:
    """The wordfreq data file inside the installed package, against its pin (it arrives with the locked wheel)."""
    import importlib.util

    spec = importlib.util.find_spec("wordfreq")
    if spec is None or not spec.origin:
        raise StagingError("wordfreq is not installed in this environment")
    path = Path(spec.origin).parent / "data" / key.split("/", 1)[1]
    if records.sha256_file(path) != e["sha256"]:
        raise StagingError(f"{path} differs from its pin {e['sha256']}")
    return {"file": str(path), "status": "verified"}


# ------------------------------------------------------------------------------------------- qe pairs


def qe_pairs(rows: Iterable[Mapping], tag: str, lang: str, limit: int | None = None) -> Iterator[dict]:
    """qe_metricx input rows from the translated benchmark's {"src", "out"} records, one text per sentence pair.

    The stand-in has no translations, so the dry run times MetricX on these public pairs (qe_metricx.py).
    """
    for i, row in enumerate(rows):
        if limit is not None and i >= limit:
            return
        src, mt = row.get("src"), row.get("out")
        if not isinstance(src, str) or not isinstance(mt, str):
            raise StagingError(f"{tag}, row {i + 1}: 'src' and 'out' must be strings")
        yield {"pair_id": f"{tag}-{i:06d}", "src": src, "mt": mt, "lang": lang}


# ---------------------------------------------------------------------------------------------- eSpeak NG


def espeak_plan(e: Mapping, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """The eSpeak NG build's settings, from its resources.lock.json entry."""
    b = e["build"]
    return {"ESPEAK_REPO": e["repo"], "ESPEAK_TAG": e["tag"], "ESPEAK_COMMIT": e["commit"],
            "ESPEAK_SRC": str(env_dir(e["checkout"]["dir_env"], environ) / e["checkout"]["dir"]),
            "ESPEAK_PREFIX": str(env_dir(b["prefix_env"], environ) / b["prefix"]),
            "ESPEAK_CONFIGURE": " ".join(b["configure"]), "ESPEAK_MODULES": " ".join(b["modules"])}


def espeak_check(e: Mapping) -> dict:
    """The checkout's commit and the version phonemizer reports, against the pin.

    The version is read exactly as the duration feature reads it before phonemizing (features/duration.py,
    parse_versions), so a build that would stop that stage stops here first.
    """
    from intract_features.features.duration import parse_versions

    plan = espeak_plan(e)
    head = subprocess.run(["git", "-C", plan["ESPEAK_SRC"], "rev-parse", "HEAD"], check=True, capture_output=True,
                          text=True).stdout.strip()
    if head != e["commit"]:
        raise StagingError(f"{plan['ESPEAK_SRC']} is at {head}, not {e['commit']}")
    program = subprocess.run([str(Path(plan["ESPEAK_PREFIX"]) / "bin" / "espeak-ng"), "--version"], check=True,
                             capture_output=True, text=True).stdout.strip()
    text = subprocess.run([sys.executable, "-I", "-m", "phonemizer.main", "--version"], check=True,
                          capture_output=True, text=True).stdout
    phonemizer_version, espeak_version = parse_versions(text)
    if espeak_version != e["tag"]:
        raise StagingError(f"phonemizer reports eSpeak NG {espeak_version!r}, not {e['tag']}: {text.strip()!r}")
    return {"commit": head, "program": program, "phonemizer": phonemizer_version, "espeak_ng": espeak_version}


# ------------------------------------------------------------------------------------------------- main


def _save_record(name: str, rec: dict) -> Path:
    folder = env_dir("INTRACT_RECORDS") / "staging"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(rec, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def _log(msg: str) -> None:
    print(f"[staging {time.strftime('%H:%M:%S')}] {msg}", flush=True)


def selected(key: str, e: Mapping, only: list[str] | None, include_optional: bool) -> bool:
    """Whether an entry is staged: named by --only, or every entry, optional ones only when asked for.

    An "optional" entry, such as the safetensors copy of MetricX-24 that no stage reads, costs disk, memory and
    time to convert, so it is staged only on request (--include-optional, or --only naming it).
    """
    if only:
        return key in only
    return include_optional or not e.get("optional")


def disk_plan(entries: Mapping, include_optional: bool = False, environ: Mapping[str, str] | None = None) -> dict:
    """Bytes the selected entries still need: hub files not yet in the cache, and conversions not yet built.

    j0_build compares the total with the free space under $FEAT before it downloads anything, so a quota that
    cannot hold the models stops the build at once instead of part way through a 10 GB file.
    """
    seen, download, convert, items = set(), 0, 0, []
    for key, e in entries.items():
        if not selected(key, e, None, include_optional) or "checkout" in e or "revision" not in e:
            continue
        files = e.get("hub_files") or e.get("files") or {}
        folder = hub_snapshot(e.get("cache_id") or e["repo"], e["revision"], environ)
        for name, pin in files.items():
            size = pin.get("bytes") if isinstance(pin, Mapping) else None
            ident = (e.get("cache_id") or e["repo"], e["revision"], name)
            if size and ident not in seen and not (folder / name).is_file():
                seen.add(ident)
                download += int(size)
                items.append({"entry": key, "file": name, "bytes": int(size), "for": "download"})
        conv = e.get("conversion")
        if conv and not (env_dir(conv.get("dir_env", "INTRACT_MODELS"), environ) / conv["dir"]).is_dir():
            # safetensors hold the same tensors as the pickles they come from, so the sources' size bounds them.
            size = sum(int((files.get(n) or {}).get("bytes") or 0) for n in [*conv["map"], *conv.get("copy", [])])
            convert += size
            items.append({"entry": key, "file": conv["dir"], "bytes": size, "for": "conversion"})
    return {"download_bytes": download, "conversion_bytes": convert, "total_bytes": download + convert,
            "items": items}


def run_models(only: list[str] | None, download: bool, convert: bool, include_optional: bool = False) -> dict:
    """Stage or verify the selected models.lock.json entries; conversions are recorded in conversions.json."""
    cfg = config_dir()
    entries = load_lock(cfg / "models.lock.json", "models")
    problems = validate_models_lock(entries)
    if problems:
        raise StagingError("models.lock.json is malformed: " + "; ".join(problems))
    conv_path = env_dir("INTRACT_MODELS") / "conversions.json"
    conversions = json.loads(conv_path.read_text(encoding="utf-8")) if conv_path.is_file() else {}
    out, failed = {}, {}
    for key, e in entries.items():
        if not selected(key, e, only, include_optional):
            if e.get("optional") and not only:
                out[key] = {"status": "optional, not staged (--include-optional stages it)"}
            continue
        try:
            if key.startswith("stanza-"):
                out[key] = stage_stanza_entry(key, e)
            elif key.startswith("udpipe-"):
                out[key] = stage_udpipe_entry(key, e)
            elif "checkout" in e:
                out[key] = stage_code_entry(key, e, download=download)
            else:
                out[key] = stage_hub_entry(key, e, download=download, log=_log)
                if e.get("conversion") and convert:
                    out[key]["conversion"] = convert_entry(key, e, cfg, conversions, _log)
                    conv_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp = conv_path.with_name(conv_path.name + ".tmp")
                    tmp.write_text(json.dumps(conversions, indent=1, sort_keys=True) + "\n", encoding="utf-8")
                    tmp.replace(conv_path)
                elif e.get("conversion"):
                    folder = env_dir(e["conversion"].get("dir_env", "INTRACT_MODELS")) / e["conversion"]["dir"]
                    rec = conversions.get(key)
                    bad = verify_files(folder, rec["files"], exact=True) if rec else ["no recorded conversion"]
                    if bad:
                        raise StagingError(f"{key}: converted folder {folder}: " + "; ".join(bad))
            _log(f"{key}: ok")
        except Exception as exc:  # every entry is tried, so one run reports every broken pin
            failed[key] = f"{type(exc).__name__}: {exc}"
            _log(f"{key}: FAILED {failed[key]}")
    return {"verified": out, "failed": failed}


def run_resources(only: list[str] | None, download: bool) -> dict:
    """Stage or verify the resources.lock.json entries this helper can fetch."""
    entries = load_lock(config_dir() / "resources.lock.json", "resources")
    problems = validate_resources_lock(entries)
    if problems:
        raise StagingError("resources.lock.json is malformed: " + "; ".join(problems))
    out, failed = {}, {}
    for key, e in entries.items():
        if only and key not in only:
            continue
        try:
            if key.startswith("wordfreq-"):
                out[key] = wordfreq_file_check(key, e)
            elif key.startswith("espeak-ng"):
                out[key] = espeak_check(e) if not download else {"status": "built by j0_build"}
            elif key == "simplestories":
                out[key] = {"status": "fetched and verified by python -m standin.build_standin download"}
            else:
                out[key] = stage_resource(key, e, download=download, log=_log)
            _log(f"{key}: ok")
        except Exception as exc:
            failed[key] = f"{type(exc).__name__}: {exc}"
            _log(f"{key}: FAILED {failed[key]}")
    return {"verified": out, "failed": failed}


def main(argv: list[str] | None = None) -> int:
    """Command line; see the module docstring."""
    p = argparse.ArgumentParser(prog="staging.py", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("models")
    m.add_argument("--only", nargs="*")
    m.add_argument("--skip-convert", action="store_true")
    m.add_argument("--include-optional", action="store_true")
    r = sub.add_parser("resources")
    r.add_argument("--only", nargs="*")
    v = sub.add_parser("verify")
    v.add_argument("--include-optional", action="store_true")
    d = sub.add_parser("disk-plan")
    d.add_argument("--include-optional", action="store_true")
    c = sub.add_parser("run-config")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--set", dest="overrides", action="append", default=[], metavar="STAGE.TABLE.KEY=VALUE")
    rp = sub.add_parser("resume-plan")
    rp.add_argument("--stage", required=True)
    rp.add_argument("--work", type=Path, required=True)
    rp.add_argument("--lang", required=True)
    rp.add_argument("--nshards", type=int, required=True)
    rp.add_argument("--shards", required=True, help="space- or comma-separated shard indices")
    rp.add_argument("--input", type=Path, action="append", default=[])
    rp.add_argument("--commit", default=os.environ.get("INTRACT_CODE_COMMIT", "unknown"))
    q = sub.add_parser("qe-pairs")
    q.add_argument("--mt", type=Path, action="append", required=True)
    q.add_argument("--lang", required=True)
    q.add_argument("--out", type=Path, required=True)
    q.add_argument("--limit", type=int)
    q.add_argument("--pin", default="translated_benchmark_mt_de", help="resources.lock.json entry pinning --mt")
    sub.add_parser("espeak-plan")
    sub.add_parser("espeak-check")
    args = p.parse_args(argv)

    try:
        if args.cmd == "models":
            rec = run_models(args.only, download=True, convert=not args.skip_convert,
                             include_optional=args.include_optional)
            print(_save_record("models", rec))
            return 1 if rec["failed"] else 0
        if args.cmd == "resources":
            rec = run_resources(args.only, download=True)
            print(_save_record("resources", rec))
            return 1 if rec["failed"] else 0
        if args.cmd == "verify":
            rec = {"models": run_models(None, download=False, convert=False, include_optional=args.include_optional),
                   "resources": run_resources(None, download=False)}
            print(_save_record("verify", rec))
            return 1 if rec["models"]["failed"] or rec["resources"]["failed"] else 0
        if args.cmd == "disk-plan":
            plan = disk_plan(load_lock(config_dir() / "models.lock.json", "models"), args.include_optional)
            print(json.dumps({k: v for k, v in plan.items() if k != "items"}), file=sys.stderr)
            print(plan["total_bytes"])
            return 0
        if args.cmd == "run-config":
            rec = write_run_config(args.out, config_dir(), env_dir("INTRACT_MODELS"), args.overrides)
            for line in rec["changes"]:
                print(f"run-config: {line}")
            return 0
        if args.cmd == "resume-plan":
            from intract_features.cli import discover  # lazy: the other subcommands run before any stage exists

            stages = discover()
            if args.stage not in stages:
                raise StagingError(f"unknown stage {args.stage!r}")
            shards = [int(s) for s in re.split(r"[,\s]+", args.shards.strip()) if s]
            todo = resume_plan(stages[args.stage].STAGE, args.work, args.lang, args.nshards, shards, args.commit,
                               args.input, log=lambda m: print(f"resume: {m}", file=sys.stderr))
            print(" ".join(map(str, todo)))
            return 0
        if args.cmd == "qe-pairs":
            pins = load_lock(config_dir() / "resources.lock.json", "resources")[args.pin]
            want = file_pins(pins["files"])
            rows = []
            for path in args.mt:
                if want.get(path.name) != records.sha256_file(path):
                    raise StagingError(f"{path} is not the file {args.pin} pins")
                rows.extend(qe_pairs(records.read_jsonl(path), path.stem, args.lang, args.limit))
            print(f"qe-pairs: {records.write_jsonl(args.out, rows)} pairs written to {args.out}")
            return 0
        entry = load_lock(config_dir() / "resources.lock.json", "resources")["espeak-ng-1.52.0"]
        if args.cmd == "espeak-plan":
            for k, v in espeak_plan(entry).items():
                print(f"{k}={shlex.quote(v)}")
            return 0
        print(json.dumps(espeak_check(entry), indent=1))
        return 0
    except StagingError as exc:
        print(f"staging: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
