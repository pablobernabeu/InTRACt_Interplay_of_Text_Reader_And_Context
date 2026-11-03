"""Stage parse_udpipe: UDPipe 2 (models of release 2.17) on every registered sentence of every text.

Reads `documents` and `segments` and writes `parses_udpipe` (CoNLL-U, sentence k of a text = sentence k of its
segmentation; format in intract_features.parse). Supplementary S3: "UDPipe 2 with its models of release 2.17 ...
Both run on every sentence of every text", and "UDPipe 2 runs on a GPU with deterministic operations". The stage
verifies the source checkout, MODELS.txt, the model's files and the encoder snapshot against models.lock.json,
starts the deterministic local server (parse/udpipe_server.py) on a free port of 127.0.0.1, sends each call's
sentences in one presegmented request (parse/udpipe_client.py) and stops the server. Constants are in
config/stages/parse_udpipe.toml; the input rules both parsers share are read from the stage it names
(input_config_stage, parse_stanza.toml), so the two artefacts cannot be cut differently.

A sentence the server refuses as longer than its 1,000-word limit keeps an empty block marked `# refused`, and
long_units.RefusalCheck checks each such unit against S3's long-unit rule. An already running server (server_url,
or ctx.extra["udpipe_url"]) cannot have its files verified, so it is accepted only where
allow_unverified_external_server is set, which is for tests.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from intract_features import config as config_mod
from intract_features.cli import Stage, StageContext
from intract_features.parse import SegmentRules, iter_parsed, join_units, model_pin, parse_shard
from intract_features.parse.long_units import LongUnitRule, RefusalCheck
from intract_features.parse.udpipe_client import UDPipeClient
from intract_features.parse.udpipe_server import (
    ServerProcess,
    free_port,
    gpu_allocated,
    server_command,
    verify_server_files,
)

STAGE = Stage(name="parse_udpipe", inputs=("documents", "segments"), outputs=("parses_udpipe",), device="gpu",
              env="udpipe", description="UDPipe 2 (2.17 models) parse of the registered sentences on a local "
                                        "deterministic server (S3)")


def _env_dir(name: str) -> Path:
    value = os.environ.get(name, "")
    if not value:
        raise RuntimeError(f"${name} is not set; it must name a directory of the UDPipe set-up")
    return Path(value)


def _client(base_url: str, model: str, scfg: dict) -> UDPipeClient:
    return UDPipeClient(base_url, model, tokenizer=scfg["tokenizer"], timeout=float(scfg["request_timeout_s"]),
                        retries=int(scfg["retries"]), retry_sleep=float(scfg["retry_sleep_s"]),
                        max_request_bytes=int(scfg["max_request_bytes"]))


def _server(ctx: StageContext, scfg: dict, src: Path, models_dir: Path, model: str, seed: int,
            tag: str) -> ServerProcess:
    port = free_port()
    env = dict(os.environ)
    # The server runs offline against the verified snapshots: nothing is fetched, and no request leaves the node.
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_HUB_DISABLE_TELEMETRY="1")
    if scfg["device"] == "cpu":
        env["CUDA_VISIBLE_DEVICES"] = ""  # the registered CPU fallback, run as EM-3 ran it
    log = ctx.work / ctx.lang / "_logs" / f"{STAGE.name}-shard-{ctx.shard}-of-{ctx.nshards}.{tag}.log"
    cmd = server_command(python=sys.executable, src=src, models_dir=models_dir, model=model, port=port,
                         threads=int(scfg["threads"]), seed=seed, batch_size=int(scfg["server_batch_size"]),
                         max_request_size=int(scfg["max_request_bytes"]))
    return ServerProcess(cmd, f"http://127.0.0.1:{port}", log, env=env,
                         startup_timeout=float(scfg["startup_timeout_s"]), poll_interval=float(scfg["poll_interval_s"]),
                         stop_timeout=float(scfg["stop_timeout_s"]), probe_timeout=float(scfg["probe_timeout_s"]))


def _rerun(client: UDPipeClient, kept: list, max_skip: int, sentences_per_call: int, fresh: bool) -> dict:
    """Reparse the kept texts, grouped into the same calls, and compare their CoNLL-U byte for byte (PRS-03)."""
    items = [(doc, units) for doc, units, _ in kept]
    again = [text for *_, text, _ in iter_parsed(items, client.parse, max_skip=max_skip,
                                                 sentences_per_call=sentences_per_call)]
    same = [a == text for a, (_, _, text) in zip(again, kept, strict=True)]
    result = {"documents": len(same), "identical": sum(same), "all_identical": all(same), "fresh_server": fresh}
    if not result["all_identical"]:
        print(f"parse_udpipe: rerun differs in {len(same) - sum(same)} of {len(same)} texts", file=sys.stderr)
    return result


def _report_refusals(check: RefusalCheck) -> None:
    """Name the refused units on stderr (the run record holds counts only)."""
    if check.refused:
        print(f"parse_udpipe: UDPipe refused {check.refused} unit(s) as longer than 1,000 words; {check.long} long "
              f"under S3, {check.not_long} not long, {check.unchecked} unchecked", file=sys.stderr)
    for unit in check.not_long_units:
        print(f"parse_udpipe: refused unit {unit} is not long under S3", file=sys.stderr)


def run(ctx: StageContext) -> dict:
    """Parse one shard of one language and return the counts and the server record for the timing record."""
    scfg = ctx.stage_config()
    icfg = ctx.config["stages"][scfg["input_config_stage"]]
    lcfg = config_mod.language(ctx.config, ctx.lang)
    model = lcfg["udpipe_model"]
    seed = int(ctx.config["seeds"]["base"])
    max_skip, keep = int(icfg["offset_max_skip"]), int(scfg["rerun_check_documents"])
    per_call = int(scfg["calls"]["sentences_per_call"])
    out = ctx.path("parses_udpipe", ext="conllu.gz")
    # The inputs are paired and checked before the server starts (about three minutes on L40S), so a bad shard
    # fails at once.
    items = list(join_units(ctx.documents(), ctx.read("segments"), lang=ctx.lang,
                            field_name=icfg["input"]["segments_field"],
                            rules=SegmentRules.from_config(icfg["segments"]),
                            allow_uncovered_text=bool(icfg["input"]["allow_uncovered_text"]),
                            line_breaks=icfg["input"]["line_breaks"]))
    mode = scfg["refusals"]["refused_not_long"]
    if mode not in ("flag", "fail"):
        raise ValueError(f"[refusals] refused_not_long must be 'flag' or 'fail', not {mode!r}")
    refusals = RefusalCheck(LongUnitRule.from_config(ctx.config, STAGE.name), spaced=bool(lcfg["spaced"]),
                            fail=mode == "fail")
    record: dict = {"model": model, "seed": seed, "device": scfg["device"], "tokenizer": scfg["tokenizer"],
                    "server_batch_size": int(scfg["server_batch_size"]), "threads": int(scfg["threads"]),
                    "sentences_per_call": per_call}

    def parse(client_: UDPipeClient):
        def check(_) -> str | None:
            return client_.model_problem() or refusals.problem()

        return parse_shard(out, items, client_.parse, max_skip=max_skip, keep_first=keep, check=check,
                           sentences_per_call=per_call, observe=refusals.observe)

    url = ctx.extra.get("udpipe_url") or scfg["server_url"]
    if url:
        if not scfg["allow_unverified_external_server"]:
            raise RuntimeError("an already running UDPipe server cannot have its checkout, model and encoder "
                               "verified against models.lock.json; the stage starts its own server unless "
                               "allow_unverified_external_server is set (tests only)")
        client = _client(url, model, scfg)
        try:
            counts, kept = parse(client)
        finally:
            _report_refusals(refusals)
        record.update(server={"external": True}, pins_verified=None)
        if keep:
            record["rerun_check"] = _rerun(client, kept, max_skip, per_call, fresh=False)
    else:
        if scfg["device"] == "gpu" and not gpu_allocated(os.environ):
            raise RuntimeError("parse_udpipe runs on a GPU (S3) and none is allocated; device = \"cpu\" in "
                               "parse_udpipe.toml is the registered CPU fallback")
        src, models_dir = _env_dir(scfg["udpipe_src_env"]), _env_dir(scfg["models_dir_env"])
        hub = os.environ.get(scfg["hf_hub_cache_env"])
        record["pins_verified"] = verify_server_files(src, models_dir, model,
                                                      model_pin(ctx.config, scfg["models_lock_key"]),
                                                      Path(hub) if hub else None)
        with _server(ctx, scfg, src, models_dir, model, seed, "server") as server:
            client = _client(server.base_url, model, scfg)
            try:
                counts, kept = parse(client)
            finally:
                _report_refusals(refusals)
        record["server"] = {"external": False, "startup_seconds": server.startup_seconds,
                            "versions": server.versions(), "resources": server.resources(),
                            "process": server.usage, "exit_code": server.proc.returncode}
        if keep:
            with _server(ctx, scfg, src, models_dir, model, seed, "rerun") as fresh:
                record["rerun_check"] = _rerun(_client(fresh.base_url, model, scfg), kept, max_skip, per_call,
                                               fresh=True)
    return {**counts.as_dict(), "udpipe": {**record, **client.stats(), "refusal_check": refusals.record()}}
