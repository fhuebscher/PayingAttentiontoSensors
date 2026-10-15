#!/usr/bin/env python3
"""Materialize the exact pinned Hotel Reservation Git object into a clean tree."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "modules" / "hotel-reservation"
UPSTREAM = ROOT / "upstream" / "deathstarbench"
SOURCE_PACKAGE = UPSTREAM / ".obsplacement-source-package.json"
SUBDIRECTORY = "hotelReservation"
DEFAULT_OUT = ROOT / ".local" / "hotel-reservation"
SENTINEL = ".obsplacement-materialized"


def command(argv: list[str]) -> str:
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {argv}\n{result.stderr}")
    return result.stdout.strip()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"expected exactly one {label} anchor, found {count}")
    return text.replace(old, new, 1)


def isolated_compose(text: str) -> str:
    """Generate a smoke-only Compose file without global names/ports."""
    text = replace_once(text, "    container_name: 'hotel_reserv_review'\n", "",
                        "review container_name")
    text = replace_once(text, "    container_name: 'hotel_reserv_attractions'\n", "",
                        "attractions container_name")
    text = replace_once(text, "    container_name: 'hotel_reserv_review_mmc'\n", "",
                        "review memcached container_name")
    text = replace_once(text, '''    ports:
      - "8300:8300"
      - "8400:8400"
      - "8500:8500"
      - "8600:53/udp"
''', "", "Consul published ports")
    text = replace_once(text, '''    ports:
      - "5000:5000"
''', '''    ports:
      - "127.0.0.1:${HR_FRONTEND_PORT:?set HR_FRONTEND_PORT}:5000"
''', "frontend published port")
    text = replace_once(text, '''    ports:
      - "14269"
      - "5778:5778"
      - "14268:14268"
      - "14267"
      - "16686:16686"
      - "5775:5775/udp"
      - "6831:6831/udp"
      - "6832:6832/udp"
''', '''    ports:
      - "127.0.0.1:${HR_JAEGER_QUERY_PORT:?set HR_JAEGER_QUERY_PORT}:16686"
''', "Jaeger published ports")
    return text


def pinned_commit(lock: Path = MODULE / "source.lock") -> str:
    match = re.search(r"^commit:\s*([0-9a-f]{40})$", lock.read_text(), re.MULTILINE)
    if not match:
        raise RuntimeError(f"exact 40-character commit missing from {lock}")
    return match.group(1)


def verify_source() -> dict:
    expected = pinned_commit()
    if SOURCE_PACKAGE.is_file() and not SOURCE_PACKAGE.is_symlink():
        try:
            receipt = json.loads(SOURCE_PACKAGE.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid installed source package receipt: {exc}") from exc
        body = {key: value for key, value in receipt.items() if key != "canonicalSha256"}
        canonical = json.dumps(body, allow_nan=False, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":")).encode()
        if (
            set(receipt) != {
                "schemaVersion", "kind", "upstreamCommit", "upstreamTree",
                "subdirectory", "entries", "canonicalSha256",
            }
            or receipt["schemaVersion"] != 1
            or receipt["kind"] != "hotel-source-package-v1"
            or receipt["upstreamCommit"] != expected
            or receipt["subdirectory"] != SUBDIRECTORY
            or receipt["canonicalSha256"] != hashlib.sha256(canonical).hexdigest()
            or not isinstance(receipt["entries"], list)
        ):
            raise RuntimeError("installed source package identity differs")
        source_root = UPSTREAM / SUBDIRECTORY
        observed = []
        for path in sorted(source_root.rglob("*")):
            if path.is_dir():
                continue
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("installed source package contains an unsupported file")
            payload = path.read_bytes()
            observed.append({
                "path": path.relative_to(source_root).as_posix(), "kind": "file",
                "mode": stat.S_IMODE(path.stat().st_mode), "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            })
        if observed != receipt["entries"]:
            raise RuntimeError("installed Hotel source bytes do not replay")
        return {
            "upstreamCommit": expected, "upstreamSubdirectory": SUBDIRECTORY,
            "upstreamTree": receipt["upstreamTree"], "sourceCheckoutClean": True,
            "sourceQualification": "exact-installed-package",
            "sourcePackageCanonicalSha256": receipt["canonicalSha256"],
        }
    actual = command(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"])
    if actual != expected:
        raise RuntimeError(f"pinned checkout mismatch: expected {expected}, found {actual}")
    dirty = command(["git", "-C", str(UPSTREAM), "status", "--porcelain", "--", SUBDIRECTORY])
    if dirty:
        raise RuntimeError(f"pinned Hotel Reservation source is dirty:\n{dirty}")
    tree = command(["git", "-C", str(UPSTREAM), "rev-parse", f"{expected}:{SUBDIRECTORY}"])
    return {"upstreamCommit": expected, "upstreamSubdirectory": SUBDIRECTORY,
            "upstreamTree": tree, "sourceCheckoutClean": True}


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.name not in {SENTINEL, ".source.sha256"}:
            relative = path.relative_to(root).as_posix().encode()
            payload = path.read_bytes()
            digest.update(len(relative).to_bytes(8, "big"))
            digest.update(relative)
            digest.update(stat.S_IMODE(path.stat().st_mode).to_bytes(4, "big"))
            digest.update(len(payload).to_bytes(8, "big"))
            digest.update(payload)
    return digest.hexdigest()


def safe_target(path: Path) -> Path:
    target = path.resolve()
    forbidden = {Path("/"), Path.home().resolve(), ROOT.resolve(), UPSTREAM.resolve(), MODULE.resolve()}
    if (target in forbidden or target in ROOT.resolve().parents or
            target.is_relative_to(UPSTREAM.resolve()) or target.is_relative_to(MODULE.resolve())):
        raise RuntimeError(f"refusing unsafe materialization target: {target}")
    return target


def materialize(out: Path) -> dict:
    proof = verify_source()
    target = safe_target(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not (target / SENTINEL).is_file():
        raise RuntimeError(f"refusing to replace non-materialized directory: {target}")

    temporary = Path(tempfile.mkdtemp(prefix=".hotel-reservation-", dir=target.parent))
    try:
        if proof.get("sourceQualification") == "exact-installed-package":
            shutil.rmtree(temporary)
            shutil.copytree(UPSTREAM / SUBDIRECTORY, temporary, symlinks=False)
        else:
            archive = subprocess.run(
                ["git", "-C", str(UPSTREAM), "archive", "--format=tar",
                 f"{proof['upstreamCommit']}:{SUBDIRECTORY}"],
                capture_output=True, check=False,
            )
            if archive.returncode:
                raise RuntimeError(
                    f"git archive failed ({archive.returncode}): "
                    f"{archive.stderr.decode(errors='replace')}"
                )
            with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as bundle:
                bundle.extractall(temporary, filter="data")
        proof["upstreamContentSha256"] = tree_sha256(temporary)
        original_compose = temporary / "docker-compose.yml"
        generated_compose = temporary / "docker-compose.obsplacement.yml"
        generated_compose.write_text(isolated_compose(original_compose.read_text()))
        proof["transformations"] = [
            "remove-global-container-names",
            "remove-consul-host-ports",
            "bind-frontend-and-jaeger-query-to-configured-loopback-ports",
        ]
        proof["generatedComposeSha256"] = hashlib.sha256(generated_compose.read_bytes()).hexdigest()
        proof["materializedSourceSha256"] = tree_sha256(temporary)
        (temporary / SENTINEL).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
        (temporary / ".source.sha256").write_text(proof["materializedSourceSha256"] + "\n")
        if target.exists():
            shutil.rmtree(target)
        temporary.rename(target)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    proof = materialize(args.out)
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
