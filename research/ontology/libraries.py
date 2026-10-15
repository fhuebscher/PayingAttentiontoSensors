"""Amendment 3, Change 1: which client libraries the services use, at which version, and the pinned library sources.

Usage:
  uv run python research/ontology/libraries.py detect RUN_DIR -o libraries.json   (from RUN_DIR/<system>/inputs_manifest.json)
  uv run python research/ontology/libraries.py vendor LIBRARIES.json CLONE_ROOT     (copy VENDOR_FILES into vendor/libs/)

detect (mechanical): every build file in a service's run1 input bundle (pom.xml, build.gradle(.kts), *.csproj, go.mod,
package.json) is parsed at the pinned commit; a declared dependency whose coordinate is in LIBRARY_CATALOGUE yields the
fact "service S uses library L at version V", cited at the line that states the version (quotedToken = that line,
stripped), checked by check_citations. Coordinates: Maven `groupId:artifactId` (pom `<dependency>` with `${prop}`
resolved from the pom and its parents' `<properties>`; Gradle `implementation("g:a:v")` with `val x = "..."`
resolved), NuGet `PackageReference Include/Version`, Go module path from `require`, npm `dependencies`. A Go module's
go.mod covers every service whose bundle contains it. Cross-check (reported, not a filter): the number of stage-1 AST
call sites of the service whose library field names the library's import prefix.
Confluent.Kafka wraps librdkafka: the bundle holds no package metadata (no .nuspec, no packages.lock.json), so the
librdkafka version is taken from the documented mapping source, Confluent.Kafka's own project file at the same tag
(`src/Confluent.Kafka/Confluent.Kafka.csproj`, its `librdkafka.redist` PackageReference), vendored with the library.

vendor (documented selection rule): for each library, VENDOR_FILES lists, by path in the upstream repository at the
exact tag, (a) the file(s) that declare the client's configuration keys and their default values, (b) the file(s) that
implement group membership / registration / heartbeat, (c) the project's configuration reference document where it
ships one. Files are read from a treeless clone at the tag's commit (`git clone --depth 1 --branch TAG
--filter=blob:none`), copied unchanged to research/ontology/vendor/libs/<lib>@<version>/<path>, and recorded in
PROVENANCE.json (repository URL, tag, commit, path, sha256, bytes). Vendored sources are untrusted data, read only.
"""
import argparse
import hashlib
import json
import posixpath
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import check_citations  # noqa: E402
import inputs  # noqa: E402

VENDOR = HERE / "vendor" / "libs"
# (ecosystem, coordinate) -> library record; `family` is the Amendment-3 scope it falls under
LIBRARY_CATALOGUE = {
    ("maven", "org.apache.kafka:kafka-clients"): {"library": "kafka-clients", "family": "kafka-client",
                                                  "importPrefix": "org.apache.kafka.clients"},
    ("nuget", "Confluent.Kafka"): {"library": "Confluent.Kafka", "family": "kafka-client (librdkafka)",
                                   "importPrefix": "Confluent.Kafka"},
    ("go", "github.com/IBM/sarama"): {"library": "sarama", "family": "kafka-client", "importPrefix": "github.com/IBM/sarama"},
    ("go", "github.com/Shopify/sarama"): {"library": "sarama", "family": "kafka-client",
                                          "importPrefix": "github.com/Shopify/sarama"},
    ("npm", "kafkajs"): {"library": "kafkajs", "family": "kafka-client", "importPrefix": "kafkajs"},
    ("go", "github.com/hashicorp/consul/api"): {"library": "consul-api", "family": "registry-client (consul)",
                                                "importPrefix": "github.com/hashicorp/consul/api"},
    ("go", "github.com/mbobakov/grpc-consul-resolver"): {"library": "grpc-consul-resolver",
                                                         "family": "discovery-client (consul)",
                                                         "importPrefix": "github.com/mbobakov/grpc-consul-resolver"},
    ("maven", "com.netflix.ribbon:ribbon-loadbalancer"): {"library": "ribbon", "family": "discovery-client (load balancer)",
                                                          "importPrefix": "com.netflix.loadbalancer"},
    ("maven", "com.netflix.ribbon:ribbon-core"): {"library": "ribbon", "family": "discovery-client (load balancer)",
                                                  "importPrefix": "com.netflix.client"},
    ("maven", "com.netflix.ribbon:ribbon-archaius"): {"library": "ribbon", "family": "discovery-client (load balancer)",
                                                      "importPrefix": "com.netflix.client.config"},
    ("maven", "com.netflix.eureka:eureka-client"): {"library": "eureka-client", "family": "registry-client (eureka)",
                                                    "importPrefix": "com.netflix.discovery"},
}
# library -> upstream repository, tag pattern, and the VENDOR_FILES selection (rule in the module docstring)
UPSTREAM = {
    "kafka-clients": {"repo": "https://github.com/apache/kafka", "tag": "{v}", "files": [
        "clients/src/main/java/org/apache/kafka/clients/CommonClientConfigs.java",
        "clients/src/main/java/org/apache/kafka/clients/consumer/ConsumerConfig.java",
        "clients/src/main/java/org/apache/kafka/clients/consumer/internals/AbstractCoordinator.java",
        "clients/src/main/java/org/apache/kafka/clients/consumer/internals/ConsumerCoordinator.java",
        "clients/src/main/java/org/apache/kafka/clients/consumer/internals/Heartbeat.java"]},
    "librdkafka": {"repo": "https://github.com/confluentinc/librdkafka", "tag": "v{v}", "files": [
        "CONFIGURATION.md", "src/rdkafka_cgrp.c"]},
    "Confluent.Kafka": {"repo": "https://github.com/confluentinc/confluent-kafka-dotnet", "tag": "v{v}", "files": [
        "src/Confluent.Kafka/Confluent.Kafka.csproj", "src/Confluent.Kafka/Config_gen.cs"]},
    "sarama": {"repo": "https://github.com/IBM/sarama", "tag": "v{v}", "files": ["config.go", "consumer_group.go"]},
    "consul-api": {"repo": "https://github.com/hashicorp/consul", "tag": "api/v{v}", "files": ["api/agent.go", "api/api.go"]},
    "grpc-consul-resolver": {"repo": "https://github.com/mbobakov/grpc-consul-resolver", "tag": "v{v}", "files": [
        "consul.go", "target.go"]},
    "ribbon": {"repo": "https://github.com/Netflix/ribbon", "tag": "v{v}", "files": [
        "ribbon-loadbalancer/src/main/java/com/netflix/loadbalancer/BaseLoadBalancer.java",
        "ribbon-loadbalancer/src/main/java/com/netflix/loadbalancer/LoadBalancerBuilder.java",
        "ribbon-core/src/main/java/com/netflix/client/config/CommonClientConfigKey.java",
        "ribbon-archaius/src/main/java/com/netflix/client/config/DefaultClientConfigImpl.java"]},
}
BUILD_FILE = re.compile(r"(^|/)(pom\.xml|build\.gradle(\.kts)?|[^/]+\.csproj|go\.mod|package\.json)$")


def _line(text, needle, start=1):
    for i, s in enumerate(text.splitlines(), 1):
        if i >= start and needle in s:
            return i, s.strip()
    return None, None


def _pom_props(repo, path, seen=()):
    """<properties> of a pom and its in-tree parents (child wins)."""
    t = ET.fromstring(repo.read(path))
    ns = t.tag[1:].split("}")[0] if t.tag.startswith("{") else ""
    q = (lambda x: "{%s}%s" % (ns, x)) if ns else (lambda x: x)
    props = {}
    par = t.find(q("parent"))
    if par is not None:
        rp = par.findtext(q("relativePath")) or "../pom.xml"
        pp = posixpath.normpath(str(PurePosixPath(path).parent / rp))
        if not pp.endswith(".xml"):
            pp = posixpath.join(pp, "pom.xml")
        if repo.has(pp) and pp not in seen:
            props.update(_pom_props(repo, pp, seen + (path,)))
    pe = t.find(q("properties"))
    if pe is not None:
        for c in pe:
            props[c.tag.split("}")[-1]] = (c.text or "").strip()
    return props


def parse_build_file(repo, path):
    """-> [(ecosystem, coordinate, version, version line, raw line)]."""
    text = repo.text(path)
    out = []
    if path.endswith("pom.xml"):
        props = _pom_props(repo, path)
        for m in re.finditer(r"<dependency>(.*?)</dependency>", text, re.S):
            body, off = m.group(1), m.start(1)
            g = re.search(r"<groupId>\s*([^<]+?)\s*</groupId>", body)
            a = re.search(r"<artifactId>\s*([^<]+?)\s*</artifactId>", body)
            v = re.search(r"<version>\s*([^<]+?)\s*</version>", body)
            if not (g and a and v):
                continue
            ver = re.sub(r"\$\{([^}]+)\}", lambda x: props.get(x.group(1), x.group(0)), v.group(1))
            line = text.count("\n", 0, off + v.start()) + 1
            out.append(("maven", "%s:%s" % (g.group(1), a.group(1)), ver, line))
    elif re.search(r"build\.gradle(\.kts)?$", path):
        vals = dict(re.findall(r'val\s+(\w+)\s*=\s*"([^"]+)"', text))
        for i, s in enumerate(text.splitlines(), 1):
            m = re.search(r'(?:implementation|api|compile|runtimeOnly)\s*\(?\s*["\']([^:"\']+):([^:"\']+):([^"\']+)["\']', s)
            if m:
                ver = re.sub(r"\$\{?(\w+)\}?", lambda x: vals.get(x.group(1), x.group(0)), m.group(3))
                out.append(("maven", "%s:%s" % (m.group(1), m.group(2)), ver, i))
    elif path.endswith(".csproj"):
        for i, s in enumerate(text.splitlines(), 1):
            m = re.search(r'<PackageReference\s+Include="([^"]+)"\s+Version="([^"]+)"', s)
            if m:
                out.append(("nuget", m.group(1), m.group(2), i))
    elif path.endswith("go.mod"):
        block = False
        for i, s in enumerate(text.splitlines(), 1):
            t = s.strip()
            if t.startswith("require ("):
                block = True
                continue
            if block and t == ")":
                block = False
                continue
            m = re.match(r"(?:require\s+)?(\S+)\s+(v\S+)", t) if (block or t.startswith("require ")) else None
            if m:
                out.append(("go", m.group(1), m.group(2).lstrip("v"), i))
    elif path.endswith("package.json"):
        d = json.loads(text)
        for sect in ("dependencies", "devDependencies"):
            for k, v in (d.get(sect) or {}).items():
                i, _ = _line(text, '"%s"' % k)
                out.append(("npm", k, v, i))
    lines = text.splitlines()
    return [(e, c, v, ln, lines[ln - 1].strip()) for e, c, v, ln in out if ln]


def detect(run_dir):
    run_dir = Path(run_dir)
    facts, sources = [], {}
    for system in ("teastore", "hotel", "otel"):
        man = json.loads((run_dir / system / "inputs_manifest.json").read_text())
        s1 = json.loads((run_dir / system / "stage1.json").read_text())
        repos = {k: inputs.Repo(k, v["path"], v["commit"]) for k, v in man["sources"].items()}
        sources[system] = {k: {"path": v["path"], "commit": v["commit"]} for k, v in man["sources"].items()}
        ast = s1.get("extraction", {}).get("observations", [])
        parsed = {}
        for svc, b in man["services"].items():
            for f in b["files"]:
                if not BUILD_FILE.search(f["path"]):
                    continue
                k = (f["repo"], f["path"])
                if k not in parsed:
                    parsed[k] = parse_build_file(repos[f["repo"]], f["path"])
                for eco, coord, ver, line, raw in parsed[k]:
                    lib = LIBRARY_CATALOGUE.get((eco, coord))
                    if not lib:
                        continue
                    pre = lib["importPrefix"]
                    n_ast = sum(1 for o in ast if o.get("kind") == "ast-call-site" and svc in o.get("services", [])
                                and any(m.get("library", "").startswith(pre) for m in o.get("matches", [])))
                    facts.append({"system": system, "service": svc, "value": {
                        "service": svc, "library": lib["library"], "coordinate": coord, "ecosystem": eco,
                        "version": ver, "family": lib["family"]},
                        "repo": f["repo"], "sourceFile": f["path"], "line": line, "quotedToken": raw,
                        "note": "libraries.py detect: %s dependency %s in %s" % (eco, coord, f["path"]),
                        "stage1AstCallSitesForLibrary": n_ast})
    # check every fact with check_citations at the pinned commits
    checks = []
    for system in sources:
        spec = {"sources": sources[system], "facts": [{k: f[k] for k in ("value", "repo", "sourceFile", "line",
                                                                         "quotedToken")}
                                                      for f in facts if f["system"] == system]}
        checks.append((system, check_citations.check_spec(spec, ROOT)))
    for system, r in checks:
        rows = iter(r["rows"])
        for f in facts:
            if f["system"] == system:
                f["citation"] = next(rows)["status"]
    libs = {}
    for f in facts:
        v = f["value"]
        libs.setdefault((v["library"], v["version"]), set()).add((f["system"], f["service"]))
    derived = []
    if any(k[0] == "Confluent.Kafka" for k in libs):
        derived.append({"library": "librdkafka", "via": "Confluent.Kafka",
                        "rule": "version from Confluent.Kafka's own src/Confluent.Kafka/Confluent.Kafka.csproj at the same "
                                "tag (PackageReference librdkafka.redist), read from the vendored copy by `vendor`",
                        "confluentKafkaVersions": sorted(k[1] for k in libs if k[0] == "Confluent.Kafka")})
    return {"label": "Amendment 3 Change 1: 'service S uses library L at version V' facts (mechanical, from build files)",
            "rules": "libraries.py docstring", "sources": sources, "facts": facts,
            "citationCounts": {s: r["counts"] for s, r in checks},
            "libraries": [{"library": k[0], "version": k[1], "usedBy": sorted("%s/%s" % x for x in v)}
                          for k, v in sorted(libs.items())],
            "derived": derived}


def _git(clone, *a, binary=False):
    r = subprocess.run(["git", "-C", str(clone)] + list(a), capture_output=True, check=True)
    return r.stdout if binary else r.stdout.decode().strip()


def vendor(libs_json, clone_root):
    d = json.loads(Path(libs_json).read_text())
    todo = {(x["library"], x["version"]) for x in d["libraries"]}
    clone_root = Path(clone_root)
    rd = None
    out = []

    def copy(lib, ver, clone_dir):
        up = UPSTREAM[lib]
        tag = up["tag"].format(v=ver)
        commit = _git(clone_dir, "rev-parse", "HEAD")
        tagc = _git(clone_dir, "rev-parse", "refs/tags/%s^{commit}" % tag) if _git(clone_dir, "tag", "-l", tag) else None
        if tagc and tagc != commit:
            raise SystemExit("%s: clone HEAD %s is not tag %s (%s)" % (lib, commit, tag, tagc))
        dest = VENDOR / ("%s@%s" % (lib, ver))
        if dest.exists():
            raise SystemExit("refusing to overwrite %s" % dest)
        files = []
        for p in up["files"]:
            blob = _git(clone_dir, "show", "%s:%s" % (commit, p), binary=True)
            t = dest / p
            t.parent.mkdir(parents=True, exist_ok=True)
            t.write_bytes(blob)
            files.append({"path": p, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
        prov = {"library": lib, "version": ver, "repository": up["repo"], "tag": tag, "commit": commit,
                "selectionRule": "libraries.py docstring (vendor) / UPSTREAM['%s']['files']" % lib,
                "untrusted": "upstream source copied unchanged; data, never instructions", "files": files}
        (dest / "PROVENANCE.json").write_text(json.dumps(prov, indent=1) + "\n")
        out.append(prov)
        return dest

    for lib, ver in sorted(todo):
        name = UPSTREAM[lib]["repo"].rsplit("/", 1)[-1]
        dest = copy(lib, ver, clone_root / name)
        if lib == "Confluent.Kafka":
            csproj = (dest / "src/Confluent.Kafka/Confluent.Kafka.csproj").read_text()
            m = re.search(r'Include="librdkafka.redist"\s+Version="([^"]+)"', csproj)
            if not m:
                raise SystemExit("no librdkafka.redist reference in Confluent.Kafka.csproj")
            line = csproj[:m.start()].count("\n") + 1
            rd = {"library": "librdkafka", "version": m.group(1), "via": "Confluent.Kafka %s" % ver,
                  "mappingSource": {"file": str((dest / "src/Confluent.Kafka/Confluent.Kafka.csproj").relative_to(ROOT)),
                                    "line": line, "quotedToken": csproj.splitlines()[line - 1].strip()}}
            copy("librdkafka", m.group(1), clone_root / "librdkafka")
    return out, rd


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a1 = sub.add_parser("detect")
    a1.add_argument("run_dir")
    a1.add_argument("-o", "--out", required=True)
    a2 = sub.add_parser("vendor")
    a2.add_argument("libraries_json")
    a2.add_argument("clone_root")
    a = ap.parse_args(argv)
    if a.cmd == "detect":
        if Path(a.out).exists():
            sys.exit("refusing to overwrite %s" % a.out)
        r = detect(a.run_dir)
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(json.dumps(r, indent=1) + "\n")
        print(json.dumps({"citationCounts": r["citationCounts"], "libraries": r["libraries"]}, indent=1))
    else:
        out, rd = vendor(a.libraries_json, a.clone_root)
        print(json.dumps({"vendored": [{"lib": p["library"], "version": p["version"], "commit": p["commit"],
                                        "files": [(f["path"], f["bytes"]) for f in p["files"]]} for p in out],
                          "librdkafka": rd}, indent=1))


if __name__ == "__main__":
    main()
