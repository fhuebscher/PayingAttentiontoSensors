"""Check every cited fact of an extracted SUT spec against its source at the pinned commit.

Usage:  uv run python research/ontology/check_citations.py SPEC.json [--root DIR] [--json]

For each fact with a sourceFile: read `git -C <sources[repo].path> show <commit>:<sourceFile>` (the pinned commit, not
the working tree) and assert quotedToken occurs on the cited line or within +-TOLERANCE lines. A documented-default fact
(sourceUrl, no file) cannot be checked offline and is reported `unchecked-default`, never `ok`.
Exit status: 0 iff no fact is `fail`. Relative source paths resolve against --root (default: the observability-placement
checkout, i.e. two levels above this file).
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOLERANCE = 2


def iter_facts(obj, path="$"):
    """Yield (json path, fact) for every fact object (a dict with 'value' and provenance) in the spec."""
    if isinstance(obj, dict):
        if "value" in obj and ("sourceFile" in obj or "sourceUrl" in obj):
            yield path, obj
            return
        for k in sorted(obj):
            if k in ("sources", "extraction"):
                continue
            yield from iter_facts(obj[k], "%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, x in enumerate(obj):
            yield from iter_facts(x, "%s[%d]" % (path, i))


class SourceReader:
    def __init__(self, sources, root):
        self.sources, self.root, self.cache = sources, Path(root), {}

    def lines(self, repo, file):
        """-> (lines or None, error or None) of file at the repo's pinned commit."""
        k = (repo, file)
        if k not in self.cache:
            src = self.sources.get(repo)
            if src is None:
                self.cache[k] = (None, "unknown repo key %r" % repo)
            else:
                wd = Path(src["path"])
                wd = wd if wd.is_absolute() else self.root / wd
                ok = subprocess.run(["git", "-C", str(wd), "cat-file", "-e", src["commit"] + "^{commit}"],
                                    capture_output=True)
                if ok.returncode != 0:
                    self.cache[k] = (None, "commit %s not found in %s" % (src["commit"], wd))
                else:
                    r = subprocess.run(["git", "-C", str(wd), "show", "%s:%s" % (src["commit"], file)],
                                       capture_output=True)
                    self.cache[k] = ((r.stdout.decode("utf-8", "replace").splitlines(), None) if r.returncode == 0
                                     else (None, "file %s absent at %s" % (file, src["commit"][:12])))
        return self.cache[k]


def check_fact(reader, f):
    if "sourceFile" not in f:
        return {"status": "unchecked-default", "detail": f.get("sourceUrl")}
    lines, err = reader.lines(f["repo"], f["sourceFile"])
    if err:
        return {"status": "fail", "detail": err}
    n, tok = f["line"], f["quotedToken"]
    if n > len(lines):
        return {"status": "fail", "detail": "line %d beyond end of file (%d lines)" % (n, len(lines))}
    for d in sorted(range(-TOLERANCE, TOLERANCE + 1), key=abs):
        i = n + d
        if 1 <= i <= len(lines) and tok in lines[i - 1]:
            return {"status": "ok", "matchedLine": i, "offset": d}
    found = [i + 1 for i, s in enumerate(lines) if tok in s]
    return {"status": "fail", "detail": "token not within +-%d of line %d" % (TOLERANCE, n),
            "tokenFoundAt": found[:10]}


def check_spec(spec, root=ROOT):
    reader = SourceReader(spec.get("sources", {}), root)
    rows = []
    for path, f in iter_facts(spec):
        r = check_fact(reader, f)
        r.update({"path": path, "repo": f.get("repo"), "sourceFile": f.get("sourceFile"), "line": f.get("line"),
                  "quotedToken": f.get("quotedToken")})
        rows.append(r)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return {"facts": len(rows), "counts": counts, "ok": counts.get("fail", 0) == 0, "rows": rows}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("spec")
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = check_spec(json.loads(Path(a.spec).read_text()), a.root)
    if a.json:
        print(json.dumps(res, indent=1))
    else:
        for r in res["rows"]:
            if r["status"] != "ok":
                print("%-18s %s  %s:%s  %r  %s" % (r["status"], r["path"], r["sourceFile"], r["line"],
                                                    r["quotedToken"], r.get("detail", "")))
        print("facts %d: %s" % (res["facts"], json.dumps(res["counts"], sort_keys=True)))
    sys.exit(0 if res["ok"] else 1)


if __name__ == "__main__":
    main()
