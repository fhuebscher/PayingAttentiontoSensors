"""Stage 1 of the extraction procedure: the deterministic layer (no model). EXTRACTION_PROTOCOL.md, "Stage 1".

Usage:  uv run python research/ontology/extract_stage1.py SYSTEM [--services a,b] [-o stage1.json]

Output: one spec in research/ontology/extraction.schema.json. Two kinds of content:
* schema facts (checked by check_citations.py, merged in stage 3): the architecture, the host, each service's name,
  role, container and replica count, and candidate sync edges from environment variables whose value names another
  compose service;
* `extraction.observations` (cited the same way, checked by the same checker through check_observations(), never
  converted to Turtle): compose `depends_on`, healthchecks, build/image, environment entries that name nothing
  resolvable, and the AST call sites of client libraries with the configuration literals passed to them. They are
  stage-2 input (the extractors receive stage1.json), not ontology facts.

Engineering defaults (recorded 2026-10-14):
D1  Role: a service whose image is built from the pinned tree is `microservice` unless the last `FROM` of its
    Dockerfile is a third-party image in ROLE_BY_IMAGE; an image-only service takes ROLE_BY_IMAGE of its image
    repository, else `other`. The fact cites the line that names the image (compose `image:` or Dockerfile `FROM`).
D2  Container: `container_name` if set (cited), else the compose service key line with the note that Compose names
    the container <project>-<service>-<n>; the value is then the service name.
D3  Replicas: `deploy.replicas` or `scale` if set (cited); else a documented default 1 (Compose specification).
D4  Env -> sync edge: the value (after .env interpolation; a bare `- NAME` entry takes NAME from .env) is split on
    commas; each part loses a `scheme://` prefix and userinfo, and its host (up to `:` or `/`) is looked up in the
    compose alias table (service keys, container_name, hostname, network aliases; a hostname shared by several
    services names none). A hit other than the service itself is a candidate edge caller=service, callee=hit.
    Citation: the line on which the callee's name literally appears (the compose line, or the .env line that
    supplied it); the note names the other line.
D5  AST layer: tree-sitter (tree-sitter-language-pack, grammar libraries hashed into the run record) over every bundle
    file in a supported language. A call/construction is a hit when (a) its root identifier is bound by an import of a
    CATALOGUE module and its final name is in that entry's `calls` (or the entry has any=True), or (b) the file imports
    the module and the callee root / constructed type is in `types`, or (c) the file imports the module and the final
    method name is in `methods` (receiver type unknown: file-scoped by the import). Go and Java add one level of
    in-tree propagation: a call into an in-tree package/class whose own files have hits is a `via-wrapper` hit with
    those categories; a Go call `New<X>Client` on an in-tree package holding generated gRPC stubs is a
    `generated-stub` gRPC hit. Literal arguments (strings, numbers) are reported with their own line; an identifier
    argument bound in the same file to a literal (const/var/field) is reported as `resolvedConstant` citing the
    declaration line. Categories: grpc, http, kafka, registry (consul, ribbon/eureka discovery), config (env/JNDI
    reads), scheduler (timer/scheduled-executor APIs: a registry heartbeat cadence is configured through them).
"""
import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_citations  # noqa: E402
import inputs  # noqa: E402

COMPOSE_DEFAULT_URL = "https://docs.docker.com/reference/compose-file/deploy/#replicas"
ROLE_BY_IMAGE = {
    "hashicorp/consul": "registry", "consul": "registry",
    "mongo": "datastore", "mysql": "datastore", "mariadb": "datastore", "postgres": "datastore",
    "memcached": "cache", "redis": "cache", "valkey/valkey": "cache",
    "apache/kafka": "broker", "rabbitmq": "broker", "bitnami/kafka": "broker",
    "otel/opentelemetry-collector-contrib": "collector", "otel/opentelemetry-collector": "collector",
    "jaegertracing/all-in-one": "telemetry-backend", "quay.io/prometheus/prometheus": "telemetry-backend",
    "prom/prometheus": "telemetry-backend", "grafana/grafana": "telemetry-backend",
    "opensearchproject/opensearch": "telemetry-backend",
}

# ============================================================================================ compose layer


def _repo_of(img):
    base = img.split("@")[0]
    last = base.split("/")[-1]
    return base.rsplit(":", 1)[0] if ":" in last else base


def _cite(loc, token=None, note=None):
    f = {"repo": loc["repo"], "sourceFile": loc["file"], "line": loc["line"],
         "quotedToken": token if token is not None else loc["raw"]}
    if note:
        f["note"] = note
    return f


def _line_of(repos, rk, path, needle, start=1):
    for i, s in enumerate(repos[rk].text(path).splitlines(), 1):
        if i >= start and needle in s:
            return i, s.strip()
    return None, None


def _role(comp, repos, name, bundle):
    s = comp.services[name]
    if bundle["kind"] == "built":
        df = bundle["dockerfile"]
        _, froms = inputs.copy_sources(repos[df["repo"]].text(df["path"]))
        img, line = froms[-1]
        role = ROLE_BY_IMAGE.get(_repo_of(img), "microservice")
        lines = repos[df["repo"]].text(df["path"]).splitlines()
        return role, {"repo": df["repo"], "sourceFile": df["path"], "line": line, "quotedToken": img,
                      "note": "stage-1 rule D1: built from the pinned tree; last FROM %s" % img}
    img = comp.interp(s["image"]["value"])[0]
    role = ROLE_BY_IMAGE.get(_repo_of(img), "other")
    return role, _cite(s["image"], note="stage-1 rule D1: image-only service, image %s" % img)


def _hosts_in(value):
    out = []
    for part in value.split(","):
        p = part.strip()
        p = re.sub(r"^[A-Za-z][A-Za-z0-9+.-]*://", "", p)
        p = p.split("@")[-1]
        h = re.split(r"[:/]", p, maxsplit=1)[0]
        if h:
            out.append(h)
    return out


def compose_facts(system, repos, comp, bundles, services):
    cfg = inputs.SYSTEMS[system]
    alias = comp.aliases()
    rk0, p0 = cfg["compose"][0]
    ln, raw = _line_of(repos, rk0, p0, "services:")
    spec_services, edges, obs = [], [], []
    for name in services:
        s, b = comp.services[name], bundles[name]
        key = s["key"]
        sv = {"name": dict(value=name, **_cite(key, name + ":"))}
        role, rc = _role(comp, repos, name, b)
        sv["role"] = dict(value=role, **rc)
        if "container_name" in s:
            sv["container"] = dict(value=comp.interp(s["container_name"]["value"])[0], **_cite(s["container_name"]))
        else:
            sv["container"] = dict(value=name, **_cite(key, name + ":", note=(
                "stage-1 rule D2: container_name not set; Compose names the container <project>-%s-<n>" % name)))
        if "replicas" in s or "scale" in s:
            loc = s.get("replicas") or s.get("scale")
            sv["replicas"] = dict(value=int(comp.interp(loc["value"])[0]), **_cite(loc))
        else:
            sv["replicas"] = {"value": 1, "basis": "documented-default", "sourceUrl": COMPOSE_DEFAULT_URL,
                              "note": "stage-1 rule D3: no deploy.replicas or scale for %s in %s; Compose default 1"
                                      % (name, ", ".join("%s:%s" % c for c in cfg["compose"]))}
        spec_services.append(sv)

        # D4 candidate sync edges
        for var, loc in sorted(s["environment"].items()):
            if loc["value"] is None:
                if var not in comp.env:
                    obs.append(dict(kind="env-unresolved", service=name, value=var, **_cite(loc)))
                    continue
                raw_v, used, unres = comp.env[var][0], [(var, comp.env[var][1])], []
                v, u2, unres = comp.interp(raw_v)
                used += u2
            else:
                v, used, unres = comp.interp(loc["value"])
            if unres:
                obs.append(dict(kind="env-unresolved", service=name, value="%s=%s" % (var, loc["value"]),
                                note="variables not in the pinned .env: %s" % ",".join(sorted(set(unres))),
                                **_cite(loc)))
            for h in _hosts_in(v):
                callee = alias.get(h)
                if not callee or callee == name:
                    continue
                if h in loc["raw"]:
                    f = _cite(loc, note="stage-1 rule D4: environment %s=%s" % (var, v))
                else:
                    envf = inputs.SYSTEMS[system]["env"][0]
                    hit = [(n, l) for n, l in used if h in comp.env[n][0]]
                    n, l = hit[-1] if hit else used[-1]
                    raw_env = repos[envf[0]].text(envf[1]).splitlines()[l - 1].strip()
                    f = {"repo": envf[0], "sourceFile": envf[1], "line": l, "quotedToken": raw_env,
                         "note": "stage-1 rule D4: %s %s:%d passes %s=%s to %s" % (
                             "bare entry" if loc["value"] is None else "entry", loc["file"], loc["line"], var, v, name)}
                edges.append(dict(value={"caller": name, "callee": callee}, **f))
        for d in s["depends_on"]:
            obs.append(dict(kind="depends_on", service=name, value=d["value"], **_cite(d)))
        if "healthcheck" in s:
            obs.append(dict(kind="healthcheck", service=name, value=s["healthcheck"]["value"],
                            params={k: v["value"] for k, v in s.get("healthcheck_params", {}).items()},
                            **_cite(s["healthcheck"])))
        for k in ("image", "build_context", "dockerfile", "entrypoint"):
            if k in s:
                v = s[k]["value"]
                obs.append(dict(kind=k, service=name, value=comp.interp(v)[0] if isinstance(v, str) else v,
                                **_cite(s[k])))
        if b.get("buildScript"):
            bs = b["buildScript"]
            l = repos[bs["repo"]].text(bs["path"]).splitlines()[bs["line"] - 1].strip()
            obs.append(dict(kind="build_context", service=name, value=b["buildContext"]["path"], repo=bs["repo"],
                            sourceFile=bs["path"], line=bs["line"], quotedToken=l,
                            note="inputs.py R2: image built by the upstream build script"))
    arch = dict(value=system, repo=rk0, sourceFile=p0, line=ln, quotedToken=raw,
                note="architecture = the services of the compose files %s" % ", ".join("%s:%s" % c for c in cfg["compose"]))
    hk, hp = inputs.HOST_TOPOLOGY
    tok = '"hostId": "%s"' % cfg["host"]
    hl, _ = _line_of(repos, hk, hp, tok)
    host = dict(value=cfg["host"], repo=hk, sourceFile=hp, line=hl, quotedToken=tok,
                note="one host per system (EXTRACTION_PROTOCOL Stage 1); inputs.SYSTEMS host")
    return arch, host, spec_services, edges, obs

# ============================================================================================ AST layer


LANG_BY_EXT = {".java": "java", ".go": "go", ".cs": "csharp", ".py": "python", ".js": "javascript",
               ".mjs": "javascript", ".cjs": "javascript", ".jsx": "javascript", ".ts": "typescript", ".tsx": "tsx",
               ".kt": "kotlin", ".kts": "kotlin", ".rb": "ruby", ".php": "php", ".rs": "rust", ".cpp": "cpp",
               ".cc": "cpp", ".cxx": "cpp", ".h": "cpp", ".hpp": "cpp", ".ex": "elixir", ".exs": "elixir"}
JS = ("javascript", "typescript", "tsx")
JVM = ("java", "kotlin")

CATALOGUE = [
    # gRPC
    dict(cat="grpc", lang=("go",), module="google.golang.org/grpc", calls=["Dial", "DialContext", "NewClient"]),
    dict(cat="grpc", lang=JVM, module="io.grpc", types=["ManagedChannelBuilder", "NettyChannelBuilder", "Grpc"],
         methods=["forAddress", "forTarget", "newBlockingStub", "newStub", "newFutureStub", "newCoroutineStub"]),
    dict(cat="grpc", lang=("csharp",), module="Grpc.Net.Client", types=["GrpcChannel"]),
    dict(cat="grpc", lang=("csharp",), module="Grpc.Core", types=["Channel"]),
    dict(cat="grpc", lang=("python",), module="grpc", calls=["insecure_channel", "secure_channel", "aio"]),
    dict(cat="grpc", lang=("python",), module="_pb2_grpc", suffix=True, any=True),
    dict(cat="grpc", lang=JS, module="@grpc/grpc-js", any=True),
    dict(cat="grpc", lang=("ruby",), module="grpc", methods=["Stub"]),
    dict(cat="grpc", lang=("php",), module="Grpc", any=True),
    dict(cat="grpc", lang=("rust",), module="tonic", any=True, methods=["connect"]),
    dict(cat="grpc", lang=("cpp",), module="grpcpp", calls=["CreateChannel", "CreateCustomChannel"],
         methods=["NewStub"]),
    # HTTP clients
    dict(cat="http", lang=("go",), module="net/http",
         calls=["Get", "Post", "PostForm", "Head", "NewRequest", "NewRequestWithContext"], types=["Client"]),
    dict(cat="http", lang=JVM, module="jakarta.ws.rs.client", types=["ClientBuilder", "Entity"],
         methods=["target", "request", "newClient"]),
    dict(cat="http", lang=JVM, module="javax.ws.rs.client", types=["ClientBuilder", "Entity"],
         methods=["target", "request", "newClient"]),
    dict(cat="http", lang=JVM, module="org.glassfish.jersey.client", types=["ClientConfig", "JerseyClientBuilder"]),
    dict(cat="http", lang=JVM, module="java.net.http", types=["HttpClient", "HttpRequest"]),
    dict(cat="http", lang=JVM, module="okhttp3", types=["OkHttpClient", "Request"]),
    dict(cat="http", lang=("csharp",), module="System.Net.Http", types=["HttpClient", "HttpRequestMessage"]),
    dict(cat="http", lang=("python",), module="requests", any=True),
    dict(cat="http", lang=("python",), module="httpx", any=True),
    dict(cat="http", lang=("python",), module="urllib.request", calls=["urlopen", "Request"]),
    dict(cat="http", lang=("python",), module="locust", methods=["get", "post", "put", "delete"]),
    dict(cat="http", lang=JS, module="axios", any=True),
    dict(cat="http", lang=JS, module="node-fetch", any=True),
    dict(cat="http", lang=JS, module=None, globals=["fetch"]),
    dict(cat="http", lang=("ruby",), module="net/http", types=["Net::HTTP"]),
    dict(cat="http", lang=("ruby",), module="faraday", any=True),
    dict(cat="http", lang=("php",), module="GuzzleHttp", any=True),
    dict(cat="http", lang=("rust",), module="reqwest", any=True),
    dict(cat="http", lang=("rust",), module="hyper", any=True),
    # Kafka
    dict(cat="kafka", lang=("go",), module="github.com/IBM/sarama", any=True),
    dict(cat="kafka", lang=("go",), module="github.com/Shopify/sarama", any=True),
    dict(cat="kafka", lang=("go",), module="github.com/segmentio/kafka-go", any=True),
    dict(cat="kafka", lang=JVM, module="org.apache.kafka.clients",
         types=["KafkaProducer", "KafkaConsumer", "ProducerRecord", "ProducerConfig", "ConsumerConfig"],
         methods=["subscribe", "poll", "send", "assign", "commitSync", "commitAsync"]),
    dict(cat="kafka", lang=("csharp",), module="Confluent.Kafka",
         types=["ConsumerBuilder", "ProducerBuilder", "ConsumerConfig", "ProducerConfig"],
         methods=["Subscribe", "Consume", "Produce", "ProduceAsync", "Commit"]),
    dict(cat="kafka", lang=("python",), module="confluent_kafka", any=True),
    dict(cat="kafka", lang=("python",), module="kafka", any=True),
    dict(cat="kafka", lang=JS, module="kafkajs", any=True),
    # registry / discovery
    dict(cat="registry", lang=("go",), module="github.com/hashicorp/consul/api", any=True,
         methods=["ServiceRegister", "ServiceDeregister", "Service", "Health"]),
    dict(cat="registry", lang=JVM, module="com.netflix.loadbalancer", any=True),
    dict(cat="registry", lang=JVM, module="com.netflix.discovery", any=True),
    dict(cat="registry", lang=JVM, module="org.springframework.cloud", any=True),
    # configuration reads
    dict(cat="config", lang=("go",), module="os", calls=["Getenv", "LookupEnv"]),
    dict(cat="config", lang=JVM, module=None, globals=["System.getenv", "System.getProperty"]),
    dict(cat="config", lang=JVM, module="javax.naming", types=["InitialContext"], methods=["lookup"]),
    dict(cat="config", lang=("csharp",), module=None, globals=["Environment.GetEnvironmentVariable"]),
    dict(cat="config", lang=("python",), module="os", calls=["getenv", "environ.get", "environ"]),
    dict(cat="config", lang=JS, module=None, globals=["process.env"]),
    dict(cat="config", lang=("ruby",), module=None, globals=["ENV.fetch", "ENV"]),
    dict(cat="config", lang=("php",), module=None, globals=["getenv"]),
    dict(cat="config", lang=("rust",), module=None, globals=["env::var", "std::env::var"]),
    dict(cat="config", lang=("cpp",), module=None, globals=["getenv", "std::getenv"]),
    dict(cat="config", lang=("elixir",), module=None, globals=["System.get_env"]),
    # schedulers (heartbeat cadence)
    dict(cat="scheduler", lang=("go",), module="time", calls=["NewTicker", "Tick", "AfterFunc", "NewTimer"]),
    dict(cat="scheduler", lang=JVM, module="java.util.concurrent",
         methods=["scheduleAtFixedRate", "scheduleWithFixedDelay", "newSingleThreadScheduledExecutor",
                  "newScheduledThreadPool"]),
    dict(cat="scheduler", lang=("csharp",), module="System.Threading", types=["Timer", "PeriodicTimer"]),
]

# in-tree propagation carries only client-library categories, not config reads or timers
WRAPPER_CATEGORIES = {"grpc", "http", "kafka", "registry"}

CALL_NODES = {
    "go": ("call_expression", "composite_literal"),
    "java": ("method_invocation", "object_creation_expression"),
    "kotlin": ("call_expression",),
    "csharp": ("invocation_expression", "object_creation_expression"),
    "python": ("call",),
    "javascript": ("call_expression", "new_expression", "member_expression"),
    "typescript": ("call_expression", "new_expression", "member_expression"),
    "tsx": ("call_expression", "new_expression", "member_expression"),
    "ruby": ("call",),
    "php": ("function_call_expression", "member_call_expression", "scoped_call_expression",
            "object_creation_expression"),
    "rust": ("call_expression",),
    "cpp": ("call_expression", "new_expression"),
    "elixir": ("call",),
}
IMPORT_NODES = {
    "go": ("import_spec",), "java": ("import_declaration",), "kotlin": ("import_header", "import"),
    "csharp": ("using_directive",), "python": ("import_statement", "import_from_statement"),
    "javascript": ("import_statement", "call_expression"), "typescript": ("import_statement", "call_expression"),
    "tsx": ("import_statement", "call_expression"), "ruby": ("call",), "php": ("namespace_use_declaration",),
    "rust": ("use_declaration",), "cpp": ("preproc_include",), "elixir": ("call",),
}
LITERAL_TYPES = {
    "interpreted_string_literal", "raw_string_literal", "string_literal", "string", "verbatim_string_literal",
    "interpolated_string_expression", "template_string", "encapsed_string", "int_literal", "integer_literal",
    "decimal_integer_literal", "hex_integer_literal", "float_literal", "real_literal", "decimal_floating_point_literal",
    "number", "integer", "float", "number_literal", "line_string_literal", "multi_line_string_literal",
    "raw_string", "char_literal", "boolean_literal", "true", "false", "long_literal",
}


def _parser(lang):
    from tree_sitter_language_pack import get_parser
    return get_parser(lang)


def _walk(n):
    stack = [n]
    while stack:
        x = stack.pop()
        yield x
        stack.extend(reversed(x.children))


def _txt(n):
    return n.text.decode("utf-8", "replace")


def _norm(s):
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"<[^<>()]*>", "", s)  # generic args
    return s


def _imports(lang, root):
    """[(bound name or None, module)] of one file."""
    out = []
    for n in _walk(root):
        if n.type not in IMPORT_NODES.get(lang, ()):
            continue
        t = _txt(n)
        if lang == "go":
            p = n.child_by_field_name("path")
            nm = n.child_by_field_name("name")
            if p is None:
                continue
            mod = _txt(p).strip('"`')
            seg = [x for x in mod.split("/") if not re.fullmatch(r"v\d+", x)]
            bound = _txt(nm) if nm is not None else re.sub(r"\.v\d+$", "", seg[-1]).replace("-", "_")
            out.append((None if bound in ("_", ".") else bound, mod))
        elif lang in JVM:
            m = re.search(r"import\s+(?:static\s+)?([\w.]+)(\.\*)?(?:\s+as\s+(\w+))?", t)
            if m:
                mod = m.group(1)
                out.append((None if m.group(2) else (m.group(3) or mod.rsplit(".", 1)[-1]), mod))
        elif lang == "csharp":
            m = re.search(r"using\s+(?:static\s+)?(?:(\w+)\s*=\s*)?([\w.]+)", t)
            if m:
                out.append((m.group(1), m.group(2)))
        elif lang == "python":
            if n.type == "import_statement":
                for m in re.finditer(r"([\w.]+)(?:\s+as\s+(\w+))?", t[len("import"):]):
                    out.append((m.group(2) or m.group(1).split(".")[0], m.group(1)))
            else:
                m = re.match(r"from\s+([\w.]+)\s+import\s+(.*)", t, re.S)
                if m:
                    for x in re.finditer(r"(\w+)(?:\s+as\s+(\w+))?", m.group(2)):
                        out.append((x.group(2) or x.group(1), m.group(1) + "." + x.group(1)))
        elif lang in JS:
            if n.type == "call_expression":
                if not t.startswith("require("):
                    continue
                m = re.match(r"require\(\s*['\"]([^'\"]+)['\"]", t)
                if not m:
                    continue
                par = n.parent
                name = par.child_by_field_name("name") if par is not None and par.type == "variable_declarator" else None
                if name is None:
                    out.append((None, m.group(1)))
                else:
                    for b in re.findall(r"\w+", _txt(name)):
                        out.append((b, m.group(1)))
                continue
            m = re.search(r"from\s+['\"]([^'\"]+)['\"]|^import\s+['\"]([^'\"]+)['\"]", t)
            if not m:
                continue
            mod = m.group(1) or m.group(2)
            head = t.split("from")[0][len("import"):]
            names = re.findall(r"(?:\w+\s+as\s+)?(\w+)", head.replace("type ", ""))
            for b in names or [None]:
                out.append((b, mod))
        elif lang == "ruby":
            m = re.match(r"require(?:_relative)?\s*\(?\s*['\"]([^'\"]+)['\"]", t)
            if m:
                out.append((None, m.group(1)))
        elif lang == "php":
            for m in re.finditer(r"([\w\\]+)(?:\s+as\s+(\w+))?", t[len("use"):]):
                mod = m.group(1).lstrip("\\")
                out.append((m.group(2) or mod.rsplit("\\", 1)[-1], mod.replace("\\", ".")))
        elif lang == "rust":
            m = re.search(r"use\s+([\w:]+)", t)
            if m:
                mod = m.group(1)
                out.append((mod.rsplit("::", 1)[-1], mod.replace("::", "/")))
                for x in re.findall(r"\{([^}]*)\}", t):
                    for b in re.findall(r"\w+", x):
                        out.append((b, mod.replace("::", "/") + "/" + b))
        elif lang == "cpp":
            m = re.search(r"[<\"]([^>\"]+)[>\"]", t)
            if m:
                out.append((None, m.group(1)))
        elif lang == "elixir":
            m = re.match(r"(alias|import|require)\s+([\w.]+)", t)
            if m:
                out.append((m.group(2).rsplit(".", 1)[-1], m.group(2)))
    return out


def _callee(lang, n):
    """-> (callee text normalised, node whose first line is cited, created type or None)."""
    t = n.type
    if lang == "go" and t == "composite_literal":
        ty = n.child_by_field_name("type")
        return (_norm(_txt(ty)), ty, _norm(_txt(ty))) if ty is not None else (None, None, None)
    if t in ("object_creation_expression", "new_expression"):
        ty = n.child_by_field_name("type") or n.child_by_field_name("constructor")
        if ty is None:
            ty = next((c for c in n.named_children if c.type not in ("argument_list", "arguments")), None)
        return (_norm(_txt(ty)), ty, _norm(_txt(ty))) if ty is not None else (None, None, None)
    if lang == "java" and t == "method_invocation":
        obj, name = n.child_by_field_name("object"), n.child_by_field_name("name")
        txt = (_txt(obj) + "." if obj is not None else "") + _txt(name)
        return _norm(txt), (obj if obj is not None else name), None
    if t == "member_expression":
        if n.parent is not None and n.parent.type in ("member_expression", "call_expression"):
            return None, None, None
        return _norm(_txt(n)), n, None
    f = n.child_by_field_name("function") or n.child_by_field_name("method") or n.child_by_field_name("name")
    if lang == "ruby":
        recv, meth = n.child_by_field_name("receiver"), n.child_by_field_name("method")
        txt = (_txt(recv) + "." if recv is not None else "") + (_txt(meth) if meth is not None else "")
        return _norm(txt), (recv if recv is not None else meth), None
    if lang == "php" and t in ("member_call_expression", "scoped_call_expression"):
        obj = n.child_by_field_name("object") or n.child_by_field_name("scope")
        nm = n.child_by_field_name("name")
        txt = (_txt(obj) + "." if obj is not None else "") + (_txt(nm) if nm is not None else "")
        return _norm(txt).replace("->", ".").replace("::", "."), (obj or nm), None
    if f is None and n.named_children:
        f = n.named_children[0]
    if f is None:
        return None, None, None
    return _norm(_txt(f)).replace("->", "."), f, None


def _segments(callee):
    s = re.sub(r"\([^()]*\)", "", callee)
    while re.search(r"\([^()]*\)", s):
        s = re.sub(r"\([^()]*\)", "", s)
    return [x for x in re.split(r"\.|::|\?\.|!!\.", s) if x]


def _args_node(n):
    for f in ("arguments", "argument_list"):
        a = n.child_by_field_name(f)
        if a is not None:
            return a
    for c in n.children:
        if c.type in ("argument_list", "arguments", "literal_value", "initializer_expression",
                      "value_arguments", "call_suffix"):
            return c
    return None


def _initializer(n):
    return next((c for c in n.children if c.type in ("initializer_expression", "literal_value", "class_body")), None)


def _constants(lang, root):
    """{identifier: literal node} for same-file declarations initialised by a literal."""
    out = {}
    for n in _walk(root):
        name = val = None
        if n.type in ("const_spec", "var_spec") and lang == "go":
            name, val = n.child_by_field_name("name"), n.child_by_field_name("value")
            if val is not None and val.named_children:
                val = val.named_children[0]
        elif n.type == "variable_declarator":
            name = n.child_by_field_name("name")
            val = n.child_by_field_name("value")
            if val is None:
                val = next((c for c in n.named_children if c.type in LITERAL_TYPES), None)
                if val is None:
                    eq = next((c for c in n.named_children if c.type == "equals_value_clause"), None)
                    val = eq.named_children[0] if eq is not None and eq.named_children else None
        elif n.type == "assignment" and lang == "python":
            name, val = n.child_by_field_name("left"), n.child_by_field_name("right")
        if name is not None and val is not None and val.type in LITERAL_TYPES:
            out.setdefault(_txt(name), val)
    return out


def _shadowed(node, name):
    """True if an enclosing function declares a parameter `name` (it then shadows a same-file constant)."""
    p = node.parent
    while p is not None:
        ps = p.child_by_field_name("parameters")
        if ps is not None and re.search(r"\b%s\b" % re.escape(name), _txt(ps)):
            return True
        p = p.parent
    return False


def _lit(repo, path, node, kind="literal", note=None):
    first = _txt(node).splitlines()[0] if _txt(node) else _txt(node)
    tok = first.strip()[:200]
    d = {"kind": kind, "value": _txt(node)[:500], "repo": repo, "sourceFile": path,
         "line": node.start_point[0] + 1, "quotedToken": tok}
    if note:
        d["note"] = note
    return d


def _arg_literals(repo, path, n, consts):
    lits = []
    a = _args_node(n)
    regions = [x for x in (a, _initializer(n)) if x is not None]
    seen = set()
    for reg in regions:
        for x in _walk(reg):
            if any(x.start_byte >= s and x.end_byte <= e for s, e in seen):
                continue
            if x.type in LITERAL_TYPES and x.type not in ("true", "false"):
                seen.add((x.start_byte, x.end_byte))
                lits.append(_lit(repo, path, x))
            elif x.type in ("identifier", "simple_identifier") and _txt(x) in consts and not _shadowed(x, _txt(x)):
                c = consts[_txt(x)]
                lits.append(_lit(repo, path, c, "resolvedConstant",
                                 "identifier %s at line %d" % (_txt(x), x.start_point[0] + 1)))
    # dedupe by (line, token)
    out, keys = [], set()
    for l in lits:
        k = (l["kind"], l["line"], l["quotedToken"])
        if k not in keys:
            keys.add(k)
            out.append(l)
    return out[:40]


def _imported(entry, imps):
    mod = entry.get("module")
    if mod is None:
        return True, set()
    bound, hit = set(), False
    for b, m in imps:
        ok = m.endswith(mod) if entry.get("suffix") else (m == mod or m.startswith(mod + ".") or
                                                           m.startswith(mod + "/") or (mod.startswith(m + ".") and b is None))
        if ok:
            hit = True
            if b:
                bound.add(b)
    return hit, bound


def match(lang, callee, ctype, imps):
    """-> [(category, library, how)] for one call."""
    segs = _segments(callee)
    if not segs:
        return []
    root, final = segs[0], segs[-1]
    out = []
    for e in CATALOGUE:
        if lang not in e["lang"]:
            continue
        if e.get("globals"):
            if any(callee == g or callee.startswith(g + ".") or callee.startswith(g + "[") or
                   ".".join(segs[:len(g.split("."))]) == g for g in e["globals"]):
                out.append((e["cat"], e.get("module") or "builtin", "global"))
            continue
        imported, bound = _imported(e, imps)
        if not imported:
            continue
        name_after_root = segs[1] if len(segs) > 1 else None
        if root in bound and (e.get("any") or (name_after_root in e.get("calls", ())) or
                              ".".join(segs[1:3]) in e.get("calls", ())):
            out.append((e["cat"], e["module"], "qualified"))
        elif root in e.get("types", ()) or (ctype and (ctype.split(".")[-1] in e.get("types", ()) or
                                                       ctype in e.get("types", ()))):
            out.append((e["cat"], e["module"], "type"))
        elif len(segs) > 1 and final in e.get("methods", ()):
            out.append((e["cat"], e["module"], "method"))
        elif lang in JVM and root in bound and final in e.get("methods", ()):
            out.append((e["cat"], e["module"], "method"))
    seen, res = set(), []
    for x in out:
        if x[:2] not in seen:
            seen.add(x[:2])
            res.append(x)
    return res


class FileAst:
    def __init__(self, repo, path, lang, src):
        self.repo, self.path, self.lang = repo, path, lang
        self.root = _parser(lang).parse(src).root_node
        self.imports = _imports(lang, self.root)
        self.consts = _constants(lang, self.root)
        self.calls = []
        for n in _walk(self.root):
            if n.type in CALL_NODES.get(lang, ()):
                callee, cnode, ctype = _callee(lang, n)
                if callee:
                    self.calls.append((n, callee, cnode, ctype))

    def hits(self, extra=None):
        """One record per matched call; a matched call nested in the callee of another matched call (the receiver
        chain `A.get().register(...)` -> `A.get()`) is dropped in favour of the outer one."""
        found = []
        for n, callee, cnode, ctype in self.calls:
            ms = match(self.lang, callee, ctype, self.imports)
            if extra:
                ms += [m for m in extra(self, callee) if m[0] in WRAPPER_CATEGORIES or m[2] == "generated-stub"]
            if ms:
                found.append((n, callee, cnode, ms))
        spans = [(c.start_byte, c.end_byte) for _, _, c, _ in found]
        out = []
        for n, callee, cnode, ms in found:
            if any(s <= n.start_byte and n.end_byte <= e and (s, e) != (cnode.start_byte, cnode.end_byte)
                   for s, e in spans):
                continue
            first = _txt(cnode).splitlines()[0].strip() if _txt(cnode) else callee
            out.append({"kind": "ast-call-site", "category": sorted({m[0] for m in ms})[0] if len(ms) == 1 else
                        "+".join(sorted({m[0] for m in ms})),
                        "matches": [{"category": c, "library": l, "match": h} for c, l, h in ms],
                        "language": self.lang, "value": callee[:300], "repo": self.repo,
                        "sourceFile": self.path, "line": cnode.start_point[0] + 1,
                        "quotedToken": first[:200],
                        "literals": _arg_literals(self.repo, self.path, n, self.consts)})
        return out


def ast_pass(system, repos, bundles, services):
    """AST call sites over the union of the selected services' bundle files. -> (observations, stats)."""
    files = {}
    for name in services:
        for f in bundles[name]["files"]:
            files.setdefault((f["repo"], f["path"]), []).append(name)
    asts, skipped = {}, {}
    for (rk, p) in sorted(files):
        lang = LANG_BY_EXT.get(posixpath.splitext(p)[1].lower())
        if lang is None:
            ext = posixpath.splitext(p)[1].lower() or posixpath.basename(p)
            skipped[ext] = skipped.get(ext, 0) + 1
            continue
        asts[(rk, p)] = FileAst(rk, p, lang, repos[rk].read(p))

    # first pass: direct hits
    direct = {k: a.hits() for k, a in asts.items()}

    # Go: in-tree wrappers and generated-stub packages
    go_mod = {}
    for (rk, p), a in asts.items():
        if a.lang == "go":
            d = posixpath.dirname(p)
            while True:
                gm = posixpath.join(d, "go.mod") if d else "go.mod"
                if repos[rk].has(gm):
                    go_mod[(rk, p)] = (d, re.search(r"^module\s+(\S+)", repos[rk].text(gm), re.M).group(1))
                    break
                if not d:
                    break
                d = posixpath.dirname(d)
    pkg_cats = {}
    for k, hs in direct.items():
        if k in go_mod:
            pkg_cats.setdefault((k[0], posixpath.dirname(k[1])), set()).update(
                m["category"] for h in hs for m in h["matches"] if m["category"] in WRAPPER_CATEGORIES)
    stub_dirs = set()
    for (rk, p), (mroot, mod) in go_mod.items():
        for b, imp in asts[(rk, p)].imports:
            if imp.startswith(mod + "/"):
                d = posixpath.normpath(posixpath.join(mroot, imp[len(mod) + 1:]))
                for f in repos[rk].files_under(d):
                    if posixpath.dirname(f) == d and inputs.exclusion(repos[rk], f) == "generated-stub" and \
                            b"grpc" in repos[rk].read(f):
                        stub_dirs.add((rk, d))

    def go_extra(a, callee):
        k = (a.repo, a.path)
        if k not in go_mod:
            return []
        mroot, mod = go_mod[k]
        segs = _segments(callee)
        out = []
        for b, imp in a.imports:
            if b and segs and segs[0] == b and imp.startswith(mod + "/"):
                d = posixpath.normpath(posixpath.join(mroot, imp[len(mod) + 1:]))
                cats = pkg_cats.get((a.repo, d), set())
                for c in sorted(cats):
                    out.append((c, "in-tree:" + d, "via-wrapper"))
                if (a.repo, d) in stub_dirs and len(segs) > 1 and re.fullmatch(r"New\w+Client", segs[1]):
                    out.append(("grpc", "generated-stub:" + d, "generated-stub"))
        return out

    # Java: in-tree classes with hits
    cls_cats = {}
    for (rk, p), hs in direct.items():
        if p.endswith(".java") and hs:
            m = re.search(r"src/main/java/(.+)\.java$", p)
            if m:
                cs = {x["category"] for h in hs for x in h["matches"] if x["category"] in WRAPPER_CATEGORIES}
                if cs:
                    cls_cats[m.group(1).replace("/", ".")] = cs

    def java_extra(a, callee):
        segs = _segments(callee)
        out = []
        if not segs:
            return out
        for b, imp in a.imports:
            if b and b == segs[0] and imp in cls_cats:
                for c in sorted(cls_cats[imp]):
                    out.append((c, "in-tree:" + imp, "via-wrapper"))
        return out

    obs = []
    for k, a in sorted(asts.items()):
        extra = go_extra if a.lang == "go" else java_extra if a.lang == "java" else None
        hs = a.hits(extra) if extra else direct[k]
        for h in hs:
            h["services"] = sorted(files[k])
        obs += hs
    from tree_sitter_language_pack import cache_dir
    stats = {"filesParsed": len(asts), "filesSkippedByExtension": skipped,
             "languages": sorted({a.lang for a in asts.values()}),
             "callSites": len(obs),
             "byCategory": {c: sum(1 for h in obs if c in {m["category"] for m in h["matches"]})
                            for c in sorted({m["category"] for h in obs for m in h["matches"]})},
             "grammarCache": str(cache_dir())}
    return obs, stats

# ============================================================================================ spec


def build_stage1(system, services=None, root=inputs.ROOT):
    repos = inputs.open_repos(system, root)
    comp, bundles = inputs.service_bundles(system, repos)
    inputs.finalize(system, repos, bundles)
    names = services or list(comp.order)
    unknown = [s for s in names if s not in comp.services]
    if unknown:
        raise SystemExit("unknown services for %s: %s" % (system, unknown))
    arch, host, svcs, edges, obs = compose_facts(system, repos, comp, bundles, names)
    ast_obs, stats = ast_pass(system, repos, bundles, names)
    srcs = {}
    for k, r in repos.items():
        srcs[k] = {"path": r.relpath, "commit": r.commit}
    spec = {
        "schemaVersion": 1,
        "sut": system,
        "extraction": {
            "stage": 1, "procedure": "research/ontology/EXTRACTION_PROTOCOL.md",
            "tool": "research/ontology/extract_stage1.py", "services": names,
            "rules": "extract_stage1.py D1-D5, inputs.py R1-R7",
            "astStats": stats,
            "observations": obs + ast_obs,
        },
        "sources": srcs,
        "architecture": {"name": arch},
        "host": {"id": host},
        "services": svcs,
    }
    if edges:
        spec["syncEdges"] = edges
    return spec


def check_observations(spec, root=inputs.ROOT):
    """check_citations over every cited observation and literal of extraction.observations (same checker)."""
    shadow = {"sources": spec["sources"], "obs": []}
    for o in spec.get("extraction", {}).get("observations", []):
        shadow["obs"].append({k: o[k] for k in ("value", "repo", "sourceFile", "line", "quotedToken")})
        for l in o.get("literals", []):
            shadow["obs"].append({k: l[k] for k in ("value", "repo", "sourceFile", "line", "quotedToken")})
    return check_citations.check_spec(shadow, root)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("system", choices=sorted(inputs.SYSTEMS))
    ap.add_argument("--services")
    ap.add_argument("-o", "--out")
    a = ap.parse_args(argv)
    spec = build_stage1(a.system, a.services.split(",") if a.services else None)
    text = json.dumps(spec, indent=1, sort_keys=False, default=str) + "\n"
    if a.out:
        if Path(a.out).exists():
            sys.exit("refusing to overwrite %s" % a.out)
        Path(a.out).write_text(text)
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
