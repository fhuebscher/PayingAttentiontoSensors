import argparse, hashlib, importlib.util, json, math, os, re, shutil, stat, subprocess, sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT=Path(__file__).parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
materialize=load("ob_materialize",ROOT/"modules/online-boutique/materialize.py")
campaign=load("ob_campaign",ROOT/"modules/online-boutique/execution/campaign.py")
workload=load("ob_workload",ROOT/"modules/online-boutique/workload/fixed_home.py")
normalizer=load("ob_normalizer",ROOT/"modules/online-boutique/normalizers/otel_debug.py")
signal_channel=load("ob_signal_channel",ROOT/"modules/online-boutique/validation/signal_channel.py")
receipt_validator=load("ob_receipt",ROOT/"modules/online-boutique/validation/receipt.py")
control_runner=load("ob_control_runner",ROOT/"modules/online-boutique/execution/control_microtests.py")
control_validator=load("ob_control_validator",ROOT/"modules/online-boutique/validation/control_microtest.py")
control_observation=load("ob_control_observation",ROOT/"modules/online-boutique/validation/control_observation.py")
control_root=load("ob_control_root",ROOT/"modules/online-boutique/validation/control_microtest_root.py")
module_audit=load("module_audit",ROOT/"src/obsplacement/module_audit.py")

def arguments(**updates):
    values={"postures":"none,selected,full","blocks":1,"duration":120,"warmup":30,"rate":1.0,
            "concurrency":4,"fault_at":45,"outage":15,"project":"obsplacement-ob-test","port":18080,
            "canary_project":"obsplacement-ob-canary","canary_port":18081}
    values.update(updates); return argparse.Namespace(**values)

def control_arguments(**updates):
    values={"cell":"frontend-source-tracing","duration":30,"warmup":15,"rate":1.0,
            "concurrency":4,"seed":20260817,"project":"obsplacement-ob-control","port":18090,
            "canary_project":"obsplacement-ob-control-canary","canary_port":18091}
    values.update(updates); return argparse.Namespace(**values)

def test_campaign_rejects_unsafe_or_unbounded_parameters():
    assert campaign.validate(arguments()) == ("none","selected","full")
    for update in ({"rate":math.inf},{"project":"BAD project"},{"port":80},{"fault_at":110,"outage":10}):
        try: campaign.validate(arguments(**update)); assert False
        except ValueError: pass

def test_materialized_guards_cover_go_request_path(tmp_path):
    source=tmp_path/"source"
    for relative in ("src/frontend/main.go","src/productcatalogservice/server.go","src/currencyservice/server.js"):
        target=source/relative; target.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(materialize.UPSTREAM/relative,target)
    changes=materialize.apply_source_guards(source)
    assert len(changes)==14
    assert "if tracingEnabled" in (source/"src/frontend/main.go").read_text()
    assert "grpc.NewClient(addr, opts...)" in (source/"src/frontend/main.go").read_text()
    assert "srv = grpc.NewServer()" in (source/"src/productcatalogservice/server.go").read_text()
    assert 'attribute.String("service.name", "frontend")' in (source/"src/frontend/main.go").read_text()
    assert 'attribute.String("service.name", "productcatalogservice")' in (source/"src/productcatalogservice/server.go").read_text()
    currency=(source/"src/currencyservice/server.js").read_text()
    assert currency.index('if(process.env.ENABLE_TRACING == "1")') < currency.index("registerInstrumentations({")

def test_homepage_goal_discloses_mandatory_unobservable_calls():
    goal=json.loads((ROOT/"modules/online-boutique/goals/homepage-path.json").read_text())
    assert "cartservice:GetCart" in goal["scenario"]["requiredRuntimeCalls"]
    assert "adservice:GetAds" in goal["scenario"]["requiredRuntimeCalls"]
    assert goal["constraints"]["completeHomepageVisibilityFeasible"] is False
    assert goal["scenario"]["requiredSensors"][0] == "span:frontend:GET"

def test_posture_environment_is_exact_and_source_bound(tmp_path):
    (tmp_path/".source.sha256").write_text("a"*64+"\n")
    env=campaign.environment("selected",tmp_path,"obs-ob-test",18080)
    assert env["OB_TRACE_FRONTEND"] == "1"
    assert env["OB_TRACE_PRODUCTCATALOG"] == "1"
    assert env["OB_TRACE_CURRENCY"] == "0"
    assert env["OB_SOURCE_SHA256"] == "a"*64

def native_fixture():
    return (ROOT/"tests/fixtures/online_boutique/otelcol-0.108.0-selected.log").read_text()


def signal_inputs(text):
    started="2026-08-08T16:09:19+00:00"
    ended="2026-08-08T16:09:30+00:00"
    window={"startedAt":started,"endedAt":ended}
    channel=json.loads((ROOT/"modules/online-boutique/acquisition/signal-channel.json").read_text())
    target=json.loads((ROOT/"modules/online-boutique/evals/signal-channel-target.json").read_text())
    digest=hashlib.sha256(text.encode()).hexdigest(); size=len(text.encode())
    captured=[(datetime.fromisoformat(ended)+timedelta(seconds=value)).isoformat()
              for value in (8,10,12)]
    parsed=normalizer.parse_detailed(text); counts=parsed["counts"]
    semantics=signal_channel.snapshot_semantics(
        parsed["spans"],window=window,posture="selected",channel=channel,target=target)
    attempts=[{"capturedAt":item,"returnCode":0,"stderr":"","stdoutBytes":size,
               "stdoutSha256":digest,"reconciled":parsed["reconciled"],"counts":counts,
               "claimProjection":semantics["claimProjection"],
               "postWindowTail":semantics["postWindowTail"]}
              for item in captured]
    completeness={"schemaVersion":1,"configuration":channel["acquisitionCompleteness"],
        "windowStartedAt":started,"windowEndedAt":ended,"observedUntil":captured[-1],
        "observationSeconds":12.0,"stableProjectionSnapshots":3,
        "carrierAppendMonotone":True,"allPollsReconciled":True,"attempts":attempts,
        "terminalCarrier":semantics["carrier"],
        "terminalClaimProjection":semantics["claimProjection"],
        "terminalPostWindowTail":semantics["postWindowTail"],"passed":True}
    image_id="sha256:38088dde2576e026be0cfa08fd1ca1a9511de714f780d9cf5e9414ff9efae0a3"
    repo_digest="otel/opentelemetry-collector-contrib@sha256:"+"b"*64
    native_container={
        "Id":"collector-container-id", "Image":image_id,
        "Config":{"Image":"otel/opentelemetry-collector-contrib:0.108.0",
                  "Labels":{"com.docker.compose.project":"obs-ob-test",
                            "com.docker.compose.service":"otel-collector"}},
        "State":{"Running":True,"OOMKilled":False}, "RestartCount":0,
    }
    native_image={"Id":image_id,"RepoDigests":[repo_digest]}
    container_stdout=json.dumps([native_container])
    image_stdout=json.dumps([native_image])
    return {
        "posture":"selected",
        "window":window,
        "query":{"returnCode":0,"stderr":"","since":started,
                 "project":"obs-ob-test","composePath":"/srv/source/compose.observability-placement.yml",
                 "composeSha256":"d"*64,"containerId":"collector-container-id",
                 "command":["docker","compose","-p","obs-ob-test","-f",
                            "/srv/source/compose.observability-placement.yml","logs","--no-color",
                            "--since",started,"otel-collector"],
                 "stdoutBytes":len(text.encode()),
                 "stdoutSha256":hashlib.sha256(text.encode()).hexdigest()},
        "collector_runtime":{"configImage":"otel/opentelemetry-collector-contrib:0.108.0",
                             "containerId":"collector-container-id",
                             "imageId":image_id,"repoDigests":[repo_digest],
                             "composeProjectLabel":"obs-ob-test",
                             "composeServiceLabel":"otel-collector",
                             "nativeContainerInspect":native_container,
                             "nativeImageInspect":native_image,
                             "acquisitionProof":{
                               "containerLookup":{"command":["docker","compose","-p","obs-ob-test","-f",
                                 "/srv/source/compose.observability-placement.yml","ps","-q","otel-collector"],
                                 "returnCode":0,"stdout":"collector-container-id\n","stderr":""},
                               "containerInspect":{"command":["docker","inspect","collector-container-id"],
                                 "returnCode":0,"stdout":container_stdout,
                                 "stdoutBytes":len(container_stdout.encode()),
                                 "stdoutSha256":hashlib.sha256(container_stdout.encode()).hexdigest(),
                                 "stderr":""},
                               "imageInspect":{"command":["docker","image","inspect",
                                 "sha256:38088dde2576e026be0cfa08fd1ca1a9511de714f780d9cf5e9414ff9efae0a3"],
                                 "returnCode":0,"stdout":image_stdout,
                                 "stdoutBytes":len(image_stdout.encode()),
                                 "stdoutSha256":hashlib.sha256(image_stdout.encode()).hexdigest(),
                                 "stderr":""}},
                             "state":{"running":True,"restartCount":0,"oomKilled":False}},
        "channel":channel,
        "target":target,
        "goal":json.loads((ROOT/"modules/online-boutique/goals/homepage-path.json").read_text()),
        "acquisition_completeness":completeness,
        "normalizer":normalizer,
    }


def debug_span_batch(index, service, started, *, name=None, kind="Client", parent=None,
                     attributes=None, trace_id=None, span_id=None):
    """Build one exact collector-0.108 debug batch for acquisition attack tests."""
    name = name or "opentelemetry.proto.collector.trace.v1.TraceService/Export"
    attributes = attributes or {
        "rpc.method": "opentelemetry.proto.collector.trace.v1.TraceService/Export",
        "rpc.response.status_code": "OK", "rpc.system.name": "grpc",
        "server.address": "172.18.0.4", "server.port": "4317",
    }
    trace_id = trace_id or f"{index + 1:032x}"
    span_id = span_id or f"{index + 1:016x}"
    end = started + timedelta(milliseconds=1)
    def native_time(value):
        return value.strftime("%Y-%m-%d %H:%M:%S.") + f"{value.microsecond:06d}000 +0000 UTC"
    attribute_lines = []
    for key, value in attributes.items():
        value_type = "Int" if key == "server.port" else "Str"
        attribute_lines.append(f"     -> {key}: {value_type}({value})")
    header = json.dumps({"kind":"exporter","data_type":"traces","name":"debug",
                         "resource spans":1,"spans":1})
    trailer = json.dumps({"kind":"exporter","data_type":"traces","name":"debug"})
    return "\n".join([
        f"TracesExporter {header}", "ResourceSpans #0", "Resource SchemaURL: ",
        "Resource attributes:", f"     -> service.name: Str({service})", "ScopeSpans #0",
        "ScopeSpans SchemaURL: ", "InstrumentationScope retained-p0b-regression 1.0.0",
        "Span #0", f"    Trace ID       : {trace_id}",
        f"    Parent ID      : {parent or ''}", f"    ID             : {span_id}",
        f"    Name           : {name}", f"    Kind           : {kind}",
        f"    Start time     : {native_time(started)}", f"    End time       : {native_time(end)}",
        "    Status code    : Unset", "    Status message : ", "Attributes:",
        *attribute_lines, trailer, "",
    ])


def control_carrier(posture):
    started=datetime.fromisoformat("2026-08-17T01:00:00+00:00")
    specifications={
        "source-off":[],
        "frontend-off":[
            ("productcatalogservice","hipstershop.ProductCatalogService/ListProducts","Server",{}),
            ("currencyservice","hipstershop.CurrencyService/GetSupportedCurrencies","Server",{}),
            ("currencyservice","hipstershop.CurrencyService/Convert","Server",{}),
        ],
        "full-reference":[
            ("frontend","GET","Server",{"http.request.method":"GET","url.path":"/"}),
            ("frontend","hipstershop.ProductCatalogService/ListProducts","Client",{}),
            ("frontend","hipstershop.CurrencyService/GetSupportedCurrencies","Client",{}),
            ("frontend","hipstershop.CurrencyService/Convert","Client",{}),
            ("productcatalogservice","hipstershop.ProductCatalogService/ListProducts","Server",{}),
            ("currencyservice","hipstershop.CurrencyService/GetSupportedCurrencies","Server",{}),
            ("currencyservice","hipstershop.CurrencyService/Convert","Server",{}),
        ],
    }
    return "".join(debug_span_batch(index,service,started+timedelta(seconds=index+1),
                                    name=name,kind=kind,attributes=attributes)
                   for index,(service,name,kind,attributes) in enumerate(specifications[posture]))


def control_inputs(posture):
    text=control_carrier(posture)
    base=signal_inputs(text)
    window={"startedAt":"2026-08-17T01:00:00+00:00",
            "endedAt":"2026-08-17T01:00:30+00:00"}
    channel=json.loads((ROOT/"modules/online-boutique/acquisition/signal-channel.json").read_text())
    target=json.loads((ROOT/"modules/online-boutique/evals/phase1-source-targets.json").read_text())
    matrix=json.loads((ROOT/"modules/online-boutique/activation/phase1-source-microtests.json").read_text())
    parsed=normalizer.parse_detailed(text)
    semantics=control_validator.snapshot_semantics(
        parsed["spans"],window=window,posture=posture,channel=channel,target=target)
    raw=text.encode(); captured=[
        (datetime.fromisoformat(window["endedAt"])+timedelta(seconds=value)).isoformat()
        for value in (8,10,12)]
    attempts=[{"capturedAt":item,"returnCode":0,"stderr":"","stdoutBytes":len(raw),
               "stdoutSha256":hashlib.sha256(raw).hexdigest(),
               "reconciled":parsed["reconciled"],"counts":parsed["counts"],
               "claimProjection":semantics["claimProjection"],
               "postWindowTail":semantics["postWindowTail"]} for item in captured]
    completeness={"schemaVersion":1,"configuration":channel["acquisitionCompleteness"],
        "windowStartedAt":window["startedAt"],"windowEndedAt":window["endedAt"],
        "observedUntil":captured[-1],"observationSeconds":12.0,
        "stableProjectionSnapshots":3,"carrierAppendMonotone":True,
        "allPollsReconciled":True,"attempts":attempts,
        "terminalCarrier":semantics["carrier"],
        "terminalClaimProjection":semantics["claimProjection"],
        "terminalPostWindowTail":semantics["postWindowTail"],"passed":True}
    digest="a"*64; controls=matrix["postures"][posture]; services={}
    build_images={}
    for index,(service,control) in enumerate((
            ("frontend","frontend"),("productcatalogservice","productcatalog"),
            ("currencyservice","currency")),1):
        cid=f"source-container-{index}"; image_id=f"sha256:{index:064x}"
        native={"Id":cid,"Image":image_id,
                "Config":{"Image":f"source-image-{index}",
                          "Env":[f"ENABLE_TRACING={controls[control]}",
                                 f"OBSPLACEMENT_SOURCE_SHA256={digest}"],
                          "Labels":{"com.observability-placement.materialized-source":digest,
                                    "com.docker.compose.project":base["query"]["project"],
                                    "com.docker.compose.service":service}},
                "State":{"Running":True,"OOMKilled":False},"RestartCount":0}
        stdout=json.dumps([native])
        lookup_stdout=cid+"\n"
        services[service]={"containerId":cid,"imageId":image_id,"expectedImageId":image_id,
            "enableTracing":controls[control],"expectedEnableTracing":controls[control],
            "embeddedSourceSha256":digest,"imageSourceSha256Label":digest,
            "composeProjectLabel":base["query"]["project"],"composeServiceLabel":service,
            "state":{"running":True,"oomKilled":False,"restartCount":0},
            "containerLookup":{"command":["docker","compose","-p",base["query"]["project"],
                "-f",base["query"]["composePath"],"ps","-q",service],"returnCode":0,
                "stdout":lookup_stdout,"stdoutBytes":len(lookup_stdout.encode()),
                "stdoutSha256":hashlib.sha256(lookup_stdout.encode()).hexdigest(),"stderr":""},
            "nativeInspect":{"command":["docker","inspect",cid],"returnCode":0,
                             "stdout":stdout,"stdoutBytes":len(stdout.encode()),
                             "stdoutSha256":hashlib.sha256(stdout.encode()).hexdigest(),
                             "stderr":""}}
        build_images[service]={"tag":f"source-image-{index}","imageId":image_id,
                               "sourceSha256Label":digest}
    query=base["query"]
    query["since"]=window["startedAt"]
    query["command"]=["docker","compose","-p",query["project"],"-f",query["composePath"],
                      "logs","--no-color","--since",window["startedAt"],"otel-collector"]
    query["stdoutBytes"]=len(raw); query["stdoutSha256"]=hashlib.sha256(raw).hexdigest()
    build={"schemaVersion":1,"buildCount":1,"materializedSourceSha256":digest,
           "composeSha256":query["composeSha256"],"images":build_images}
    build_sha="e"*64
    return {"cell":"frontend-source-tracing","posture":posture,"window":window,
            "query":query,"collector_runtime":base["collector_runtime"],
            "acquisition_completeness":completeness,
            "posture_proof":{"schemaVersion":1,"cell":"frontend-source-tracing",
                "requested":posture,"requestedControls":controls,"sourceGuarded":True,
                "materializedSourceSha256":digest,
                "buildReceiptSha256":build_sha,
                "guardChangeIds":sorted(control_validator.EXPECTED_GUARD_IDS),
                "services":services},
            "matrix":matrix,"target":target,"channel":channel,"build":build,
            "build_sha256":build_sha,"normalizer":normalizer}


def write_control_inputs(run, values):
    """Write one terminal control fixture and bind it to its root build receipt."""
    run.mkdir(parents=True,exist_ok=True)
    build_path=run.parent/"build.json"
    if not build_path.exists():
        build_path.write_text(json.dumps(values["build"],indent=2,sort_keys=True)+"\n")
    build_sha=campaign.sha256(build_path)
    posture=json.loads(json.dumps(values["posture_proof"]))
    posture["buildReceiptSha256"]=build_sha
    for filename,payload in (("otelcol-query.json",values["query"]),
            ("collector-runtime.json",values["collector_runtime"]),
            ("acquisition-completeness.json",values["acquisition_completeness"]),
            ("posture-proof.json",posture)):
        (run/filename).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    (run/"otelcol.log").write_text(control_carrier(values["posture"]))
    values["posture_proof"]=posture
    values["build_sha256"]=build_sha
    return values


def bind_prefix_history(prefixes, capture_offsets, *, posture="selected"):
    """Bind poll evidence to terminal bytes exactly as the validator must recompute it."""
    assert len(prefixes) == len(capture_offsets) and prefixes
    terminal = prefixes[-1]
    values = signal_inputs(terminal)
    values["posture"] = posture
    channel = values["channel"]; target = values["target"]; window = values["window"]
    ended = datetime.fromisoformat(window["endedAt"])
    attempts = []; previous = b""; append_monotone = True; all_reconciled = True
    stable = 0; previous_projection = None
    for text, offset in zip(prefixes, capture_offsets):
        raw = text.encode(); parsed = normalizer.parse_detailed(text)
        semantics = signal_channel.snapshot_semantics(
            parsed["spans"], window=window, posture=posture, channel=channel, target=target)
        poll_append = raw.startswith(previous)
        valid = parsed["reconciled"] and not parsed["errors"] and poll_append
        projection = semantics["claimProjection"]["spanRecordSetSha256"]
        stable = stable + 1 if valid and projection == previous_projection else (1 if valid else 0)
        append_monotone = append_monotone and poll_append
        all_reconciled = all_reconciled and valid
        captured = (ended + timedelta(seconds=offset)).isoformat()
        attempts.append({
            "capturedAt": captured, "returnCode": 0, "stderr": "",
            "stdoutBytes": len(raw), "stdoutSha256": hashlib.sha256(raw).hexdigest(),
            "reconciled": parsed["reconciled"], "counts": parsed["counts"],
            "claimProjection": semantics["claimProjection"],
            "postWindowTail": semantics["postWindowTail"],
        })
        previous = raw; previous_projection = projection
    terminal_parsed = normalizer.parse_detailed(terminal)
    terminal_semantics = signal_channel.snapshot_semantics(
        terminal_parsed["spans"], window=window, posture=posture, channel=channel, target=target)
    minimum = channel["acquisitionCompleteness"]["minimumPostWindowObservationSeconds"]
    required = channel["acquisitionCompleteness"]["requiredStableSnapshots"]
    passed = (capture_offsets[-1] >= minimum and stable >= required and
              append_monotone and all_reconciled)
    values["acquisition_completeness"] = {
        "schemaVersion": 1, "configuration": channel["acquisitionCompleteness"],
        "windowStartedAt": window["startedAt"], "windowEndedAt": window["endedAt"],
        "observedUntil": attempts[-1]["capturedAt"],
        "observationSeconds": round(float(capture_offsets[-1]), 6),
        "stableProjectionSnapshots": stable, "carrierAppendMonotone": append_monotone,
        "allPollsReconciled": all_reconciled, "attempts": attempts,
        "terminalCarrier": terminal_semantics["carrier"],
        "terminalClaimProjection": terminal_semantics["claimProjection"],
        "terminalPostWindowTail": terminal_semantics["postWindowTail"], "passed": passed,
    }
    return values


def test_real_native_trace_fixture_reconciles_and_proves_shared_edge():
    text=native_fixture()
    provenance=json.loads((ROOT/"tests/fixtures/online_boutique/otelcol-0.108.0-selected.provenance.json").read_text())
    assert provenance["fixtureBytes"] == len(text.encode()) == 64384
    assert provenance["fixtureSha256"] == hashlib.sha256(text.encode()).hexdigest() == \
        "57b3da4a92eea5ed309e94586d0537a5bc2dc3068d98a4b415fe433da676883d"
    assert provenance["sourceArtifactBytes"] == 388769
    assert provenance["sourceArtifactSha256"] == "8180cc6ecf2a596168ce567dbc8f3e7406107497f35ad89a21064f430c806e26"
    assert provenance["sourceCampaignEvidenceSha256"] == "3d8078b1c50a390ded2fb361d89c92f7bf25658d8a6e33aa04415da549d888a3"
    assert provenance["extraction"] == "byte-preserving lines 1-1096; first two complete exporter batches"
    parsed=normalizer.parse_detailed(text)
    assert parsed["reconciled"] is True
    assert parsed["counts"]["exportBatchCount"] == 2
    assert parsed["counts"]["exporterDeclaredSpanCount"] == 65
    assert parsed["counts"]["rawObservedSpanCount"] == 65
    assert parsed["counts"]["normalizedSpanCount"] == 65
    assert parsed["counts"]["uniqueSpanIdentityCount"] == 65
    spans=parsed["spans"]
    spans=normalizer.detailed_spans(text)
    goal=json.loads((ROOT/"modules/online-boutique/goals/homepage-path.json").read_text())
    visible=normalizer.goal_visibility(spans,goal)
    assert len(spans)==65
    assert visible["verdict"] == "pass"
    assert visible["requiredSensorRetention"] == 1.0
    assert "1466e070884a34bd8bdff8e65fde8766" in visible["sharedTraceIdsForRequiredEdge"]
    assert "1466e070884a34bd8bdff8e65fde8766" in visible["directParentLinkedTraceIdsForRequiredEdge"]
    assert visible["completePathTraceCount"] >= 1
    assert visible["descriptiveTelemetryPathCompleteness"] == 0.8

    retained=ROOT/provenance["sourceArtifact"]
    if retained.is_file():
        retained_bytes=retained.read_bytes()
        assert len(retained_bytes) == provenance["sourceArtifactBytes"]
        assert hashlib.sha256(retained_bytes).hexdigest() == provenance["sourceArtifactSha256"]
        extracted=b"\n".join(retained_bytes.splitlines()[:1096])+b"\n"
        assert extracted == text.encode()


def test_signal_target_state_passes_real_fixture_and_keeps_carrier_semantics_explicit():
    text=native_fixture()
    result=signal_channel.evaluate(text,**signal_inputs(text))
    assert result["passed"] is True, result["blockers"]
    assert result["channel"] == {
        "signalType":"traces","semanticUnit":"span","transport":"otlp-grpc",
        "collectorEndpoint":"otel-collector:4317","acquisitionCarrier":"collector-debug-stdout",
        "applicationLogsInstrumented":False,"applicationLogsSupport":"unsupported"}
    assert result["stageClassification"]["normalization"] == "passed"
    assert result["visibility"]["verdict"] == "pass"


def test_p0b_exporter_tail_growth_keeps_claim_projection_stable_and_diagnostic():
    base = native_fixture(); ended = datetime.fromisoformat("2026-08-08T16:09:30+00:00")
    # P0b produced alternating frontend/product exporter self-spans at an approximately
    # five-second cadence.  The raw carrier grew forever although the measured cohort froze.
    offsets = (4.067,4.702,9.071,9.703,14.072,14.709,19.072,19.713,24.072,24.716)
    services = ("productcatalogservice","frontend") * 5
    batches = [debug_span_batch(1000+index,service,ended+timedelta(seconds=offset))
               for index,(offset,service) in enumerate(zip(offsets,services))]
    carriers = [base+"".join(batches[:6]), base+"".join(batches[:8]), base+"".join(batches)]
    values = bind_prefix_history(carriers, (16,22,28))
    result = signal_channel.evaluate(carriers[-1], **values)
    proof = result["acquisitionCompleteness"]
    assert result["passed"] is True, result["blockers"]
    assert proof["terminalCarrier"]["spanCount"] == 75
    assert proof["terminalClaimProjection"]["spanCount"] == 65
    assert proof["terminalPostWindowTail"]["all"]["spanCount"] == 10
    assert proof["terminalPostWindowTail"]["exporterSelfObservation"]["spanCount"] == 10
    assert proof["terminalPostWindowTail"]["unclassified"]["spanCount"] == 0
    assert proof["terminalPostWindowTail"]["scope"].startswith("diagnostic-only")


def test_unclassified_allowed_tail_is_retained_but_not_silently_promoted_to_evidence():
    base = native_fixture(); ended = datetime.fromisoformat("2026-08-08T16:09:30+00:00")
    unknown = debug_span_batch(
        1200,"frontend",ended+timedelta(seconds=4),name="health.check",kind="Internal",
        attributes={"check":"ready"})
    terminal = base + unknown
    values = bind_prefix_history([terminal]*3, (12,14,16))
    result = signal_channel.evaluate(terminal, **values)
    tail = result["acquisitionCompleteness"]["terminalPostWindowTail"]
    assert result["passed"] is True, result["blockers"]
    assert tail["all"]["spanCount"] == tail["unclassified"]["spanCount"] == 1
    assert tail["exporterSelfObservation"]["spanCount"] == 0
    assert result["acquisitionCompleteness"]["terminalClaimProjection"]["spanCount"] == 65


def test_late_in_window_record_resets_projection_stability():
    base = native_fixture(); ended = datetime.fromisoformat("2026-08-08T16:09:30+00:00")
    late = debug_span_batch(1300,"frontend",ended-timedelta(seconds=1),
                            name="late.in-window",kind="Internal",attributes={"late":"true"})
    terminal = base + late
    values = bind_prefix_history([base,base,terminal], (12,14,16))
    assert values["acquisition_completeness"]["stableProjectionSnapshots"] == 1
    result = signal_channel.evaluate(terminal, **values)
    assert result["passed"] is False
    assert any("bounded post-window stability" in item for item in result["blockers"])


def test_late_forbidden_service_span_blocks_selected_after_projection_stabilizes():
    base = native_fixture(); ended = datetime.fromisoformat("2026-08-08T16:09:30+00:00")
    forbidden = debug_span_batch(
        1400,"currencyservice",ended+timedelta(seconds=4),name="currency.background",
        kind="Internal",attributes={"source":"forbidden"})
    terminal = base + forbidden
    values = bind_prefix_history([terminal]*3, (12,14,16))
    assert values["acquisition_completeness"]["passed"] is True
    result = signal_channel.evaluate(terminal, **values)
    assert result["passed"] is False
    assert any("source-off carrier retained forbidden service spans: currencyservice" in item
               for item in result["blockers"])


def test_poll_history_is_recomputed_from_terminal_prefixes_and_rejects_forgery():
    base = native_fixture(); ended = datetime.fromisoformat("2026-08-08T16:09:30+00:00")
    tail = debug_span_batch(1500,"frontend",ended+timedelta(seconds=4))
    terminal = base + tail
    values = bind_prefix_history([base,terminal,terminal], (12,14,16))
    values["acquisition_completeness"]["attempts"][0]["stdoutSha256"] = "0" * 64
    result = signal_channel.evaluate(terminal, **values)
    assert result["passed"] is False
    assert any("hash is not a prefix of the retained carrier" in item for item in result["blockers"])

    values = bind_prefix_history([terminal]*3, (12,14,16))
    values["acquisition_completeness"]["attempts"][0]["claimProjection"][
        "spanRecordSetSha256"] = "1" * 64
    result = signal_channel.evaluate(terminal, **values)
    assert result["passed"] is False
    assert any("claim projection is not recomputed" in item for item in result["blockers"])


def test_record_digest_detects_same_count_same_identity_content_substitution():
    values = signal_inputs(native_fixture()); parsed = normalizer.parse_detailed(native_fixture())
    original = signal_channel.snapshot_semantics(
        parsed["spans"],window=values["window"],posture="selected",
        channel=values["channel"],target=values["target"])["claimProjection"]
    changed = json.loads(json.dumps(parsed["spans"]))
    changed[0]["attributes"]["rpc.response.status_code"] = "ERROR"
    substituted = signal_channel.snapshot_semantics(
        changed,window=values["window"],posture="selected",
        channel=values["channel"],target=values["target"])["claimProjection"]
    assert original["spanCount"] == substituted["spanCount"]
    assert original["spanIdentitySetSha256"] == substituted["spanIdentitySetSha256"]
    assert original["spanRecordSetSha256"] != substituted["spanRecordSetSha256"]


def test_carrier_removal_malformed_and_duplicate_tail_attacks_fail_closed():
    base = native_fixture(); ended = datetime.fromisoformat("2026-08-08T16:09:30+00:00")
    tail = debug_span_batch(1600,"frontend",ended+timedelta(seconds=4))
    terminal = base + tail
    values = bind_prefix_history([terminal,base,terminal], (12,14,16))
    result = signal_channel.evaluate(terminal, **values)
    assert result["passed"] is False
    assert any("append-only carrier prefix" in item for item in result["blockers"])

    first = normalizer.parse_detailed(base)["spans"][0]
    duplicate = debug_span_batch(
        1601,first["service"],ended+timedelta(seconds=4),
        trace_id=first["traceId"],span_id=first["spanId"])
    for attacked in (base+"collector error: malformed late tail\n", base+duplicate):
        values = bind_prefix_history([attacked]*3, (12,14,16))
        result = signal_channel.evaluate(attacked, **values)
        assert result["passed"] is False
        assert any(item.startswith("native carrier:") for item in result["blockers"])


def test_selected_requires_goal_visibility_not_merely_required_service_names():
    started = datetime.fromisoformat("2026-08-08T16:09:19+00:00")
    carrier = (
        debug_span_batch(1700,"frontend",started+timedelta(seconds=1)) +
        debug_span_batch(1701,"productcatalogservice",started+timedelta(seconds=2)))
    values = bind_prefix_history([carrier]*3, (12,14,16))
    result = signal_channel.evaluate(carrier, **values)
    assert result["passed"] is False
    services = result["measurementCounts"]["measuredServiceSpanCounts"]
    assert services["frontend"] == 1
    assert services["productcatalogservice"] == 1
    assert result["visibility"]["verdict"] == "blocked"
    assert any("required measured path visibility did not pass" in item
               for item in result["blockers"])


def test_bounded_horizon_dependency_or_configuration_drift_requires_abstention():
    text = native_fixture(); values = signal_inputs(text)
    values["channel"] = json.loads(json.dumps(values["channel"]))
    values["channel"]["acquisitionCompleteness"]["horizonQualification"][
        "nodeSdkVersions"] = "drifted"
    result = signal_channel.evaluate(text, **values)
    assert result["passed"] is False
    assert any("signal channel manifest differs from the exact supported contract" in item
               for item in result["blockers"])


def test_receipt_separates_measured_cohort_from_capture_time_carrier_totals():
    denominators = {
        "exporterDeclaredSpanCount":1,"rawObservedSpanCount":1,
        "normalizedSpanCount":1,"uniqueSpanIdentityCount":1,
        "malformedSpanRecordCount":0,"duplicateSpanIdentityCount":0,
    }
    receipt = {
        "posture":"full",
        "source":{"upstreamSha":"9a4616e77f0f9cbcbecaf27d711c38890dda1404"},
        "workload":{"offered":1,"completed":1,"failed":0},
        "intervention":{"manifested":True,"recovered":True},
        "telemetry":{"inWindowSpanRecords":1,"terminalCarrierValuesComparable":False,
                     "terminalCarrierScope":"capture-time diagnostic only; not a denominator"},
        "postureProof":{"sourceGuarded":True},
        "signalChannel":{"passed":True,"counts":denominators,
                         "channel":{"signalType":"traces",
                                    "acquisitionCarrier":"collector-debug-stdout",
                                    "applicationLogsInstrumented":False}},
        "teardown":{"projectClean":True},
    }
    assert receipt_validator.blockers(receipt) == []
    drifted = json.loads(json.dumps(receipt))
    drifted["telemetry"]["terminalCarrierValuesComparable"] = True
    assert "terminal carrier totals are not declared diagnostic-only" in \
        receipt_validator.blockers(drifted)
    empty = json.loads(json.dumps(receipt)); empty["telemetry"]["inWindowSpanRecords"] = 0
    assert "full posture retained no in-window spans" in receipt_validator.blockers(empty)


def test_native_format_drift_and_positive_raw_zero_normalized_fail_at_normalization():
    text=native_fixture().replace("     ID             :", "     Span ID        :")
    parsed=normalizer.parse_detailed(text)
    assert parsed["counts"]["rawObservedSpanCount"] == 65
    assert parsed["counts"]["normalizedSpanCount"] == 0
    assert parsed["reconciled"] is False
    result=signal_channel.evaluate(text,**signal_inputs(text))
    assert result["passed"] is False
    assert result["stageClassification"] == {
        "anySignalObserved":True,"targetSourceEmission":"indeterminate-normalization-failed",
        "backgroundEmission":"indeterminate-normalization-failed","transport":"observed","collectorReception":"observed",
        "normalization":"failed","goalEvaluation":"not-reached"}
    assert any("unexpected Span ID" in item for item in result["blockers"])


def test_native_count_duplicate_and_truncation_mutations_fail_closed():
    text=native_fixture()
    count_drift=text.replace('"resource spans": 1, "spans": 6}',
                             '"resource spans": 1, "spans": 7}',1)
    assert normalizer.parse_detailed(count_drift)["reconciled"] is False
    parsed=normalizer.parse_detailed(text)["spans"]
    first=parsed[0]
    second=next(row for row in parsed[1:] if row["traceId"] != first["traceId"])
    duplicate=text.replace(f"Trace ID       : {second['traceId']}",
                           f"Trace ID       : {first['traceId']}",1)
    duplicate=duplicate.replace(f"ID             : {second['spanId']}",
                                f"ID             : {first['spanId']}",1)
    duplicate_result=normalizer.parse_detailed(duplicate)
    assert duplicate_result["reconciled"] is False
    assert duplicate_result["counts"]["duplicateSpanIdentityCount"] == 1
    truncated="\n".join(text.splitlines()[:-1])+"\n"
    assert any("trailer" in item for item in normalizer.parse_detailed(truncated)["errors"])


def test_none_target_allows_silence_but_not_target_source_spans():
    empty=signal_inputs("")
    empty["posture"]="none"
    empty["window"]={"startedAt":"2026-08-08T16:09:19+00:00","endedAt":"2026-08-08T16:09:30+00:00"}
    passed=signal_channel.evaluate("",**empty)
    assert passed["passed"] is True
    assert passed["stageClassification"]["targetSourceEmission"] == "absent-as-expected"
    text=native_fixture()
    nonempty=signal_inputs(text); nonempty["posture"]="none"
    blocked=signal_channel.evaluate(text,**nonempty)
    assert blocked["passed"] is False
    assert any("source-off carrier retained" in item for item in blocked["blockers"])


def test_none_rejects_delayed_forbidden_warmup_spans_outside_measurement_window():
    text=native_fixture(); values=signal_inputs(text); values["posture"]="none"
    values["window"]={"startedAt":"2026-08-08T16:10:00+00:00","endedAt":"2026-08-08T16:11:00+00:00"}
    values["query"]["since"]=values["window"]["startedAt"]
    values["query"]["command"]=["docker","compose","-p",values["query"]["project"],"-f",
                                 values["query"]["composePath"],"logs","--no-color","--since",
                                 values["window"]["startedAt"],"otel-collector"]
    result=signal_channel.evaluate(text,**values)
    assert result["measurementCounts"]["beforeWindowSpanCount"] == 65
    assert result["passed"] is False
    assert any("source-off carrier retained" in item for item in result["blockers"])


def test_nonempty_unknown_carrier_and_weakened_target_fail_closed():
    garbage="collector error: otlp receiver failed\n"
    parsed=normalizer.parse_detailed(garbage)
    assert parsed["reconciled"] is False and parsed["spans"] == []
    values=signal_inputs(native_fixture())
    values["target"]={**values["target"],"sourceServices":[]}
    result=signal_channel.evaluate(native_fixture(),**values)
    assert result["passed"] is False
    assert any("exact supported target" in item for item in result["blockers"])


def test_workload_denominators_require_rows_arithmetic_and_a_success():
    def row(at,error,status=200):
        return {"scheduledAtEpoch":at,"startedAtEpoch":at+.01,"endedAtEpoch":at+.02,
                "status":status,"bytes":100 if error is None else 0,"error":error}
    valid={"scenario":"homepage","url":"http://127.0.0.1:18080/",
           "ratePerSecond":2.0,"durationSeconds":1.0,"concurrency":2,
           "offered":2,"completed":1,"failed":1,
           "requests":[row(10,None),row(10.5,"Timeout",None)]}
    assert campaign.workload_blockers(valid) == []
    assert campaign.workload_blockers({**valid,"completed":0,"failed":2})
    assert campaign.workload_blockers({**valid,"requests":[]})
    expected={key:valid[key] for key in
              ("scenario","url","ratePerSecond","durationSeconds","concurrency")}
    window={"startedAt":"1970-01-01T00:00:09+00:00","endedAt":"1970-01-01T00:00:12+00:00"}
    assert campaign.workload_blockers(valid,expected=expected,window=window) == []
    assert campaign.workload_blockers(valid,expected={**expected,"ratePerSecond":3.0},window=window)
    malformed={**valid,"requests":[{"error":None},row(10.5,"Timeout",None)]}
    assert campaign.workload_blockers(malformed,expected=expected,window=window)

def test_campaign_requires_exact_three_posture_cohort_and_frozen_collector_image():
    try: campaign.validate(arguments(postures="none")); assert False
    except ValueError: pass
    text=native_fixture(); values=signal_inputs(text)
    values["collector_runtime"]={**values["collector_runtime"],"imageId":"sha256:"+"c"*64}
    result=signal_channel.evaluate(text,**values)
    assert result["passed"] is False
    assert any("frozen signal-channel image ID" in item for item in result["blockers"])

def test_none_requires_bounded_claim_projection_and_collector_project_binding():
    values=signal_inputs(""); values["posture"]="none"
    witness=values["acquisition_completeness"]
    ended=datetime.fromisoformat(witness["windowEndedAt"])
    witness["attempts"]=[{**row,"capturedAt":(ended+timedelta(seconds=index)).isoformat()}
                         for index,row in zip((1,2,3),witness["attempts"])]
    witness["observedUntil"]=witness["attempts"][-1]["capturedAt"]
    witness["observationSeconds"]=3.0
    witness["passed"]=True
    result=signal_channel.evaluate("",**values)
    assert result["passed"] is False
    assert any("bounded post-window stability" in item for item in result["blockers"])

    values=signal_inputs(""); values["posture"]="none"
    witness=values["acquisition_completeness"]
    identical=(datetime.fromisoformat(witness["windowEndedAt"])+timedelta(seconds=12)).isoformat()
    witness["attempts"]=[{**row,"capturedAt":identical} for row in witness["attempts"]]
    witness["observedUntil"]=identical
    result=signal_channel.evaluate("",**values)
    assert result["passed"] is False
    assert any("strictly increasing" in item or "poll interval" in item
               for item in result["blockers"])

    values=signal_inputs(""); values["posture"]="none"
    witness=values["acquisition_completeness"]
    ended=datetime.fromisoformat(witness["windowEndedAt"])
    shifted=(ended-timedelta(seconds=100),ended-timedelta(seconds=50),
             ended+timedelta(seconds=12))
    witness["attempts"]=[{**row,"capturedAt":captured.isoformat()}
                         for row,captured in zip(witness["attempts"],shifted)]
    result=signal_channel.evaluate("",**values)
    assert result["passed"] is False
    assert any("post-window observations" in item for item in result["blockers"])

    text=native_fixture(); values=signal_inputs(text)
    forged="forged-container-id"
    values["query"]["containerId"]=forged
    values["collector_runtime"]={**values["collector_runtime"],"containerId":forged}
    lookup=values["collector_runtime"]["acquisitionProof"]["containerLookup"]
    lookup["stdout"]=forged+"\n"
    inspect=values["collector_runtime"]["acquisitionProof"]["containerInspect"]
    inspect["command"]=["docker","inspect",forged]
    forged_native={**values["collector_runtime"]["nativeContainerInspect"],"Id":forged}
    values["collector_runtime"]["nativeContainerInspect"]=forged_native
    result=signal_channel.evaluate(text,**values)
    assert result["passed"] is False
    assert any("retained raw stdout" in item for item in result["blockers"])

    values=signal_inputs(text)
    inspect=values["collector_runtime"]["acquisitionProof"]["containerInspect"]
    del inspect["stdoutBytes"]; del inspect["stdoutSha256"]
    result=signal_channel.evaluate(text,**values)
    assert result["passed"] is False
    assert any("raw stdout binding" in item for item in result["blockers"])

def test_shared_signal_schemas_leave_adapter_values_and_posture_names_project_owned():
    channel_schema=json.loads((ROOT/"contracts/signal-channel.schema.json").read_text())
    target_schema=json.loads((ROOT/"contracts/signal-target.schema.json").read_text())
    assert "const" not in channel_schema["properties"]["collector"].get("properties",{}).get("service",{})
    postures=target_schema["properties"]["postures"]
    assert "required" not in postures and "additionalProperties" in postures

def test_failed_docker_inventory_query_can_never_prove_cleanup(monkeypatch):
    class Failed:
        returncode=1; stdout=""; stderr="daemon unavailable"
    monkeypatch.setattr(campaign,"command",lambda *args,**kwargs: Failed())
    proof=campaign.project_resources("obs-ob-test")
    assert proof["containers"] == proof["networks"] == proof["volumes"] == []
    assert proof["queryPassed"] is False
    assert campaign.resources_clean(proof) is False

def test_failed_git_status_can_never_prove_clean_framework(monkeypatch):
    def fake(argv,**kwargs):
        if "rev-parse" in argv:
            return subprocess.CompletedProcess(argv,0,"a"*40+"\n","")
        if kwargs.get("check",True):
            raise RuntimeError("git status failed")
        return subprocess.CompletedProcess(argv,1,"","git status failed")
    monkeypatch.setattr(campaign,"command",fake)
    try: campaign.framework_proof(); assert False
    except RuntimeError: pass
    assert campaign.receipt_label([]) == "noncanonical-functional-smoke"
    assert campaign.receipt_label(["teardown failed"]) == "diagnostic-quarantine"

def clean_resource_proof(project):
    label=f"label=com.docker.compose.project={project}"
    commands={
        "containers":["docker","ps","-aq","--filter",label],
        "networks":["docker","network","ls","-q","--filter",label],
        "volumes":["docker","volume","ls","-q","--filter",label],
    }
    return {"project":project,"queryPassed":True,"containers":[],"networks":[],"volumes":[],
            "queries":{key:{"command":argv,"returnCode":0,"stderr":""}
                       for key,argv in commands.items()}}

def configure_main_without_infrastructure(monkeypatch,tmp_path,*,canary_passed,build_error=None):
    source=tmp_path/"source"; source.mkdir(parents=True)
    (source/".source.sha256").write_text("a"*64+"\n")
    (source/campaign.COMPOSE_FILE).write_text("services: {}\n")
    (source/"otelcol.yml").write_text("receivers: {}\n")
    output=tmp_path/"evidence"
    argv=["campaign.py","--output",str(output),"--source",str(source),"--project","obs-main",
          "--port","18080","--canary-project","obs-canary","--canary-port","18081"]
    monkeypatch.setattr(sys,"argv",argv)
    proof={"materializedSourceSha256":"a"*64,"materializationProofSha256":"b"*64,
           "sourceGuardChanges":[]}
    monkeypatch.setattr(campaign,"ensure_materialized",lambda path:proof)
    monkeypatch.setattr(campaign,"framework_proof",lambda:{"frameworkCommit":"c"*40,"dirty":False,
        "provenanceSource":"independently-inspected-local-git-checkout",
        "executorAssertionCrossChecked":False})
    monkeypatch.setattr(campaign,"project_resources",lambda project:clean_resource_proof(project))
    monkeypatch.setattr(campaign,"assert_port_free",lambda port:None)
    if build_error:
        monkeypatch.setattr(campaign,"build_once",lambda *args,**kwargs:(_ for _ in ()).throw(build_error))
    else:
        monkeypatch.setattr(campaign,"build_once",lambda *args,**kwargs:{"images":{}})
    canary={"passed":canary_passed,"collectorRuntime":{"imageId":"sha256:"+"d"*64},
            "blockers":[] if canary_passed else ["parser failed"]}
    monkeypatch.setattr(campaign,"run_acquisition_canary",lambda *args,**kwargs:canary)
    monkeypatch.setattr(campaign,"validate_completed_canary",lambda *args,**kwargs:canary)
    monkeypatch.setattr(campaign,"write_manifest",lambda root:(root/"evidence-manifest.json").write_text("{}\n"))
    return output

def test_canary_failure_and_post_allocation_exception_seal_quarantine(monkeypatch,tmp_path):
    output=configure_main_without_infrastructure(monkeypatch,tmp_path,canary_passed=False)
    called=[]; monkeypatch.setattr(campaign,"run_one",lambda *args,**kwargs:called.append(True))
    assert campaign.main() == 2
    assert called == []
    summary=json.loads((output/"summary.json").read_text())
    assert summary["label"] == "diagnostic-quarantine" and summary["runs"] == 0
    assert (output/"final-hygiene.json").is_file() and (output/"evidence-manifest.json").is_file()

    other=tmp_path/"other"
    output=configure_main_without_infrastructure(
        monkeypatch,other,canary_passed=False,build_error=RuntimeError("build failed"))
    assert campaign.main() == 2
    summary=json.loads((output/"summary.json").read_text())
    assert summary["label"] == "diagnostic-quarantine" and "build failed" in summary["failure"]
    assert (output/"evidence-manifest.json").is_file()

def test_only_complete_three_receipt_cohort_gets_root_smoke_label(monkeypatch,tmp_path):
    output=configure_main_without_infrastructure(monkeypatch,tmp_path,canary_passed=True)
    def fake_run(root,run_id,posture,*args,**kwargs):
        run=root/run_id; run.mkdir(); receipt={"runId":run_id,"posture":posture,"functionalVerdict":"pass"}
        (run/"receipt.json").write_text(json.dumps(receipt)); return receipt
    monkeypatch.setattr(campaign,"run_one",fake_run)
    monkeypatch.setattr(campaign,"validate_completed_receipt",
                        lambda path,run_id,posture,config,image:json.loads(path.read_text()))
    assert campaign.main() == 0
    summary=json.loads((output/"summary.json").read_text())
    assert summary["label"] == "noncanonical-functional-smoke"
    assert summary["plannedRuns"] == summary["runs"] == summary["functionalPasses"] == 3

def test_signal_artifacts_are_recomputed_from_raw_bytes_and_reject_tamper(tmp_path):
    text=native_fixture(); values=signal_inputs(text)
    (tmp_path/"otelcol.log").write_text(text)
    (tmp_path/"otelcol-query.json").write_text(json.dumps(values["query"]))
    (tmp_path/"collector-runtime.json").write_text(json.dumps(values["collector_runtime"]))
    (tmp_path/"acquisition-completeness.json").write_text(
        json.dumps(values["acquisition_completeness"]))
    proof=signal_channel.materialize_run(
        tmp_path,posture="selected",window=values["window"],
        expected_collector_image_id=values["collector_runtime"]["imageId"])
    assert proof["passed"] is True
    before=(tmp_path/"spans-normalized.json").read_bytes()
    (tmp_path/"otelcol.log").write_text(text+"collector error: late corruption\n")
    try:
        signal_channel.validate_run(
            tmp_path,posture="selected",window=values["window"],
            expected_collector_image_id=values["collector_runtime"]["imageId"])
        assert False
    except RuntimeError: pass
    assert (tmp_path/"spans-normalized.json").read_bytes() == before

def test_resume_receipt_is_bound_to_schedule_configuration(tmp_path):
    config={"project":"obs-ob-test","materializedSourceSha256":"a"*64,
            "configurationHashes":{"goalSha256":"b"*64}}
    receipt={"runId":"b01-full","posture":"full","project":"obs-ob-test",
             "source":{"materializedSourceSha256":"a"*64},
             "configurationHashes":{"goalSha256":"b"*64}}
    path=tmp_path/"receipt.json"; path.write_text(json.dumps(receipt))
    assert campaign.validate_existing_receipt(path,"b01-full","full",config)==receipt
    receipt["project"]="other"; path.write_text(json.dumps(receipt))
    try: campaign.validate_existing_receipt(path,"b01-full","full",config); assert False
    except RuntimeError: pass

def test_compose_has_no_global_names_and_builds_source_with_digest_label():
    text=(ROOT/"modules/online-boutique/deployment/compose.observability-placement.yml").read_text()
    assert "container_name:" not in text
    assert "name:" not in "\n".join(line for line in text.splitlines() if "com.observability" not in line) \
        or text.startswith("name: ${OB_COMPOSE_PROJECT")
    assert text.count("com.observability-placement.materialized-source") == 3

def test_workload_validation_and_percentile():
    assert workload.percentile([1,2,3,4],.95)==4
    try: workload.run("http://localhost",math.inf,1,1,1); assert False
    except ValueError: pass

def test_docker_byte_parser_supports_distroless_collector_stats():
    assert campaign.byte_value("0B") == 0
    assert campaign.byte_value("1.25kB") == 1250
    assert campaign.byte_value("2MiB") == 2 * 1024 * 1024
    try: campaign.byte_value("not bytes"); assert False
    except ValueError: pass

def test_runtime_config_mode_is_normalized_under_restrictive_umask(tmp_path):
    source=tmp_path/"source-otelcol.yml"; source.write_text("receivers: {}\n")
    source.chmod(0o600)
    target=tmp_path/"materialized-otelcol.yml"
    previous=os.umask(0o077)
    try:
        proof=materialize.install_runtime_config(source,target)
    finally:
        os.umask(previous)
    assert proof == {target.name:"0644"}
    assert stat.S_IMODE(target.stat().st_mode) == 0o644

def test_source_proof_mode_gate_rejects_nonroot_unreadable_collector_config(tmp_path):
    config=tmp_path/"otelcol.yml"; config.write_text("receivers: {}\n")
    config.chmod(0o600)
    try: campaign.runtime_config_mode_proof(tmp_path); assert False
    except RuntimeError as exc: assert "expected 0644, found 0600" in str(exc)

def test_failure_envelope_captures_stopped_collector_before_teardown(monkeypatch,tmp_path):
    calls=[]
    def fake(argv,**kwargs):
        calls.append(argv)
        if argv[-4:] == ["ps","-a","-q","otel-collector"]:
            return subprocess.CompletedProcess(argv,0,"collector-id\n","")
        if argv[:2] == ["docker","inspect"]:
            return subprocess.CompletedProcess(
                argv,0,'[{"State":{"Status":"exited","ExitCode":1}}]',"")
        if "logs" in argv:
            return subprocess.CompletedProcess(argv,0,"permission denied\n","")
        return subprocess.CompletedProcess(argv,0,"NAME STATUS\n","")
    monkeypatch.setattr(campaign,"command",fake)
    envelope=campaign.capture_failure_envelope(tmp_path,"obs-ob-test",{},tmp_path)
    assert envelope["collectorLogsTailLines"] == 200
    assert envelope["collectorInspect"]["stdout"].startswith('[{"State"')
    assert any(argv[-5:] == ["logs","--no-color","--tail","200","otel-collector"]
               for argv in calls)
    assert json.loads((tmp_path/"failure-envelope.json").read_text()) == envelope


def test_phase1_runner_is_separate_and_freezes_the_first_exact_cell():
    assert campaign.validate(arguments()) == ("none","selected","full")
    assert control_runner.validate(control_arguments()) == (
        "full-reference","frontend-off","source-off")
    for updates in ({"cell":"productcatalog-source-tracing"},{"duration":31},
                    {"rate":2.0},{"seed":20260818},{"project":"obs bad"},{"port":18091}):
        try:
            control_runner.validate(control_arguments(**updates)); assert False
        except ValueError:
            pass


def test_phase1_framework_git_transcript_rejects_a_clean_checked_out_branch(monkeypatch):
    commit="c"*40
    def fake_run(argv,**kwargs):
        if argv[1:3] == ["rev-parse","--verify"]:
            return subprocess.CompletedProcess(argv,0,commit+"\n","")
        if argv[1] == "status":
            return subprocess.CompletedProcess(argv,0,"","")
        if argv[1] == "cat-file":
            return subprocess.CompletedProcess(argv,0,"commit\n","")
        if argv[1] == "symbolic-ref":
            return subprocess.CompletedProcess(argv,0,"refs/heads/main\n","")
        raise AssertionError(argv)
    monkeypatch.setattr(control_runner.subprocess,"run",fake_run)
    try:
        control_runner.framework_git_transcript({"frameworkCommit":commit}); assert False
    except RuntimeError as exc:
        assert "clean detached" in str(exc)


def test_phase1_source_postures_pass_only_their_exact_sensor_targets():
    for posture in ("full-reference","frontend-off","source-off"):
        text=control_carrier(posture)
        result=control_validator.evaluate(text,**control_inputs(posture))
        assert result["passed"] is True, (posture,result["blockers"])
        assert result["stageVector"]["emitted"]["status"] == "unsupported"
        assert result["stageVector"]["transported"]["status"] == "unsupported"
        assert result["stageVector"]["exactVectorComplete"] is False
    values=control_inputs("frontend-off")
    text=control_carrier("frontend-off")+debug_span_batch(
        99,"frontend",datetime.fromisoformat(values["window"]["endedAt"])+timedelta(seconds=1),
        name="GET",kind="Server",attributes={"http.request.method":"GET","url.path":"/"})
    values=control_inputs("frontend-off")
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("forbidden source service" in item for item in result["blockers"])


def test_phase1_validator_rederives_runtime_and_source_control_native_transcripts():
    text=control_carrier("full-reference"); values=control_inputs("full-reference")
    forged="forged-container-id"
    values["query"]["containerId"]=forged
    runtime=values["collector_runtime"]
    runtime["containerId"]=forged
    runtime["acquisitionProof"]["containerLookup"]["stdout"]=forged+"\n"
    runtime["acquisitionProof"]["containerInspect"]["command"]=["docker","inspect",forged]
    runtime["nativeContainerInspect"]={**runtime["nativeContainerInspect"],"Id":forged}
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("retained native inspect JSON" in item for item in result["blockers"])

    values=control_inputs("full-reference")
    service=values["posture_proof"]["services"]["frontend"]
    service["enableTracing"]="0"
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("native inspect JSON for frontend" in item for item in result["blockers"])


def test_phase1_source_proof_rejects_foreign_container_guard_loss_and_unhealthy_state():
    text=control_carrier("full-reference")
    values=control_inputs("full-reference")
    service=values["posture_proof"]["services"]["frontend"]
    foreign="foreign-container"
    service["containerId"]=foreign
    service["composeProjectLabel"]="foreign-project"
    service["composeServiceLabel"]="unrelated-service"
    service["containerLookup"]["stdout"]=foreign+"\n"
    service["containerLookup"]["stdoutBytes"]=len((foreign+"\n").encode())
    service["containerLookup"]["stdoutSha256"]=hashlib.sha256((foreign+"\n").encode()).hexdigest()
    native=json.loads(service["nativeInspect"]["stdout"])[0]
    native["Id"]=foreign
    native["Config"]["Labels"]["com.docker.compose.project"]="foreign-project"
    native["Config"]["Labels"]["com.docker.compose.service"]="unrelated-service"
    native_text=json.dumps([native])
    service["nativeInspect"].update({"command":["docker","inspect",foreign],
        "stdout":native_text,"stdoutBytes":len(native_text.encode()),
        "stdoutSha256":hashlib.sha256(native_text.encode()).hexdigest()})
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("frontend" in item and ("Compose service lookup" in item or
               "enabled proof differs" in item) for item in result["blockers"])

    values=control_inputs("full-reference")
    values["posture_proof"]["guardChangeIds"] = []
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("audited source-guard set" in item for item in result["blockers"])

    values=control_inputs("full-reference")
    service=values["posture_proof"]["services"]["frontend"]
    service["state"]={"running":False,"oomKilled":True,"restartCount":2}
    native=json.loads(service["nativeInspect"]["stdout"])[0]
    native["State"]={"Running":False,"OOMKilled":True}; native["RestartCount"]=2
    native_text=json.dumps([native])
    service["nativeInspect"].update({"stdout":native_text,
        "stdoutBytes":len(native_text.encode()),
        "stdoutSha256":hashlib.sha256(native_text.encode()).hexdigest()})
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("enabled proof differs for frontend" in item for item in result["blockers"])


def test_phase1_stability_replay_rejects_pre_window_and_zero_interval_tails():
    text=control_carrier("source-off")
    values=control_inputs("source-off")
    proof=values["acquisition_completeness"]
    ended=datetime.fromisoformat(values["window"]["endedAt"])
    shifted=(ended-timedelta(seconds=4),ended-timedelta(seconds=2),ended+timedelta(seconds=12))
    proof["attempts"]=[{**row,"capturedAt":captured.isoformat()}
                       for row,captured in zip(proof["attempts"],shifted)]
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("post-window observations" in item for item in result["blockers"])

    values=control_inputs("source-off"); proof=values["acquisition_completeness"]
    identical=(ended+timedelta(seconds=12)).isoformat()
    proof["attempts"]=[{**row,"capturedAt":identical} for row in proof["attempts"]]
    proof["observedUntil"]=identical
    result=control_validator.evaluate(text,**values)
    assert result["passed"] is False
    assert any("strictly increasing" in item or "poll interval" in item
               for item in result["blockers"])


def test_phase1_terminal_replay_rejects_retained_carrier_tamper(tmp_path):
    posture="frontend-off"; text=control_carrier(posture); run=tmp_path/"run"
    values=write_control_inputs(run,control_inputs(posture))
    proof=control_validator.materialize_run(
        run,cell="frontend-source-tracing",posture=posture,window=values["window"])
    assert proof["passed"] is True
    normalized=(run/"spans-normalized.json").read_bytes()
    (run/"otelcol.log").write_text(text+"late corrupt carrier\n")
    try:
        control_validator.validate_run(
            run,cell="frontend-source-tracing",posture=posture,window=values["window"])
        assert False
    except RuntimeError:
        pass
    assert (run/"spans-normalized.json").read_bytes() == normalized


def test_phase1_adapter_projects_schema_valid_but_descriptive_only_observations(tmp_path):
    root=tmp_path/"control-root"; root.mkdir()
    (root/"schedule.json").write_text(json.dumps({"cell":"frontend-source-tracing"}))
    observations=[]; baseline=None
    for index,posture in enumerate(("full-reference","frontend-off","source-off"),1):
        run=root/f"c0{index}-{posture}"; run.mkdir()
        values=control_inputs(posture); evaluation=control_validator.evaluate(
            control_carrier(posture),**values)
        for filename,payload in (("posture-proof.json",values["posture_proof"]),
                                 ("otelcol-query.json",values["query"]),
                                 ("collector-runtime.json",values["collector_runtime"]),
                                 ("control-evaluation.json",evaluation),
                                 ("teardown.json",clean_resource_proof("obs-ob-test"))):
            (run/filename).write_text(json.dumps(payload))
        (run/"otelcol.log").write_text(control_carrier(posture))
        receipt={"runId":run.name,"posture":posture,
            "completedAt":"2026-08-17T01:01:00+00:00",
            "source":{"frameworkCommit":"a"*40,"upstreamSha":"b"*40},
            "window":values["window"],"postureProof":values["posture_proof"],
            "controlEvaluation":evaluation,
            "teardown":{"projectClean":True}}
        observation=control_observation.build(
            run,receipt,baseline=baseline if posture=="frontend-off" else None)
        assert control_root._schema_errors(observation) == []
        assert observation["runIdentity"]["artifactRoot"] == run.name
        assert observation["runIdentity"]["artifactSha256"] == \
            control_observation.artifact_identity(observation["evidenceItems"])
        assert all(not Path(item["locator"]).is_absolute() and
                   ".." not in Path(item["locator"]).parts
                   for item in observation["evidenceItems"])
        by_id={item["id"]:item for item in observation["evidenceItems"]}
        assert by_id["run-evaluation"]["kind"] == "test"
        assert by_id["run-collector"]["kind"] == "collector-output"
        assert set(observation["stages"]["retained"]["evidenceItems"]) == {
            "run-collector","run-collector-query","run-collector-runtime","run-evaluation"}
        assert by_id["run-collector"]["capturedAt"] == \
            values["acquisition_completeness"]["observedUntil"]
        assert by_id["run-runtime"]["capturedAt"] == "not-recorded"
        assert all(control_observation.evidence_verifier(root)(item)
                   for item in observation["evidenceItems"])
        if posture=="full-reference": baseline=observation
        observations.append(observation)
    report=control_root._generic_evaluator()(
        json.loads((ROOT/"modules/online-boutique/activation/control-universe.json").read_text()),
        observations,evidence_verifier=control_root._evidence_verifier(root))
    assert report["valid"] is True, report["errors"]
    assert report["complete"] is False
    assert report["claimCeiling"] == "descriptive-only"
    assert report["policy"]["empiricalClaimsAllowed"] is False
    assert report["policy"]["optimizationClaimsAllowed"] is False
    assert {row["microtestId"] for row in observations} == {
        "full-reference","perturb-frontend-source-tracing","true-source-off"}
    assert all(row["stages"]["emitted"]["state"] == "unsupported" and
               row["stages"]["transported"]["state"] == "unsupported"
               for row in observations)


def test_phase1_observation_verifier_rejects_escape_absolute_and_symlink(tmp_path):
    root=tmp_path/"evidence"; root.mkdir()
    artifact=root/"proof.json"; artifact.write_text("{}")
    item={"locator":"proof.json","sha256":control_observation.sha256(artifact)}
    verify=control_observation.evidence_verifier(root)
    assert verify(item)
    assert not verify({**item,"locator":str(artifact.resolve())})
    assert not verify({**item,"locator":"../proof.json"})
    link=root/"link.json"; link.symlink_to(artifact)
    assert not verify({**item,"locator":"link.json"})


def synthetic_control_root(tmp_path):
    tmp_path.mkdir(parents=True,exist_ok=True)
    source=tmp_path/"materialized-source"; source.mkdir()
    compose=source/campaign.COMPOSE_FILE; compose.write_text("services: {}\n")
    root=tmp_path/"terminal-control-root"; root.mkdir()
    framework_root=tmp_path/"captured-framework"
    captured_workload=framework_root/control_runner.WORKLOAD_RELATIVE_PATH
    captured_workload.parent.mkdir(parents=True)
    shutil.copyfile(control_runner.WORKLOAD_PATH,captured_workload)
    digest="a"*64
    guard_rows=[{"id":item} for item in sorted(control_validator.EXPECTED_GUARD_IDS)]
    sentinel={"schemaVersion":1,"upstreamCommit":campaign.UPSTREAM_SHA,
        "sourceCheckoutClean":True,"materializedSourceSha256":digest,
        "runtimeConfigModes":{"otelcol.yml":"0644"},"sourceGuardChanges":guard_rows}
    (root/"materialization-sentinel.json").write_text(
        json.dumps(sentinel,indent=2,sort_keys=True)+"\n")
    source_proof={**sentinel,"materializationProofSha256":campaign.sha256(
        root/"materialization-sentinel.json")}
    (root/"source-proof.json").write_text(json.dumps(source_proof,indent=2,sort_keys=True)+"\n")
    (root/"materialized-source.sha256").write_text(digest+"\n")
    shutil.copyfile(compose,root/"source-compose.yml")
    framework={"frameworkCommit":"a"*40,"dirty":False,
               "provenanceSource":"independently-inspected-local-git-checkout",
               "executorAssertionCrossChecked":True}
    (root/"framework-proof.json").write_text(json.dumps(framework,indent=2,sort_keys=True)+"\n")
    framework_git={"schemaVersion":2,"workingDirectoryRole":"framework-root",
        "workingDirectory":str(framework_root.resolve()),"commands":{
        "revParse":{"command":["git","rev-parse","--verify","HEAD^{commit}"],
            "returnCode":0,"stdout":"a"*40+"\n","stderr":""},
        "status":{"command":["git","status","--porcelain=v1","--untracked-files=all"],
            "returnCode":0,"stdout":"","stderr":""},
        "objectType":{"command":["git","cat-file","-t","a"*40],
            "returnCode":0,"stdout":"commit\n","stderr":""},
        "symbolicHead":{"command":["git","symbolic-ref","-q","HEAD"],
            "returnCode":1,"stdout":"","stderr":""}}}
    (root/"framework-git.json").write_text(
        json.dumps(framework_git,indent=2,sort_keys=True)+"\n")
    python_runtime=control_runner.python_runtime_transcript()
    (root/"python-runtime.json").write_text(
        json.dumps(python_runtime,indent=2,sort_keys=True)+"\n")
    hashes={"matrixSha256":campaign.sha256(control_runner.MATRIX_PATH),
        "targetSha256":campaign.sha256(control_runner.TARGET_PATH),
        "channelSha256":campaign.sha256(control_runner.CHANNEL_PATH),
        "normalizerSha256":campaign.sha256(control_runner.NORMALIZER_PATH),
        "validatorSha256":campaign.sha256(control_runner.VALIDATOR_PATH),
        "runnerSha256":campaign.sha256(control_runner.Path(control_runner.__file__)),
        "rootValidatorSha256":campaign.sha256(control_runner.ROOT_VALIDATOR_PATH),
        "observationBuilderSha256":campaign.sha256(control_runner.OBSERVATION_BUILDER_PATH),
        "controlUniverseSha256":campaign.sha256(control_runner.CONTROL_UNIVERSE_PATH),
        "workloadSha256":campaign.sha256(control_runner.WORKLOAD_PATH),
        "composeSha256":campaign.sha256(root/"source-compose.yml"),
        "frameworkGitSha256":campaign.sha256(root/"framework-git.json"),
        "pythonRuntimeTranscriptSha256":campaign.sha256(root/"python-runtime.json"),
        "pythonExecutableSha256":python_runtime["fileSha256"]}
    command_bindings={"schemaVersion":1,
        "frameworkRoot":str(framework_root.resolve()),
        "evidenceRoot":str(root.resolve()),
        "pythonExecutable":python_runtime["resolvedExecutable"],
        "workloadScript":control_runner.WORKLOAD_RELATIVE_PATH.as_posix()}
    configuration={"schemaVersion":1,"sut":"online-boutique",
        "cell":"frontend-source-tracing",
        "qualificationCeiling":"noncanonical-functional-characterization",
        "registersAsEvidence":False,"project":"obs-ob-test","frontendPort":18090,
        "canaryProject":"obs-ob-test-canary","canaryFrontendPort":18091,
        "seed":20260817,"postures":["full-reference","frontend-off","source-off"],
        "warmupSeconds":15.0,"measurementSeconds":30.0,"requestsPerSecond":1.0,
        "concurrency":4,"expectedOfferedRequests":30,"fault":None,
        "materializedSourcePath":str(source.resolve()),
        "materializedSourceSha256":digest,"upstreamSha":campaign.UPSTREAM_SHA,
        "framework":framework,"configurationHashes":hashes,
        "commandBindings":command_bindings,
        "rawTranscriptTrustBoundary":control_runner.RAW_TRANSCRIPT_TRUST_BOUNDARY}
    order=["full-reference","frontend-off","source-off"]
    import random as _random
    _random.Random(20260817).shuffle(order)
    schedule_runs=[{"runId":f"c{index:02d}-{posture}","posture":posture}
                   for index,posture in enumerate(order,1)]
    schedule={"configuration":configuration,"runs":schedule_runs}
    (root/"schedule.json").write_text(json.dumps(schedule,indent=2,sort_keys=True)+"\n")
    projects={name:clean_resource_proof(name) for name in
              (configuration["project"],configuration["canaryProject"])}
    (root/"preflight.json").write_text(json.dumps({"schemaVersion":1,
        "capturedAt":"2026-08-17T00:00:00+00:00","projects":projects,
        "sourceProof":source_proof,"framework":framework,
        "pythonRuntime":python_runtime,
        "rawTranscriptTrustBoundary":control_runner.RAW_TRANSCRIPT_TRUST_BOUNDARY,
        "configuration":configuration},
        indent=2,sort_keys=True)+"\n")

    template=control_inputs("full-reference")["build"]
    build={**template,"builtAt":"2026-08-17T00:00:01+00:00",
           "composeSha256":hashes["composeSha256"]}
    (root/"build.json").write_text(json.dumps(build,indent=2,sort_keys=True)+"\n")
    build_sha=campaign.sha256(root/"build.json")

    def rows_and_workload(count,duration,url,started):
        start=datetime.fromisoformat(started).timestamp()
        rows=[{"scheduledAtEpoch":start+index,"startedAtEpoch":start+index+0.01,
               "endedAtEpoch":start+index+0.02,"status":200,"bytes":100,"error":None}
              for index in range(count)]
        return {"scenario":"homepage","url":url,"ratePerSecond":1.0,
                "durationSeconds":float(duration),"concurrency":4,
                "offered":count,"completed":count,"failed":0,"requests":rows}

    def bind_runtime(values,project):
        query=values["query"]; query["project"]=project
        query["composePath"]=str(compose.resolve()); query["composeSha256"]=hashes["composeSha256"]
        query["command"]=["docker","compose","-p",project,"-f",str(compose.resolve()),
                          "logs","--no-color","--since",values["window"]["startedAt"],
                          "otel-collector"]
        runtime=values["collector_runtime"]; runtime["composeProjectLabel"]=project
        runtime["nativeContainerInspect"]["Config"]["Labels"][
            "com.docker.compose.project"]=project
        native=json.dumps([runtime["nativeContainerInspect"]])
        inspect=runtime["acquisitionProof"]["containerInspect"]
        inspect.update({"stdout":native,"stdoutBytes":len(native.encode()),
                        "stdoutSha256":hashlib.sha256(native.encode()).hexdigest()})
        runtime["acquisitionProof"]["containerLookup"]["command"]=[
            "docker","compose","-p",project,"-f",str(compose.resolve()),
            "ps","-q","otel-collector"]
        proof=values.get("posture_proof")
        if proof:
            proof["buildReceiptSha256"]=build_sha
            for service,row in proof["services"].items():
                row["composeProjectLabel"]=project
                lookup=row["containerLookup"]
                lookup["command"]=["docker","compose","-p",project,"-f",str(compose.resolve()),
                                   "ps","-q",service]
                native_row=json.loads(row["nativeInspect"]["stdout"])[0]
                native_row["Config"]["Labels"]["com.docker.compose.project"]=project
                native_text=json.dumps([native_row])
                row["nativeInspect"].update({"stdout":native_text,
                    "stdoutBytes":len(native_text.encode()),
                    "stdoutSha256":hashlib.sha256(native_text.encode()).hexdigest()})
        return values

    # Retain and validate the real Phase-0 acquisition canary before control runs.
    canary=root/"acquisition-canary"; canary.mkdir()
    (canary/"ownership-preflight.json").write_text(json.dumps(
        clean_resource_proof(configuration["canaryProject"]),indent=2,sort_keys=True)+"\n")
    carrier=native_fixture(); signal=signal_inputs(carrier)
    canary_started="2026-08-08T16:09:18+00:00"; canary_ended="2026-08-08T16:09:33+00:00"
    signal["window"]={"startedAt":canary_started,"endedAt":canary_ended}
    signal=bind_prefix_history([carrier]*3,(12,14,16),posture="selected")
    # bind_prefix_history restores its native 11s window; widen and recompute the stable witness.
    signal["window"]={"startedAt":canary_started,"endedAt":canary_ended}
    parsed=normalizer.parse_detailed(carrier)
    semantics=signal_channel.snapshot_semantics(parsed["spans"],window=signal["window"],
        posture="selected",channel=signal["channel"],target=signal["target"])
    captured=[(datetime.fromisoformat(canary_ended)+timedelta(seconds=x)).isoformat()
              for x in (12,14,16)]
    for attempt,capture in zip(signal["acquisition_completeness"]["attempts"],captured):
        attempt["capturedAt"]=capture; attempt["claimProjection"]=semantics["claimProjection"]
        attempt["postWindowTail"]=semantics["postWindowTail"]
    signal["acquisition_completeness"].update({"windowStartedAt":canary_started,
        "windowEndedAt":canary_ended,"observedUntil":captured[-1],"observationSeconds":16.0,
        "terminalCarrier":semantics["carrier"],"terminalClaimProjection":semantics["claimProjection"],
        "terminalPostWindowTail":semantics["postWindowTail"]})
    signal["query"]["since"]=canary_started
    signal=bind_runtime(signal,configuration["canaryProject"])
    for filename,key in (("otelcol-query.json","query"),("collector-runtime.json","collector_runtime"),
                         ("acquisition-completeness.json","acquisition_completeness")):
        (canary/filename).write_text(json.dumps(signal[key],indent=2,sort_keys=True)+"\n")
    (canary/"otelcol.log").write_text(carrier)
    canary_posture=control_inputs("full-reference")["posture_proof"]
    canary_posture={"requested":"selected","sourceGuarded":True,
        "guardChangeIds":sorted(control_validator.EXPECTED_GUARD_IDS),
        "services":canary_posture["services"]}
    selected=json.loads((ROOT/"modules/online-boutique/activation/catalog.json").read_text())[
        "postures"]["selected"]
    for service,control in (("frontend","frontend"),("productcatalogservice","productcatalog"),
                            ("currencyservice","currency")):
        row=canary_posture["services"][service]
        row["enableTracing"]=row["expectedEnableTracing"]=selected[control]
    (canary/"posture-proof.json").write_text(
        json.dumps(canary_posture,indent=2,sort_keys=True)+"\n")
    canary_workload=rows_and_workload(15,15,"http://127.0.0.1:18091/",canary_started)
    (canary/"workload.json").write_text(json.dumps(canary_workload,indent=2,sort_keys=True)+"\n")
    signal_eval=signal_channel.materialize_run(canary,posture="selected",
        window=signal["window"],expected_collector_image_id=signal["collector_runtime"]["imageId"])
    canary_teardown=clean_resource_proof(configuration["canaryProject"])
    canary_down={"schemaVersion":1,"command":["docker","compose","-p",
        configuration["canaryProject"],"-f",str(compose.resolve()),"down","--remove-orphans"],
        "returnCode":0,"stdout":"","stderr":""}
    (canary/"teardown.json").write_text(json.dumps(canary_teardown,indent=2,sort_keys=True)+"\n")
    (canary/"down-command.json").write_text(json.dumps(canary_down,indent=2,sort_keys=True)+"\n")
    canary_result={"schemaVersion":1,"project":configuration["canaryProject"],
        "frontendPort":18091,"window":signal["window"],
        "workload":{key:canary_workload[key] for key in
                    ("offered","completed","failed","ratePerSecond","durationSeconds")},
        "postureProof":canary_posture,"collectorRuntime":signal["collector_runtime"],
        "collectorRxBytesBefore":100,"collectorRxBytesAfter":200,
        "signalChannel":signal_eval,"blockers":[],"passed":True,
        "teardown":{"downCommand":canary_down,"projectResources":canary_teardown,
                    "projectClean":True}}
    canary_result["artifacts"]=campaign.artifact_hashes(canary)
    (canary/"canary-result.json").write_text(json.dumps(canary_result,indent=2,sort_keys=True)+"\n")

    for scheduled in schedule_runs:
        posture=scheduled["posture"]; run=root/scheduled["runId"]; run.mkdir()
        text=control_carrier(posture); values=bind_runtime(control_inputs(posture),"obs-ob-test")
        values["build"]=build; values["build_sha256"]=build_sha
        for filename,payload in (("otelcol-query.json",values["query"]),
            ("collector-runtime.json",values["collector_runtime"]),
            ("acquisition-completeness.json",values["acquisition_completeness"]),
            ("posture-proof.json",values["posture_proof"])):
            (run/filename).write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
        (run/"otelcol.log").write_text(text)
        evaluation=control_validator.materialize_run(
            run,cell="frontend-source-tracing",posture=posture,window=values["window"])
        workload=rows_and_workload(30,30,"http://127.0.0.1:18090/",
                                   values["window"]["startedAt"])
        (run/"workload.json").write_text(json.dumps(workload,indent=2,sort_keys=True)+"\n")
        warmup_started="2026-08-17T00:59:30+00:00"; warmup_ended="2026-08-17T00:59:45+00:00"
        warmup=rows_and_workload(15,15,"http://127.0.0.1:18090/",warmup_started)
        (run/"warmup.json").write_text(json.dumps(warmup,indent=2,sort_keys=True)+"\n")
        for stem,duration,started,ended in (("warmup",15,warmup_started,warmup_ended),
            ("workload",30,values["window"]["startedAt"],values["window"]["endedAt"])):
            argv=[python_runtime["resolvedExecutable"],
                  str(framework_root/control_runner.WORKLOAD_RELATIVE_PATH),
                  "--url","http://127.0.0.1:18090/","--rate","1.0","--duration",str(float(duration)),
                  "--concurrency","4","--output",str(root/scheduled["runId"]/f"{stem}.json")]
            (run/f"{stem}-command.json").write_text(json.dumps({"schemaVersion":1,
                "command":argv,"startedAt":started,"endedAt":ended,"returnCode":0,
                "stdout":"","stderr":""},indent=2,sort_keys=True)+"\n")
        (run/"ownership-preflight.json").write_text(json.dumps(
            clean_resource_proof("obs-ob-test"),indent=2,sort_keys=True)+"\n")
        teardown=clean_resource_proof("obs-ob-test")
        down={"schemaVersion":1,"command":["docker","compose","-p","obs-ob-test","-f",
              str(compose.resolve()),"down","--remove-orphans"],"returnCode":0,
              "stdout":"","stderr":""}
        (run/"teardown.json").write_text(json.dumps(teardown,indent=2,sort_keys=True)+"\n")
        (run/"down-command.json").write_text(json.dumps(down,indent=2,sort_keys=True)+"\n")
        receipt={"schemaVersion":1,"runId":scheduled["runId"],"sut":"online-boutique",
            "cell":"frontend-source-tracing","posture":posture,"project":"obs-ob-test",
            "completedAt":"2026-08-17T01:01:00+00:00",
            "source":{"upstreamSha":campaign.UPSTREAM_SHA,"frameworkCommit":"a"*40,
                "frameworkDirty":False,"frameworkProvenanceSource":framework["provenanceSource"],
                "materializedSourceSha256":digest},"configurationHashes":hashes,
            "window":values["window"],
            "warmup":{key:warmup[key] for key in ("scenario","url","ratePerSecond",
                "durationSeconds","concurrency","offered","completed","failed")},
            "workload":{key:workload[key] for key in ("scenario","url","ratePerSecond",
                "durationSeconds","concurrency","offered","completed","failed")},
            "postureProof":values["posture_proof"],"controlEvaluation":evaluation,
            "technicalBlockers":[],"qualification":{
                "label":"noncanonical-functional-characterization","registersAsEvidence":False,
                "scope":"one no-fault source-control cell; no effect or optimization inference",
                "prohibitedClaims":json.loads(control_runner.MATRIX_PATH.read_text())["prohibitedClaims"]},
            "functionalVerdict":"pass","teardown":{"downCommand":down,
                "projectResources":teardown,"projectClean":True}}
        receipt["artifacts"]=campaign.artifact_hashes(run)
        (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    final_projects={name:clean_resource_proof(name) for name in
                    (configuration["project"],configuration["canaryProject"])}
    (root/"final-hygiene.json").write_text(json.dumps({"schemaVersion":1,
        "capturedAt":"2026-08-17T01:02:00+00:00","projects":final_projects,
        "projectClean":True},indent=2,sort_keys=True)+"\n")
    summary={"schemaVersion":1,"label":"noncanonical-functional-characterization",
        "cell":"frontend-source-tracing","plannedRuns":3,"runs":3,"functionalPasses":3,
        "acquisitionCanaryPassed":True,"projectClean":True,"registersAsEvidence":False,
        "failure":None,"claimBoundary":control_root.EXACT_CLAIM_BOUNDARY}
    (root/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    control_root.build_observations(root)
    campaign.write_manifest(root)
    return root


def reseal_control_root(root):
    campaign.write_manifest(root)


def refresh_control_receipt(run):
    receipt=json.loads((run/"receipt.json").read_text())
    receipt["artifacts"]=campaign.artifact_hashes(run)
    (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")


def rewrite_python_binding(root, executable, *, python_runtime=None,
                           executable_sha256=None):
    """Coherently reseal derived Python claims for adversarial tests."""
    if python_runtime is None:
        python_runtime=json.loads((root/"python-runtime.json").read_text())
    else:
        (root/"python-runtime.json").write_text(
            json.dumps(python_runtime,indent=2,sort_keys=True)+"\n")
    schedule=json.loads((root/"schedule.json").read_text())
    configuration=schedule["configuration"]
    configuration["commandBindings"]["pythonExecutable"]=executable
    hashes=configuration["configurationHashes"]
    hashes["pythonRuntimeTranscriptSha256"]=campaign.sha256(root/"python-runtime.json")
    hashes["pythonExecutableSha256"]=(executable_sha256 if executable_sha256 is not None
        else python_runtime["fileSha256"])
    (root/"schedule.json").write_text(
        json.dumps(schedule,indent=2,sort_keys=True)+"\n")
    preflight=json.loads((root/"preflight.json").read_text())
    preflight["configuration"]=configuration
    preflight["pythonRuntime"]=python_runtime
    (root/"preflight.json").write_text(
        json.dumps(preflight,indent=2,sort_keys=True)+"\n")
    for run in (path for path in root.iterdir()
                if path.is_dir() and path.name.startswith("c0")):
        for name in ("warmup-command.json","workload-command.json"):
            command=json.loads((run/name).read_text())
            command["command"][0]=executable
            (run/name).write_text(json.dumps(command,indent=2,sort_keys=True)+"\n")
        receipt=json.loads((run/"receipt.json").read_text())
        receipt["configurationHashes"]=hashes
        (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
        refresh_control_receipt(run)
    control_root.build_observations(root)
    reseal_control_root(root)


def test_phase1_root_replays_every_receipt_projection_and_manifest(tmp_path):
    root=synthetic_control_root(tmp_path)
    result=control_root.validate_root(root)
    assert result["internalValid"] is True, result
    assert result["terminalObservationCount"] == 3
    assert result["blindStages"] == ["emitted","transported"]
    rows=json.loads((root/"control-observations.json").read_text())
    rows[0]["stages"]["retained"]["count"] += 1
    (root/"control-observations.json").write_text(json.dumps(rows))
    tampered=control_root.validate_root(root)
    assert tampered["internalValid"] is False
    assert tampered["projectionMatches"] is False
    assert tampered["manifestMatches"] is False


def test_phase1_root_rejects_schedule_drift_missing_prerequisite_and_extra_attempt(tmp_path):
    root=synthetic_control_root(tmp_path)
    original=json.loads((root/"schedule.json").read_text())
    for key,value in (("measurementSeconds",29.0),("warmupSeconds",14.0),
                      ("requestsPerSecond",2.0),("concurrency",3),
                      ("expectedOfferedRequests",29),("seed",20260818),("fault",{})):
        schedule=json.loads(json.dumps(original)); schedule["configuration"][key]=value
        (root/"schedule.json").write_text(json.dumps(schedule,indent=2,sort_keys=True)+"\n")
        try: control_root.validate_root(root); assert False
        except RuntimeError as exc: assert "exact reviewed cell" in str(exc)
    (root/"schedule.json").write_text(json.dumps(original,indent=2,sort_keys=True)+"\n")

    for index,name in enumerate(("preflight.json","build.json","final-hygiene.json",
                                 "framework-git.json"),1):
        missing=synthetic_control_root(tmp_path/f"missing-{index}")
        (missing/name).unlink(); reseal_control_root(missing)
        result=control_root.validate_root(missing)
        assert result["internalValid"] is False
        assert result["rootPrerequisitesValid"] is False
    missing_canary=synthetic_control_root(tmp_path/"missing-canary")
    shutil.rmtree(missing_canary/"acquisition-canary"); reseal_control_root(missing_canary)
    result=control_root.validate_root(missing_canary)
    assert result["internalValid"] is False
    assert result["rootPrerequisitesValid"] is False

    extra=synthetic_control_root(tmp_path/"extra")
    discarded=extra/"discarded-attempt"; discarded.mkdir()
    (discarded/"receipt.json").write_text(json.dumps({"functionalVerdict":"blocked"})+"\n")
    reseal_control_root(extra)
    result=control_root.validate_root(extra)
    assert result["internalValid"] is False
    assert any("unscheduled" in item for item in result["rootErrors"])


def test_phase1_root_rejects_burst_cadence_and_missing_ownership_preflight(tmp_path):
    root=synthetic_control_root(tmp_path)
    run=next(path for path in root.iterdir() if path.is_dir() and path.name.startswith("c0"))
    workload=json.loads((run/"workload.json").read_text())
    first=workload["requests"][0]["scheduledAtEpoch"]
    for row in workload["requests"]:
        row["scheduledAtEpoch"]=first
        row["startedAtEpoch"]=max(row["startedAtEpoch"],first)
    (run/"workload.json").write_text(json.dumps(workload,indent=2,sort_keys=True)+"\n")
    refresh_control_receipt(run); reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("cadence" in item or "strictly ordered" in item
               for item in result["receiptErrors"])

    missing=synthetic_control_root(tmp_path/"ownership")
    run=next(path for path in missing.iterdir() if path.is_dir() and path.name.startswith("c0"))
    (run/"ownership-preflight.json").unlink()
    refresh_control_receipt(run); reseal_control_root(missing)
    result=control_root.validate_root(missing)
    assert result["internalValid"] is False
    assert any("ownership-preflight" in item for item in result["receiptErrors"])


def test_phase1_root_rejects_coherent_no_fault_request_failure(tmp_path):
    root=synthetic_control_root(tmp_path)
    run=next(path for path in root.iterdir() if path.is_dir() and path.name.startswith("c0"))
    workload=json.loads((run/"workload.json").read_text())
    workload["requests"][0].update({"status":None,"bytes":0,"error":"Timeout"})
    workload["completed"]=29; workload["failed"]=1
    (run/"workload.json").write_text(json.dumps(workload,indent=2,sort_keys=True)+"\n")
    receipt=json.loads((run/"receipt.json").read_text())
    receipt["workload"].update({"completed":29,"failed":1})
    (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    refresh_control_receipt(run); reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("without failure" in item or "successful 2xx" in item
               for item in result["receiptErrors"])

    canary_workload=json.loads((root/"acquisition-canary"/"workload.json").read_text())
    canary_workload["requests"][0].update({"status":503,"error":None})
    blockers=control_runner.phase1_workload_blockers(
        canary_workload,
        expected={"scenario":"homepage","url":"http://127.0.0.1:18091/",
                  "ratePerSecond":1.0,"durationSeconds":15.0,"concurrency":4},
        window={"startedAt":"2026-08-08T16:09:18+00:00",
                "endedAt":"2026-08-08T16:09:33+00:00"},
        expected_offered=15)
    assert "no-fault workload rows must all retain successful 2xx outcomes" in blockers


def test_phase1_root_rejects_self_asserted_framework_provenance(tmp_path):
    root=synthetic_control_root(tmp_path)
    framework=json.loads((root/"framework-proof.json").read_text())
    framework["provenanceSource"]="executor-self-asserted"
    framework["executorAssertionCrossChecked"]=False
    (root/"framework-proof.json").write_text(json.dumps(framework,indent=2,sort_keys=True)+"\n")
    schedule=json.loads((root/"schedule.json").read_text())
    schedule["configuration"]["framework"]=framework
    (root/"schedule.json").write_text(json.dumps(schedule,indent=2,sort_keys=True)+"\n")
    preflight=json.loads((root/"preflight.json").read_text())
    preflight["framework"]=framework; preflight["configuration"]=schedule["configuration"]
    (root/"preflight.json").write_text(json.dumps(preflight,indent=2,sort_keys=True)+"\n")
    reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("framework proof" in item for item in result["rootErrors"])

    branch=synthetic_control_root(tmp_path/"branch")
    transcript=json.loads((branch/"framework-git.json").read_text())
    transcript["commands"]["symbolicHead"].update(
        {"returnCode":0,"stdout":"refs/heads/main\n"})
    (branch/"framework-git.json").write_text(
        json.dumps(transcript,indent=2,sort_keys=True)+"\n")
    schedule=json.loads((branch/"schedule.json").read_text())
    schedule["configuration"]["configurationHashes"]["frameworkGitSha256"]=campaign.sha256(
        branch/"framework-git.json")
    (branch/"schedule.json").write_text(json.dumps(schedule,indent=2,sort_keys=True)+"\n")
    preflight=json.loads((branch/"preflight.json").read_text())
    preflight["configuration"]=schedule["configuration"]
    (branch/"preflight.json").write_text(json.dumps(preflight,indent=2,sort_keys=True)+"\n")
    reseal_control_root(branch)
    result=control_root.validate_root(branch)
    assert result["internalValid"] is False
    assert any("framework Git transcript" in item for item in result["rootErrors"])


def test_phase1_root_rejects_receipt_claim_and_identity_rewrites(tmp_path):
    root=synthetic_control_root(tmp_path)
    run=next(path for path in root.iterdir() if path.is_dir() and path.name.startswith("c0"))
    receipt=json.loads((run/"receipt.json").read_text())
    receipt["qualification"]["scope"]="canonical optimization result"
    receipt["qualification"]["prohibitedClaims"]=[]
    (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("characterization ceiling" in item for item in result["receiptErrors"])

    identity=synthetic_control_root(tmp_path/"identity")
    run=next(path for path in identity.iterdir()
             if path.is_dir() and path.name.startswith("c0"))
    receipt=json.loads((run/"receipt.json").read_text())
    receipt["schemaVersion"]=999; receipt["sut"]="teastore"
    (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    reseal_control_root(identity)
    result=control_root.validate_root(identity)
    assert result["internalValid"] is False
    assert any("receipt identity" in item for item in result["receiptErrors"])


def test_phase1_command_binding_survives_validator_checkout_relocation(
        tmp_path,monkeypatch):
    root=synthetic_control_root(tmp_path)
    real_load=control_root.load
    relocated_runner=real_load(
        "ob_control_root_runner_relocated",control_runner.Path(control_runner.__file__))
    relocated_runner.MODULE=Path("/opt/external-adjudicator/modules/online-boutique")

    def relocated_load(name,path):
        return relocated_runner if name == "ob_control_root_runner" else real_load(name,path)

    monkeypatch.setattr(control_root,"load",relocated_load)
    result=control_root.validate_root(root)
    assert result["internalValid"] is True,result


def test_phase1_command_binding_rejects_foreign_matching_suffix(tmp_path):
    root=synthetic_control_root(tmp_path)
    run=next(path for path in root.iterdir()
             if path.is_dir() and path.name.startswith("c0"))
    command=json.loads((run/"warmup-command.json").read_text())
    command["command"][1]="/tmp/foreign/modules/online-boutique/workload/fixed_home.py"
    (run/"warmup-command.json").write_text(
        json.dumps(command,indent=2,sort_keys=True)+"\n")
    refresh_control_receipt(run)
    control_root.build_observations(root); reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("warmup command differs" in item for item in result["receiptErrors"])


def test_phase1_command_binding_rejects_workload_digest_drift(tmp_path):
    root=synthetic_control_root(tmp_path)
    schedule=json.loads((root/"schedule.json").read_text())
    schedule["configuration"]["configurationHashes"]["workloadSha256"]="f"*64
    (root/"schedule.json").write_text(json.dumps(schedule,indent=2,sort_keys=True)+"\n")
    preflight=json.loads((root/"preflight.json").read_text())
    preflight["configuration"]=schedule["configuration"]
    (root/"preflight.json").write_text(json.dumps(preflight,indent=2,sort_keys=True)+"\n")
    for run in (path for path in root.iterdir()
                if path.is_dir() and path.name.startswith("c0")):
        receipt=json.loads((run/"receipt.json").read_text())
        receipt["configurationHashes"]=schedule["configuration"]["configurationHashes"]
        (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    control_root.build_observations(root); reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("workload digest" in item for item in result["rootErrors"])
    assert all("current reviewed bytes" in item for item in result["receiptErrors"])


def test_phase1_command_binding_rejects_same_run_output_root_drift(tmp_path):
    root=synthetic_control_root(tmp_path)
    run=next(path for path in root.iterdir()
             if path.is_dir() and path.name.startswith("c0"))
    command=json.loads((run/"workload-command.json").read_text())
    command["command"][11]=f"/tmp/foreign/{run.name}/workload.json"
    (run/"workload-command.json").write_text(
        json.dumps(command,indent=2,sort_keys=True)+"\n")
    refresh_control_receipt(run)
    control_root.build_observations(root); reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("measurement command differs" in item for item in result["receiptErrors"])


def test_phase1_command_binding_rejects_legacy_unbound_schedule(tmp_path):
    root=synthetic_control_root(tmp_path)
    transcript=json.loads((root/"framework-git.json").read_text())
    transcript["schemaVersion"]=1; transcript.pop("workingDirectory")
    (root/"framework-git.json").write_text(
        json.dumps(transcript,indent=2,sort_keys=True)+"\n")
    schedule=json.loads((root/"schedule.json").read_text())
    schedule["configuration"].pop("commandBindings")
    hashes=schedule["configuration"]["configurationHashes"]
    hashes.pop("workloadSha256")
    hashes["frameworkGitSha256"]=campaign.sha256(root/"framework-git.json")
    (root/"schedule.json").write_text(json.dumps(schedule,indent=2,sort_keys=True)+"\n")
    preflight=json.loads((root/"preflight.json").read_text())
    preflight["configuration"]=schedule["configuration"]
    (root/"preflight.json").write_text(json.dumps(preflight,indent=2,sort_keys=True)+"\n")
    for run in (path for path in root.iterdir()
                if path.is_dir() and path.name.startswith("c0")):
        receipt=json.loads((run/"receipt.json").read_text())
        receipt["configurationHashes"]=hashes
        (run/"receipt.json").write_text(json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    control_root.build_observations(root); reseal_control_root(root)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert any("command binding" in item for item in result["rootErrors"])
    assert any("command binding" in item for item in result["receiptErrors"])


def test_phase1_replay_rejects_every_lexical_path_alias_without_filesystem_access(
        tmp_path,monkeypatch):
    root=synthetic_control_root(tmp_path)
    transcript=json.loads((root/"python-runtime.json").read_text())

    def forbidden_resolve(*args,**kwargs):
        raise AssertionError("portable transcript replay consulted the adjudicator filesystem")

    monkeypatch.setattr(Path,"resolve",forbidden_resolve)
    assert control_runner.python_runtime_transcript_errors(transcript) == []
    for alias in ("//opt/python", "/opt//python", "/opt/./python",
                  "/opt/bin/../python", "/opt/python/"):
        try:
            control_runner.canonical_absolute_path(alias,"attack")
            assert False,alias
        except ValueError:
            pass


def test_phase1_rejects_coherently_resealed_derived_python_forgery(tmp_path):
    root=synthetic_control_root(tmp_path)
    rewrite_python_binding(
        root,"/opt/forged-python",executable_sha256="f"*64)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert result["internalValid"] is False
    assert any("raw runtime transcript" in item
               for item in result["rootErrors"]+result["receiptErrors"])


def test_phase1_whole_raw_transcript_replacement_requires_external_seal(tmp_path):
    root=synthetic_control_root(tmp_path)
    sealed_manifest_file_sha=campaign.sha256(root/"evidence-manifest.json")
    transcript=json.loads((root/"python-runtime.json").read_text())
    forged="/opt/forged-python"
    transcript.update({
        "requestedExecutable":forged,
        "resolvedExecutable":forged,
        "identityExecutableResolved":forged,
        "fileSha256":"f"*64,
    })
    transcript["identity"]["executable"]=forged
    transcript["versionCommand"]["command"]=[forged,"--version"]
    transcript["identityCommand"]["command"]=[
        forged,"-c",control_runner.PYTHON_IDENTITY_CODE]
    transcript["identityCommand"]["stdout"]=(
        json.dumps(transcript["identity"],sort_keys=True)+"\n")
    assert control_runner.python_runtime_transcript_errors(transcript) == []
    rewrite_python_binding(root,forged,python_runtime=transcript)

    internally_resealed=control_root.validate_root(root)
    assert internally_resealed["valid"] is False,internally_resealed
    assert internally_resealed["internalValid"] is True
    assert internally_resealed["finalizationEligible"] is False
    assert internally_resealed["externalSealProvided"] is False

    detected=control_root.validate_root(
        root,expected_evidence_manifest_file_sha256=sealed_manifest_file_sha)
    assert detected["valid"] is False
    assert detected["internalValid"] is True
    assert detected["externalSealProvided"] is True
    assert detected["externalSealValid"] is False
    assert detected["finalizationEligible"] is False

    current_manifest_file_sha=campaign.sha256(root/"evidence-manifest.json")
    externally_sealed=control_root.validate_root(
        root,expected_evidence_manifest_file_sha256=current_manifest_file_sha)
    assert externally_sealed["valid"] is True
    assert externally_sealed["finalizationEligible"] is True


def test_phase1_root_is_portable_and_never_uses_stale_original_locators(tmp_path):
    original=synthetic_control_root(tmp_path/"original")
    copied=tmp_path/"copied-root"
    shutil.copytree(original,copied)
    assert control_root.validate_root(copied)["internalValid"] is True
    (original/"source-compose.yml").write_text("forged stale original\n")
    assert control_root.validate_root(copied)["internalValid"] is True
    # Destroy the old evidence, materialized source, and captured framework workspace.
    shutil.rmtree(tmp_path/"original")
    assert control_root.validate_root(copied)["internalValid"] is True
    rows=json.loads((copied/"control-observations.json").read_text())
    assert all(not Path(item["locator"]).is_absolute()
               for row in rows for item in row["evidenceItems"])


def test_phase1_root_rejects_unexpected_generic_retained_blocker(tmp_path,monkeypatch):
    root=synthetic_control_root(tmp_path)
    stored=json.loads((root/"control-universe-evaluation.json").read_text())
    stored["blockers"].append(
        "observation 'obs-c01-full-reference'.stages.retained lacks "
        "stage-appropriate runtime evidence; generic test evidence cannot prove 'retained'")
    (root/"control-universe-evaluation.json").write_text(
        json.dumps(stored,indent=2,sort_keys=True)+"\n")
    reseal_control_root(root)
    monkeypatch.setattr(control_root,"_generic_evaluator",lambda:lambda *args,**kwargs:stored)
    result=control_root.validate_root(root)
    assert result["internalValid"] is False
    assert result["genericBlockersExact"] is False


def test_phase1_cli_separates_internal_replay_from_external_finalization(
        tmp_path,monkeypatch,capsys):
    root=synthetic_control_root(tmp_path)
    monkeypatch.setattr(sys,"argv",["control_microtest_root.py",str(root),"--summary"])
    assert control_root.main() == 2
    result=json.loads(capsys.readouterr().out)
    assert result["valid"] is False
    assert result["internalValid"] is True
    assert result["finalizationEligible"] is False
    assert result["externalSealProvided"] is False
    assert result["externalSealValid"] is False
    assert result["validationMode"] == "external-finalization"
    assert result["commandAccepted"] is False
    assert result["evidenceContentSha256"] == json.loads(
        (root/"evidence-manifest.json").read_text())["evidenceSha256"]
    assert result["evidenceManifestFileSha256"] == campaign.sha256(
        root/"evidence-manifest.json")
    assert result["archiveSha256"] is None

    monkeypatch.setattr(sys,"argv",["control_microtest_root.py",str(root),"--summary",
        "--internal-replay-only"])
    assert control_root.main() == 0
    internal=json.loads(capsys.readouterr().out)
    assert internal["valid"] is False
    assert internal["internalValid"] is True
    assert internal["finalizationEligible"] is False
    assert internal["validationMode"] == "internal-replay-only"
    assert internal["commandAccepted"] is True

    manifest_file_sha=campaign.sha256(root/"evidence-manifest.json")
    monkeypatch.setattr(sys,"argv",["control_microtest_root.py",str(root),"--summary",
        "--expected-evidence-manifest-file-sha256",manifest_file_sha])
    assert control_root.main() == 0
    finalized=json.loads(capsys.readouterr().out)
    assert finalized["valid"] is True
    assert finalized["internalValid"] is True
    assert finalized["externalSealProvided"] is True
    assert finalized["externalSealValid"] is True
    assert finalized["finalizationEligible"] is True
    assert finalized["validationMode"] == "external-finalization"
    assert finalized["commandAccepted"] is True


def test_phase1_canary_failure_is_sealed_as_diagnostic_quarantine(monkeypatch,tmp_path):
    source=tmp_path/"source"; source.mkdir()
    (source/".source.sha256").write_text("a"*64+"\n")
    (source/campaign.COMPOSE_FILE).write_text("services: {}\n")
    (source/".obsplacement-materialized").write_text(json.dumps({
        "materializedSourceSha256":"a"*64})+"\n")
    output=tmp_path/"phase1"
    monkeypatch.setattr(sys,"argv",["control_microtests.py","--output",str(output),
        "--source",str(source),"--project","obs-phase1-main","--port","18090",
        "--canary-project","obs-phase1-canary","--canary-port","18091"])
    primitives=control_runner.campaign
    source_proof={"materializedSourceSha256":"a"*64,"sourceGuardChanges":[]}
    monkeypatch.setattr(primitives,"ensure_materialized",lambda path:source_proof)
    monkeypatch.setattr(primitives,"framework_proof",lambda:{"frameworkCommit":"c"*40,
        "dirty":False,"provenanceSource":"independently-inspected-local-git-checkout"})
    monkeypatch.setattr(control_runner,"framework_git_transcript",lambda framework:{
        "schemaVersion":1,"workingDirectoryRole":"framework-root","commands":{}})
    monkeypatch.setattr(primitives,"project_resources",lambda project:clean_resource_proof(project))
    monkeypatch.setattr(primitives,"assert_port_free",lambda port:None)
    monkeypatch.setattr(primitives,"build_once",lambda *args,**kwargs:{"images":{}})
    monkeypatch.setattr(primitives,"run_acquisition_canary",lambda *args,**kwargs:{
        "passed":False,"blockers":["synthetic canary failure"]})
    monkeypatch.setattr(primitives,"write_manifest",lambda root:
        (root/"evidence-manifest.json").write_text("{}\n"))
    assert control_runner.main() == 2
    summary=json.loads((output/"summary.json").read_text())
    assert summary["label"] == "diagnostic-quarantine"
    assert summary["registersAsEvidence"] is False
    assert summary["runs"] == 0
    assert (output/"final-hygiene.json").is_file()
    assert (output/"evidence-manifest.json").is_file()


def test_phase1_partial_no_fault_canary_stops_before_control_runs(monkeypatch,tmp_path):
    source=tmp_path/"source"; source.mkdir()
    (source/".source.sha256").write_text("a"*64+"\n")
    (source/campaign.COMPOSE_FILE).write_text("services: {}\n")
    (source/".obsplacement-materialized").write_text(json.dumps({
        "materializedSourceSha256":"a"*64})+"\n")
    output=tmp_path/"phase1-partial-canary"
    monkeypatch.setattr(sys,"argv",["control_microtests.py","--output",str(output),
        "--source",str(source),"--project","obs-phase1-main","--port","18090",
        "--canary-project","obs-phase1-canary","--canary-port","18091"])
    primitives=control_runner.campaign
    source_proof={"materializedSourceSha256":"a"*64,"sourceGuardChanges":[]}
    monkeypatch.setattr(primitives,"ensure_materialized",lambda path:source_proof)
    monkeypatch.setattr(primitives,"framework_proof",lambda:{"frameworkCommit":"c"*40,
        "dirty":False,"provenanceSource":"independently-inspected-local-git-checkout",
        "executorAssertionCrossChecked":False})
    monkeypatch.setattr(control_runner,"framework_git_transcript",lambda framework:{
        "schemaVersion":1,"workingDirectoryRole":"framework-root","commands":{}})
    monkeypatch.setattr(primitives,"project_resources",lambda project:clean_resource_proof(project))
    monkeypatch.setattr(primitives,"assert_port_free",lambda port:None)
    monkeypatch.setattr(primitives,"build_once",lambda *args,**kwargs:{"images":{}})
    started="2026-08-17T00:00:00+00:00"; ended="2026-08-17T00:00:15+00:00"
    rows=[{"scheduledAtEpoch":datetime.fromisoformat(started).timestamp()+index,
           "startedAtEpoch":datetime.fromisoformat(started).timestamp()+index+0.01,
           "endedAtEpoch":datetime.fromisoformat(started).timestamp()+index+0.02,
           "status":200,"bytes":100,"error":None} for index in range(15)]
    rows[0].update({"status":None,"bytes":0,"error":"Timeout"})
    partial={"scenario":"homepage","url":"http://127.0.0.1:18091/",
        "ratePerSecond":1.0,"durationSeconds":15.0,"concurrency":4,
        "offered":15,"completed":14,"failed":1,"requests":rows}
    canary={"passed":True,"window":{"startedAt":started,"endedAt":ended}}
    def fake_canary(root,*args,**kwargs):
        directory=root/"acquisition-canary"; directory.mkdir()
        (directory/"workload.json").write_text(json.dumps(partial,indent=2,sort_keys=True)+"\n")
        return canary
    monkeypatch.setattr(primitives,"run_acquisition_canary",fake_canary)
    monkeypatch.setattr(primitives,"validate_completed_canary",lambda *args,**kwargs:canary)
    calls=[]
    monkeypatch.setattr(control_runner,"run_one",lambda *args,**kwargs:calls.append(True))
    monkeypatch.setattr(primitives,"write_manifest",lambda root:
        (root/"evidence-manifest.json").write_text("{}\n"))
    assert control_runner.main() == 2
    assert calls == []
    summary=json.loads((output/"summary.json").read_text())
    assert summary["runs"] == 0
    assert "no-fault canary failed" in summary["failure"]

def test_every_online_boutique_framework_file_is_classified():
    result=module_audit.audit(ROOT/"modules/online-boutique")
    assert result["verdict"] == "pass", result
    assert result["classified_files"] == 25
