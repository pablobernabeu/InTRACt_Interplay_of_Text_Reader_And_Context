"""How the parts of the pipeline fit together: stage names, artefacts, configuration, environments and documents.

Each builder tested its own modules; these tests hold the contracts between them, so that a change to one part
that breaks another fails here. They read only the package's source, its configuration, the environment locks and
the documentation files; no model, resource or story text is opened.
"""

import ast
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

from intract_features import cli, records
from intract_features.text import keyed

FEATURES = Path(__file__).resolve().parents[2]
SRC = FEATURES / "src"
CONFIG = FEATURES / "config"

# The fixed names of the first version (DESIGN.md, Artefacts and stages; README.md, Stages).
STAGES = frozenset({"documents", "sat", "seg_check", "parse_stanza", "parse_udpipe", "features_gramlex",
                    "features_discourse", "surprisal_goldfish", "surprisal_xglm", "encode_e5", "encode_bgem3",
                    "coref_corpipe", "qe_metricx", "aggregate_timing"})
ARTEFACTS = frozenset({"documents", "segments", "parses_stanza", "parses_udpipe", "features_gramlex",
                       "features_discourse", "surprisal_goldfish", "surprisal_xglm", "encode_e5", "encode_bgem3",
                       "coref_corpipe", "qe_metricx"})
ENVIRONMENTS = frozenset({"core", "udpipe", "corpipe", "metricx"})

# Import names whose distribution is named otherwise.
DISTRIBUTION = {"google": "protobuf", "tf_keras": "tf-keras", "ufal": "ufal-udpipe"}
# Packages a stage needs at run time that no import of the package names: programs and servers the stage starts
# in its own environment, and libraries that its imports load in turn.
RUNTIME = {
    # phonemizer 3.4.0 runs as a separate program (python -I -m phonemizer.main), never imported (features/duration.py)
    "features_discourse": {"phonemizer"},
    # the unmodified udpipe2_server.py runs in the stage's environment (parse/udpipe_server.py)
    "parse_udpipe": {"tensorflow", "tf-keras", "transformers", "ufal-udpipe", "ufal-chu-liu-edmonds"},
    # the official CorPipe script runs in the stage's environment (reference/corpipe_run.py)
    "coref_corpipe": {"minnt", "udapi", "sentencepiece", "torch", "transformers"},
    # build_tokenizer reads spiece.model with sentencepiece's generated protobuf module (reference/metricx_qe.py)
    "qe_metricx": {"protobuf"},
}
# Imports a stage's modules make that its environment need not hold in the first, English version, and why.
NOT_NEEDED_FOR_ENGLISH = {
    "opencc": "Traditional Chinese lookups only (S3, tw2s); added to core before the zh-tw run (P81)",
}


def lock_packages(env: str) -> set[str]:
    """The distribution names pinned in envs/<env>.lock, normalised as PEP 503 names."""
    names = set()
    for line in (FEATURES / "envs" / f"{env}.lock").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?==", line)
        if m:
            names.add(re.sub(r"[-_.]+", "-", m.group(1)).lower())
    return names


def module_file(name: str) -> Path | None:
    path = SRC.joinpath(*name.split("."))
    if (path / "__init__.py").is_file():
        return path / "__init__.py"
    return path.with_suffix(".py") if path.with_suffix(".py").is_file() else None


def third_party_imports(start: str) -> set[str]:
    """Top-level third-party modules imported anywhere (lazily too) in the package modules `start` reaches."""
    seen, found, todo = set(), set(), [start]
    while todo:
        name = todo.pop()
        path = module_file(name)
        if name in seen or path is None:
            continue
        seen.add(name)
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    parts = package.split(".")
                    base = ".".join(parts[:len(parts) - node.level + 1] + ([node.module] if node.module else []))
                targets = [base] + [f"{base}.{a.name}" for a in node.names]
            else:
                continue
            for target in targets:
                top = target.split(".")[0]
                if top == "intract_features":
                    parts = target.split(".")
                    prefixes = (".".join(parts[:i]) for i in range(len(parts), 0, -1))
                    todo.extend(p for p in prefixes if module_file(p))
                elif top and top not in sys.stdlib_module_names and top != "__future__":
                    found.add(top)
    return found


def test_the_fourteen_stages_are_discovered_with_their_fixed_names():
    found = cli.discover()
    assert set(found) == STAGES
    for name, mod in found.items():
        stage = mod.STAGE
        assert mod.__name__ == f"intract_features.stages.{name}", "a stage's module is named after the stage"
        assert stage.device in ("cpu", "gpu") and stage.env in ENVIRONMENTS
        assert set(stage.outputs) <= ARTEFACTS and set(stage.inputs) <= ARTEFACTS, name
        assert (CONFIG / "stages" / f"{name}.toml").is_file(), f"config/stages/{name}.toml is missing"


def test_every_artefact_has_one_producer_and_every_input_a_producer():
    producers: dict[str, list[str]] = {}
    for name, mod in cli.discover().items():
        for out in mod.STAGE.outputs:
            producers.setdefault(out, []).append(name)
    assert set(producers) == ARTEFACTS
    assert all(len(p) == 1 for p in producers.values()), producers
    for mod in cli.discover().values():
        assert set(mod.STAGE.inputs) <= set(producers)


def test_no_stage_runs_in_the_metricx_environment():
    # envs/metricx is Python 3.11 with the official MetricX-24 pins, where this package (Python >= 3.12) cannot be
    # installed; it serves the one-off validation of the port only (envs/README.md).
    assert all(mod.STAGE.env != "metricx" for mod in cli.discover().values())


def test_every_package_a_stage_needs_is_locked_in_its_environment():
    for name, mod in cli.discover().items():
        env = mod.STAGE.env
        locked = lock_packages(env)
        needed = {DISTRIBUTION.get(m, m) for m in third_party_imports(mod.__name__)} | RUNTIME.get(name, set())
        needed = {re.sub(r"[-_.]+", "-", n).lower() for n in needed} - set(NOT_NEEDED_FOR_ENGLISH)
        missing = sorted(needed - locked)
        assert not missing, f"{name} (env {env}) needs {missing}, which envs/{env}.lock does not pin"


def test_the_stand_in_builder_runs_in_core():
    # jobs/arc/j1_standin.sbatch builds the stand-in in the core environment; pyarrow reads the parquet shards.
    assert "pyarrow" in lock_packages("core")


def test_importing_every_stage_module_loads_no_heavy_library():
    # run_stage.sh discovers the stages in core and each stage then runs in its own environment, so a stage module
    # may import its heavy libraries only inside functions (DESIGN.md); the unit tests also rely on it.
    heavy = ["torch", "transformers", "tensorflow", "stanza", "wtpsplit", "numpy", "pyarrow", "tokenizers",
             "safetensors", "sentencepiece", "minnt", "udapi", "wordfreq", "phonemizer", "opencc", "scipy"]
    code = ("import json, sys\nfrom intract_features import cli\ncli.discover()\n"
            f"print(json.dumps(sorted(m for m in {heavy!r} if m in sys.modules)))")
    done = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, text=True, check=True)
    assert json.loads(done.stdout) == []


def test_pipeline_keys_are_the_defaults_the_code_falls_back_to():
    # records.shard_of and keyed_hash default to these values, and text.keyed falls back to them, so a change to
    # pipeline.toml [keys] must reach every caller (the documents and qe_metricx stages pass it explicitly).
    keys = tomllib.loads((CONFIG / "pipeline.toml").read_text(encoding="utf-8"))["keys"]
    assert keyed.key_settings({"keys": keys}) == {"prefix": keyed.DEFAULT_PREFIX, "version": keyed.DEFAULT_VERSION}
    assert records.shard_of("S1", 7) == records.shard_of("S1", 7, prefix=keys["prefix"], version=keys["version"])
    assert records.keyed_hash("p", "S1") == records.keyed_hash("p", "S1", **keyed.key_settings({"keys": keys}))


def test_the_parse_artefacts_have_one_reader():
    # The CoNLL-U of parses_stanza and parses_udpipe is written and read by intract_features.parse alone.
    assert not (SRC / "intract_features" / "io" / "conllu.py").exists()
    readers = []
    for path in (SRC / "intract_features").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"\bnewdoc id\b", text) and "def read_conllu" in text:
            readers.append(path.relative_to(SRC).as_posix())
    # features.grammatical reads external CoNLL-U (UD gold, earlier benchmark parses) in gfeat's shape.
    assert sorted(readers) == ["intract_features/features/grammatical.py", "intract_features/parse/__init__.py"]


def test_the_ci_workflow_pins_every_action_by_commit():
    text = (FEATURES / "ci" / "features.yml").read_text(encoding="utf-8")
    uses = re.findall(r"uses:\s*(\S+)", text)
    assert uses, "the workflow uses no action"
    for action in uses:
        assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", action), f"{action} is not pinned to a full commit SHA"


def test_licences_name_every_pinned_model_and_resource():
    text = (FEATURES / "LICENCES.md").read_text(encoding="utf-8")
    for name in ("models", "resources"):
        entries = json.loads((CONFIG / f"{name}.lock.json").read_text(encoding="utf-8"))[name]
        for key, entry in entries.items():
            label = entry.get("repo") or key.split("@")[0]
            assert label in text or key in text, f"LICENCES.md does not name {key} ({name}.lock.json)"


def test_design_and_readme_name_the_fixed_stages_and_artefacts():
    design = (FEATURES / "DESIGN.md").read_text(encoding="utf-8")
    readme = (FEATURES / "README.md").read_text(encoding="utf-8")
    for name in STAGES:
        assert f"`{name}`" in readme, f"README.md does not list the stage {name}"
    for name in ARTEFACTS | {"segments"}:
        assert f"`{name}`" in design, f"DESIGN.md does not name the artefact {name}"
    for env in ENVIRONMENTS:
        assert f"`{env}`" in design and f"`{env}`" in readme
