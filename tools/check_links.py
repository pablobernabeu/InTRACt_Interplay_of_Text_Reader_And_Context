"""Check that every relative link in the repository's Markdown files resolves.

    python tools/check_links.py

Run from anywhere inside the repository. Reads every tracked .md file, collects the
targets of its Markdown links, images, reference definitions and HTML href/src
attributes, and checks each relative target against the tracked files. Web links,
mail links and in-page anchors are not checked, and neither is anything inside a
code block or a code span. A target with a #fragment is checked for the file alone.

Targets are resolved against tracked files rather than the disk, so a link that
works only because of an untracked local file (a delivery kept outside version
control, for example) still fails, as it would for a reader on GitHub. A leading
slash means the repository root, as on GitHub.

Exit status 1 if any link is broken, 0 otherwise. Standard library only.
"""
import os
import posixpath
import re
import subprocess
import sys
from urllib.parse import unquote

INLINE = re.compile(r"!?\[(?:[^\[\]]|\[[^\]]*\])*\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+\"[^\"]*\")?\s*\)")
REFDEF = re.compile(r"^ {0,3}\[[^\]]+\]:\s*(<[^>]*>|\S+)", re.M)
HTML_ATTR = re.compile(r"<(?:a|img|source)\b[^>]*?\b(?:href|src)=\"([^\"]+)\"", re.I)
FENCE = re.compile(r"^ {0,3}(```|~~~).*?^ {0,3}\1[^\n]*$", re.M | re.S)
CODE_SPAN = re.compile(r"(`+)(?:(?!\1).)+?\1", re.S)
EXTERNAL = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#|//)", re.I)


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          encoding="utf-8", check=True).stdout


def main():
    root = git("rev-parse", "--show-toplevel").strip()
    os.chdir(root)
    files = git("ls-files", "-z").split("\0")
    tracked = {f for f in files if f}
    dirs = {posixpath.dirname(f) for f in tracked}
    while True:
        parents = {posixpath.dirname(d) for d in dirs if d} - dirs
        if not parents:
            break
        dirs |= parents

    broken = []
    checked = 0
    for md in sorted(f for f in tracked if f.lower().endswith(".md")):
        with open(md, encoding="utf-8") as fh:
            text = fh.read()
        # Blank the code first, keeping its newlines so line numbers stay right.
        text = FENCE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        text = CODE_SPAN.sub(lambda m: "\n" * m.group(0).count("\n"), text)
        found = []
        for rx in (INLINE, REFDEF, HTML_ATTR):
            for m in rx.finditer(text):
                found.append((m.start(1), m.group(1)))
        for pos, target in sorted(found):
            target = target.strip("<>").strip()
            if not target or EXTERNAL.match(target):
                continue
            path = unquote(target.split("#", 1)[0].split("?", 1)[0])
            if not path:
                continue
            if path.startswith("/"):
                resolved = posixpath.normpath(path.lstrip("/"))
            else:
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(md), path))
            resolved = resolved.rstrip("/")
            if resolved in ("", "."):
                continue
            checked += 1
            if resolved.startswith("..") or (resolved not in tracked and resolved not in dirs):
                line = text.count("\n", 0, pos) + 1
                broken.append(f"{md}:{line}: {target}")

    for b in broken:
        print("BROKEN  " + b)
    n_md = sum(1 for f in tracked if f.lower().endswith(".md"))
    print(f"{checked} relative links checked in {n_md} Markdown files, {len(broken)} broken")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
