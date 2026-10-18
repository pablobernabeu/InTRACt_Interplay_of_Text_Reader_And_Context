"""Run both test scripts and compare their reports with the recorded ones.

    python check_expected.py            # exit 1 if any scenario's report changed
    python check_expected.py --update   # rewrite expected/ from this run

The two test scripts describe what each count-script version does with each
synthetic input but assert nothing, so a changed outcome would pass unnoticed. This
runs them with the interpreter running this file and drops the timing fields (any
key ending in " seconds"). It then compares every scenario with
expected/<script>.json, recorded on 18 October 2026 from both versions as supplied
to the data controller.
The scenarios that need the real sample are skipped, as with no arguments.

Standard library only, Python 3.8 or later.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ["test_malformed_inputs", "test_revised_version"]


def strip_timings(x):
    if isinstance(x, dict):
        return {k: strip_timings(v) for k, v in x.items() if not k.endswith(" seconds")}
    if isinstance(x, list):
        return [strip_timings(v) for v in x]
    return x


def main():
    update = "--update" in sys.argv[1:]
    failed = False
    for name in SCRIPTS:
        p = subprocess.run([sys.executable, os.path.join(HERE, name + ".py")], cwd=HERE,
                           capture_output=True, text=True, encoding="utf-8")
        if p.returncode != 0:
            print(f"{name}: exited {p.returncode}\n{p.stderr}")
            failed = True
            continue
        got = strip_timings(json.loads(p.stdout))
        path = os.path.join(HERE, "expected", name + ".json")
        if update:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as fh:
                json.dump(got, fh, indent=1, ensure_ascii=False)
                fh.write("\n")
            print(f"{name}: recorded {len(got)} scenarios")
            continue
        with open(path, encoding="utf-8") as fh:
            want = json.load(fh)
        changed = [k for k in sorted(set(want) | set(got)) if want.get(k) != got.get(k)]
        for k in changed:
            print(f"{name}: scenario changed: {k}")
            print("  expected: " + json.dumps(want.get(k), ensure_ascii=False))
            print("  got:      " + json.dumps(got.get(k), ensure_ascii=False))
        print(f"{name}: {len(got)} scenarios, {len(changed)} changed")
        failed = failed or bool(changed)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
