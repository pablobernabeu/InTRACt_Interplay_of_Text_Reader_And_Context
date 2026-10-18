"""Refuse a change that edits a frozen file or adds a confidential or oversized one.

    python tools/guard.py --staged            # what is staged for the next commit
    python tools/guard.py --range BASE HEAD   # what a push or pull request changes
    python tools/guard.py --tree [REV]        # every file tracked at REV (default HEAD)

Run from anywhere inside the repository. The pre-commit hook in .githooks/ runs the
first form, and the Guard workflow runs the other two on every push and pull request,
the range form once per pushed commit, so a file added and removed again within one
push is still caught. --confidential-from REV takes the confidential list from REV
instead of the state being checked, so commits made before a pattern was added are
held to it too.

Frozen files (tools/frozen.txt) are outputs that must stay as they were issued: the
printed poster and the files it was built from, the archived protocol drafts, the
count-script versions supplied to the data controller and the frozen prior rules.
A change may add a file under a frozen pattern, which is how a new draft is
archived, but may not modify, delete or rename one. To change a frozen file on
purpose, remove its pattern from tools/frozen.txt in the same commit, so the
decision shows in the diff. The list is read from the state being checked.

Confidential patterns (tools/confidential.txt) name material that must never enter
this public repository: the data controller's deliveries, the count script's
outputs, publisher PDFs and credentials. A staged or pushed file matching one fails,
and so does any file larger than MAX_BYTES.

In both lists, one pattern per line in fnmatch syntax, matched against the path from
the repository root, where * also matches across folders. Text after # is a comment.

Exit status 1 on any violation, 0 otherwise. Standard library only.
"""
import argparse
import fnmatch
import os
import subprocess
import sys

MAX_BYTES = 10 * 1024 * 1024  # GitHub warns at 50 MB; nothing here should near 10 MB
FROZEN = "tools/frozen.txt"
CONFIDENTIAL = "tools/confidential.txt"


def git(*args, check=True):
    p = subprocess.run(["git", *args], capture_output=True)
    if check and p.returncode != 0:
        sys.exit("git " + " ".join(args) + " failed: " + p.stderr.decode(errors="replace"))
    return p


def patterns(spec):
    """The patterns in a list file, read from a git object spec such as HEAD:tools/x."""
    p = git("show", spec, check=False)
    if p.returncode != 0:
        return []
    out = []
    for line in p.stdout.decode("utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def matches(path, pats):
    return [p for p in pats if fnmatch.fnmatchcase(path, p)]


def changes(diff_args):
    """(status, path) pairs from git diff --name-status, renames split in two."""
    raw = git("diff", "--name-status", "-z", "--no-renames", *diff_args).stdout.decode("utf-8")
    fields = [f for f in raw.split("\0") if f]
    return list(zip(fields[0::2], fields[1::2]))


def blob_size(spec):
    p = git("cat-file", "-s", spec, check=False)
    return int(p.stdout) if p.returncode == 0 else 0


def check(pairs, frozen, confidential, size_of):
    problems = []
    for status, path in pairs:
        if status[0] in "MDT":
            for p in matches(path, frozen):
                verb = {"M": "modifies", "D": "deletes or moves", "T": "retypes"}[status[0]]
                problems.append(f"FROZEN        {path}: the change {verb} it (pattern {p})")
        if status[0] in "AMT":
            for p in matches(path, confidential):
                problems.append(f"CONFIDENTIAL  {path}: matches {p}")
            size = size_of(path)
            if size > MAX_BYTES:
                problems.append(f"TOO LARGE     {path}: {size / 2**20:.1f} MB, the limit is "
                                f"{MAX_BYTES / 2**20:.0f} MB")
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--staged", action="store_true")
    mode.add_argument("--range", nargs=2, metavar=("BASE", "HEAD"))
    mode.add_argument("--tree", nargs="?", const="HEAD", metavar="REV")
    ap.add_argument("--confidential-from", metavar="REV")
    args = ap.parse_args()
    os.chdir(git("rev-parse", "--show-toplevel").stdout.decode().strip())

    def confidential(state):
        return patterns(f"{args.confidential_from or state}:{CONFIDENTIAL}")

    if args.staged:
        what = "the staged changes"
        pairs = changes(["--cached"])
        problems = check(pairs, patterns(":" + FROZEN), confidential(""),
                         lambda p: blob_size(":" + p))
    elif args.range:
        base, head = args.range
        what = f"{base[:10]}..{head[:10]}"
        pairs = changes([base, head])
        problems = check(pairs, patterns(f"{head}:{FROZEN}"), confidential(head),
                         lambda p: blob_size(f"{head}:{p}"))
    else:
        rev = args.tree
        what = f"every file tracked at {rev}"
        files = git("ls-tree", "-r", "-z", "--name-only", rev).stdout.decode("utf-8")
        pairs = [("A", f) for f in files.split("\0") if f]
        problems = check(pairs, [], confidential(rev), lambda p: blob_size(f"{rev}:{p}"))

    for line in problems:
        print(line)
    print(f"guard: {len(pairs)} paths in {what}, {len(problems)} problem(s)")
    if problems and args.staged:
        print("A frozen file is changed on purpose by removing its pattern from "
              f"{FROZEN} in the same commit.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
