"""The harness tree at its pinned commit, for the fixture generators: `git archive <commit>` of the harness worktree
into a scratch directory (the worktree itself is never written to, and its HEAD may have moved on), with each upstream
submodule linked to the worktree's checkout when that checkout is at the commit's gitlink (else left empty)."""
import io
import subprocess
import tarfile
from pathlib import Path


def pinned_tree(worktree, commit, scratch):
    worktree, scratch = Path(worktree).resolve(), Path(scratch).resolve()
    full = subprocess.run(["git", "-C", str(worktree), "rev-parse", commit + "^{commit}"], capture_output=True,
                          text=True, check=True).stdout.strip()
    dest = scratch / ("harness-" + full[:12])
    if not dest.exists():
        data = subprocess.run(["git", "-C", str(worktree), "archive", "--format=tar", full], capture_output=True,
                              check=True).stdout
        dest.mkdir(parents=True)
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(dest, filter="data")
        tree = subprocess.run(["git", "-C", str(worktree), "ls-tree", full, "upstream/"], capture_output=True,
                              text=True, check=True).stdout
        for line in tree.splitlines():
            meta, path = line.split("\t", 1)
            mode, kind, sha = meta.split()
            if kind != "commit":
                continue
            sub = worktree / path
            head = subprocess.run(["git", "-C", str(sub), "rev-parse", "HEAD"], capture_output=True, text=True)
            target = dest / path
            if head.returncode == 0 and head.stdout.strip() == sha:
                if target.is_dir() and not any(target.iterdir()):
                    target.rmdir()
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(sub)
    return dest, full
