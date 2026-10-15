import argparse, base64, hashlib, importlib.util, json, math, os, shutil, socket, subprocess, types
from pathlib import Path
import pytest

ROOT=Path(__file__).parents[1]
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
materialize=load("ob_lgtm_materialize",ROOT/"modules/online-boutique-lgtm/materialize.py")
campaign=load("ob_lgtm_campaign",ROOT/"modules/online-boutique-lgtm/execution/campaign.py")
preflight=load("ob_lgtm_preflight",ROOT/"modules/online-boutique-lgtm/execution/preflight.py")
bootstrap=load("ob_lgtm_bootstrap",ROOT/"modules/online-boutique-lgtm/execution/bootstrap_tools.py")
kind_smoke=load("ob_lgtm_kind_smoke",ROOT/"modules/online-boutique-lgtm/execution/kind_smoke.py")
synthetic=load("ob_lgtm_synthetic",ROOT/"modules/online-boutique-lgtm/validation/synthetic.py")
receipt=load("ob_lgtm_receipt",ROOT/"modules/online-boutique-lgtm/validation/receipt.py")
acquisition=load("ob_lgtm_acquisition",ROOT/"modules/online-boutique-lgtm/validation/acquisition.py")
tempo_collector=load("ob_lgtm_tempo_collector",ROOT/"modules/online-boutique-lgtm/collectors/tempo.py")
loki_collector=load("ob_lgtm_loki_collector",ROOT/"modules/online-boutique-lgtm/collectors/loki.py")
tempo_normalizer=load("ob_lgtm_tempo_normalizer",ROOT/"modules/online-boutique-lgtm/normalizers/tempo.py")
loki_normalizer=load("ob_lgtm_loki_normalizer",ROOT/"modules/online-boutique-lgtm/normalizers/loki.py")
module_audit=load("module_audit_lgtm",ROOT/"src/obsplacement/module_audit.py")

def args(source,**updates):
    values={"source":source,"postures":"none,selected,full","blocks":1,"duration":120,"warmup":30,"rate":1.0,"concurrency":4,"fault_at":45,"outage":15,"cluster":"obsplacement-test","seed":1,"tempo_chart_version":"1.20.0","loki_chart_version":"0.80.0","promtail_chart_version":"6.16.6"}
    values.update(updates); return argparse.Namespace(**values)

def endpoint_fixture(expected=None):
    expected=expected or {"frontend-service":8080}
    slice_items=[]; endpoint_items=[]
    for index,(service,port) in enumerate(sorted(expected.items()),start=1):
        address=f"10.0.0.{index}"
        slice_items.append({"metadata":{"name":f"{service}-slice","uid":f"uid-{index}",
            "resourceVersion":str(index),"labels":{"kubernetes.io/service-name":service}},
            "ports":[{"port":port,"protocol":"TCP"}],
            "endpoints":[{"conditions":{"ready":True},"addresses":[address]}]})
        endpoint_items.append({"metadata":{"name":service},"subsets":[{
            "ports":[{"port":port,"protocol":"TCP"}],"addresses":[{"ip":address}]}]})
    queries={}
    for name,document in (("endpointSlices",{"items":slice_items}),
                          ("endpoints",{"items":endpoint_items})):
        payload=json.dumps(document)
        queries[name]={"returnCode":0,"stderr":"","stdout":payload,
                       "stdoutSha256":hashlib.sha256(payload.encode()).hexdigest()}
    return receipt.build_endpoint_proof(expected,queries)

def tempo_fixture_proof(document, search_ids, spans=None, limit=1000):
    """Build the same immutable raw/normalized bindings as the executor."""
    spans=tempo_normalizer.normalize(document) if spans is None else spans
    search={"traces":[{"traceID":trace_id} for trace_id in search_ids]}
    trace_payload=json.dumps(document,sort_keys=True)+"\n"
    artifacts=[acquisition.trace_artifact_record(
        trace_id,f"tempo-traces/{trace_id}.json",trace_payload,document,spans)
        for trace_id in search_ids]
    search_payload=json.dumps(search,sort_keys=True)+"\n"
    spans_payload=json.dumps(spans,sort_keys=True)+"\n"
    start_ns=1_000_000_000; end_ns=2_000_000_000
    window_payload=json.dumps({"startNs":start_ns,"endNs":end_ns},sort_keys=True)+"\n"
    window_artifact=acquisition.raw_artifact_record(
        "measurement-window.json",window_payload,1)
    url=tempo_collector.search_request("http://127.0.0.1:13200",1,2,limit=limit)
    search_artifact=acquisition.raw_artifact_record(
        "tempo-search.json",search_payload,len(search_ids))
    request=acquisition.tempo_search_request_record(
        url,url,200,start_ns,end_ns,limit,search_artifact,window_artifact)
    request_payload=json.dumps(request,sort_keys=True)+"\n"
    return acquisition.tempo_proof(
        search,search_ids,spans,start_ns,end_ns,limit,trace_artifacts=artifacts,
        search_artifact=search_artifact,
        normalized_spans_artifact=acquisition.raw_artifact_record(
            "spans-normalized.json",spans_payload,len(spans)),
        search_request=request,
        search_request_artifact=acquisition.raw_artifact_record(
            "tempo-search-request.json",request_payload,1),
        measurement_window_artifact=window_artifact)

def write_tempo_fixture(run_dir, trace_hex="00"+"11"*15):
    run_dir.mkdir(parents=True)
    trace_raw=base64.b64encode(bytes.fromhex(trace_hex)).decode()
    document={"batches":[{"resource":{"attributes":[
        {"key":"service.name","value":{"stringValue":"frontend"}}]},
        "scopeSpans":[{"spans":[{"traceId":trace_raw,
            "spanId":base64.b64encode(bytes.fromhex("22"*8)).decode(),
            "name":"GET","kind":2,"startTimeUnixNano":"1200000000",
            "endTimeUnixNano":"1300000000","attributes":[
                {"key":"http.request.method","value":{"stringValue":"GET"}},
                {"key":"url.path","value":{"stringValue":"/"}}]}]}]}]}
    search_id=trace_hex.lstrip("0")
    search={"traces":[{"traceID":search_id}]}
    search_payload=json.dumps(search,indent=2,sort_keys=True)+"\n"
    (run_dir/"tempo-search.json").write_text(search_payload)
    trace_dir=run_dir/"tempo-traces"; trace_dir.mkdir()
    trace_payload=json.dumps(document,indent=2,sort_keys=True)+"\n"
    (trace_dir/f"{search_id}.json").write_text(trace_payload)
    spans=tempo_normalizer.normalize(document)
    spans_payload=json.dumps(spans,indent=2,sort_keys=True)+"\n"
    (run_dir/"spans-normalized.json").write_text(spans_payload)
    start_ns=1_000_000_000; end_ns=2_000_000_000
    workload={"requests":[{"startedAtEpoch":1.1,"endedAtEpoch":1.9}]}
    workload_payload=json.dumps(workload,indent=2,sort_keys=True)+"\n"
    (run_dir/"workload.json").write_text(workload_payload)
    window,window_artifact=kind_smoke.write_measurement_window(
        run_dir,start_ns,end_ns,{"measurementSeconds":1})
    start_ns=window["startNs"]; end_ns=window["endNs"]
    url=tempo_collector.search_request("http://127.0.0.1:13200",1,2,limit=1000)
    search_artifact=acquisition.raw_artifact_record("tempo-search.json",search_payload,1)
    request=acquisition.tempo_search_request_record(
        url,url,200,start_ns,end_ns,1000,search_artifact,window_artifact)
    request_payload=json.dumps(request,indent=2,sort_keys=True)+"\n"
    (run_dir/"tempo-search-request.json").write_text(request_payload)
    proof=acquisition.tempo_proof(
        search,[search_id],spans,start_ns,end_ns,1000,
        trace_artifacts=[acquisition.trace_artifact_record(
            search_id,f"tempo-traces/{search_id}.json",trace_payload,document,spans)],
        search_artifact=search_artifact,
        normalized_spans_artifact=acquisition.raw_artifact_record(
            "spans-normalized.json",spans_payload,len(spans)),
        search_request=request,
        search_request_artifact=acquisition.raw_artifact_record(
            "tempo-search-request.json",request_payload,1),
        measurement_window_artifact=window_artifact)
    proof["apiWindowUnit"]="unix-seconds"
    assert proof["passed"]
    return proof,spans,search_id

def write_loki_fixture(run_dir):
    run_dir.mkdir(parents=True,exist_ok=True)
    workload={"requests":[{"startedAtEpoch":1.1,"endedAtEpoch":2.9}]}
    workload_payload=json.dumps(workload,indent=2,sort_keys=True)+"\n"
    (run_dir/"workload.json").write_text(workload_payload)
    start_ns=1_000_000_000; end_ns=3_000_000_000
    window,window_artifact=kind_smoke.write_measurement_window(
        run_dir,start_ns,end_ns,{"measurementSeconds":1})
    start_ns=window["startNs"]; end_ns=window["endNs"]
    document={"status":"success","data":{"resultType":"streams","result":[{"stream":{"namespace":"online-boutique","pod":"frontend"},
        "values":[["2000000000","homepage"]]}]}}
    raw_payload=json.dumps(document,indent=2,sort_keys=True)+"\n"
    (run_dir/"loki.json").write_text(raw_payload)
    records=loki_normalizer.normalize(document)
    normalized_payload=json.dumps(records,indent=2,sort_keys=True)+"\n"
    (run_dir/"logs-normalized.json").write_text(normalized_payload)
    raw_artifact=acquisition.raw_artifact_record("loki.json",raw_payload,1)
    url=loki_collector.query_request(
        "http://127.0.0.1:13100",start_ns,end_ns,limit=5000)
    request=acquisition.loki_query_request_record(
        url,url,200,start_ns,end_ns,5000,raw_artifact,window_artifact)
    request_payload=json.dumps(request,indent=2,sort_keys=True)+"\n"
    (run_dir/"loki-query-request.json").write_text(request_payload)
    proof=acquisition.loki_proof(
        document,records,start_ns,end_ns,5000,raw_artifact=raw_artifact,
        normalized_artifact=acquisition.raw_artifact_record(
            "logs-normalized.json",normalized_payload,1),query_request=request,
        query_request_artifact=acquisition.raw_artifact_record(
            "loki-query-request.json",request_payload,1),
        measurement_window_artifact=window_artifact)
    assert proof["passed"]
    return proof,records,workload

def write_global_tempo_fixture(run_dir,services=()):
    run_dir.mkdir(parents=True,exist_ok=True)
    workload={"requests":[{"startedAtEpoch":1.1,"endedAtEpoch":1.9}]}
    (run_dir/"workload.json").write_text(json.dumps(workload,indent=2,sort_keys=True)+"\n")
    window,window_artifact=kind_smoke.write_measurement_window(
        run_dir,1_000_000_000,2_000_000_000,{"measurementSeconds":1})
    trace_ids=[f"{index:032x}" for index in range(1,len(services)+1)]
    search={"traces":[{"traceID":trace_id} for trace_id in trace_ids]}
    payload=json.dumps(search,indent=2,sort_keys=True)+"\n"
    (run_dir/"tempo-global-search.json").write_text(payload)
    artifact=acquisition.raw_artifact_record(
        "tempo-global-search.json",payload,len(trace_ids))
    url=tempo_collector.global_search_request("http://127.0.0.1:13200",1,2,limit=1000)
    request=acquisition.tempo_search_request_record(
        url,url,200,window["startNs"],window["endNs"],1000,artifact,window_artifact)
    request_payload=json.dumps(request,indent=2,sort_keys=True)+"\n"
    (run_dir/"tempo-global-search-request.json").write_text(request_payload)
    trace_dir=run_dir/"tempo-global-traces"; trace_dir.mkdir()
    spans=[]; artifacts=[]
    for index,(trace_id,service) in enumerate(zip(trace_ids,services),1):
        document={"batches":[{"resource":{"attributes":[
            {"key":"service.name","value":{"stringValue":service}}]},
            "scopeSpans":[{"spans":[{
                "traceId":base64.b64encode(bytes.fromhex(trace_id)).decode(),
                "spanId":base64.b64encode(index.to_bytes(8,"big")).decode(),
                "name":"health","kind":2,"startTimeUnixNano":"1200000000",
                "endTimeUnixNano":"1300000000"}]}]}]}
        trace_payload=json.dumps(document,indent=2,sort_keys=True)+"\n"
        path=trace_dir/f"{trace_id}.json"; path.write_text(trace_payload)
        normalized=tempo_normalizer.normalize(document); spans.extend(normalized)
        artifacts.append(acquisition.trace_artifact_record(
            trace_id,path.relative_to(run_dir).as_posix(),trace_payload,document,normalized,
            directory="tempo-global-traces"))
    spans_payload=json.dumps(spans,indent=2,sort_keys=True)+"\n"
    (run_dir/"spans-global-normalized.json").write_text(spans_payload)
    targets=kind_smoke.targeted_source_services(json.loads(
        (ROOT/"modules/online-boutique/activation/catalog.json").read_text()))
    proof=acquisition.tempo_global_proof(
        search,window["startNs"],window["endNs"],1000,search_artifact=artifact,
        search_request=request,search_request_artifact=acquisition.raw_artifact_record(
            "tempo-global-search-request.json",request_payload,1),
        trace_artifacts=artifacts,spans=spans,
        normalized_spans_artifact=acquisition.raw_artifact_record(
            "spans-global-normalized.json",spans_payload,len(spans)),
        targeted_source_services=targets,
        measurement_window_artifact=window_artifact)
    assert proof["passed"],proof["blockers"]
    return proof,workload

def test_transform_rebinds_app_and_excludes_generators():
    source=materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST
    transformed,proof=materialize.transform_manifest(source.read_text(),"a"*64)
    assert proof["syntheticGeneratorsAbsent"] is True
    assert "loadgenerator" not in transformed and "v0.8.0" not in transformed and ":latest" not in transformed
    assert transformed.count("obsplacement/online-boutique-")==3
    assert proof["removedIngresses"] == ["ingress-microservices"]
    assert "kind: Ingress" not in transformed
    compatibility=proof["runtimeCompatibility"]
    assert compatibility["status"]=="passed" and compatibility["ingressAbsent"] is True
    frontend=compatibility["sourceBuiltDeployments"]["frontend"]
    assert frontend["environment"]["SHOPPING_ASSISTANT_SERVICE_ADDR"]=="shoppingassistantservice:80"
    assert frontend["environment"]["ENABLE_ASSISTANT"]=="false"
    assert set(frontend["auditedRequiredEnvironment"])=={
        "AD_SERVICE_ADDR","CART_SERVICE_ADDR","CHECKOUT_SERVICE_ADDR",
        "COLLECTOR_SERVICE_ADDR","CURRENCY_SERVICE_ADDR","PRODUCT_CATALOG_SERVICE_ADDR",
        "RECOMMENDATION_SERVICE_ADDR","SHIPPING_SERVICE_ADDR","SHOPPING_ASSISTANT_SERVICE_ADDR",
    }
    assert compatibility["inactiveFrontendTarget"]["servicePresent"] is False

@pytest.mark.parametrize(("service","old","new"),[
    ("frontend","SHOPPING_ASSISTANT_SERVICE_ADDR","UNBOUND_ASSISTANT_ADDR"),
    ("productcatalogservice",'value: "3550"','value: "3551"'),
    ("currencyservice",'value: "7000"','value: "7001"'),
])
def test_runtime_contract_rejects_source_service_environment_drift(service,old,new):
    source=materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST
    transformed,_=materialize.transform_manifest(source.read_text(),"a"*64)
    document=materialize._single_document(materialize.yaml_documents(transformed),"Deployment",service)
    mutated=document.replace(old,new,1)
    assert mutated!=document
    with pytest.raises(RuntimeError,match=f"{service} literal environment differs"):
        materialize.audit_runtime_contract(transformed.replace(document,mutated,1))

def test_runtime_contract_rejects_probe_port_and_ingress_drift():
    source=materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST
    transformed,_=materialize.transform_manifest(source.read_text(),"a"*64)
    product=materialize._single_document(
        materialize.yaml_documents(transformed),"Deployment","productcatalogservice")
    mutated=product.replace("readinessProbe:\n          grpc:\n            port: 3550",
                            "readinessProbe:\n          grpc:\n            port: 3551",1)
    assert mutated!=product
    with pytest.raises(RuntimeError,match="productcatalogservice readinessProbe"):
        materialize.audit_runtime_contract(transformed.replace(product,mutated,1))
    with pytest.raises(RuntimeError,match="unowned Ingress"):
        materialize.audit_runtime_contract(
            transformed+"---\napiVersion: networking.k8s.io/v1\nkind: Ingress\nmetadata:\n  name: stale\n")

@pytest.mark.parametrize(("service","old","new","message"),[
    ("productcatalogservice","targetPort: 3550","targetPort: 3551","targetPort 3550"),
    ("frontend-service","targetPort: 8080","targetPort: 9999","targetPort 8080"),
    ("frontend-service","port: 8080","port: 9999","exact port 8080"),
])
def test_runtime_contract_rejects_service_routing_drift(service,old,new,message):
    source=materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST
    transformed,_=materialize.transform_manifest(source.read_text(),"a"*64)
    document=materialize._single_document(materialize.yaml_documents(transformed),"Service",service)
    mutated=document.replace(old,new,1)
    assert mutated!=document
    with pytest.raises(RuntimeError,match=message):
        materialize.audit_runtime_contract(transformed.replace(document,mutated,1))

def test_runtime_contract_rejects_ambiguous_service_workload_match():
    source=materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST
    transformed,_=materialize.transform_manifest(source.read_text(),"a"*64)
    product=materialize._single_document(
        materialize.yaml_documents(transformed),"Deployment","productcatalogservice")
    shadow=product.replace("name: productcatalogservice","name: productcatalog-shadow",1)
    assert shadow!=product
    with pytest.raises(RuntimeError,match="productcatalogservice does not resolve to exactly"):
        materialize.audit_runtime_contract(transformed+"---\n"+shadow)

def test_runtime_contract_rejects_ready_workload_on_wrong_service_listener():
    source=materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST
    transformed,_=materialize.transform_manifest(source.read_text(),"a"*64)
    ad=materialize._single_document(materialize.yaml_documents(transformed),"Deployment","adservice")
    mutated=ad.replace("9555","9556")
    assert mutated!=ad
    with pytest.raises(RuntimeError,match="adservice does not expose the exact audited container port 9555"):
        materialize.audit_runtime_contract(transformed.replace(ad,mutated,1))

def test_runtime_contract_rejects_udp_service_or_workload_listener():
    source=materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST
    transformed,_=materialize.transform_manifest(source.read_text(),"a"*64)
    documents=materialize.yaml_documents(transformed)
    service=materialize._single_document(documents,"Service","adservice")
    udp_service=service.replace("targetPort: 9555","targetPort: 9555\n    protocol: UDP",1)
    with pytest.raises(RuntimeError,match="Service/adservice does not retain effective TCP"):
        materialize.audit_runtime_contract(transformed.replace(service,udp_service,1))
    workload=materialize._single_document(documents,"Deployment","adservice")
    udp_workload=workload.replace("containerPort: 9555","containerPort: 9555\n          protocol: UDP",1)
    with pytest.raises(RuntimeError,match="adservice does not retain effective TCP listener"):
        materialize.audit_runtime_contract(transformed.replace(workload,udp_workload,1))

def test_plan_reuses_shared_contract_and_rejects_latest(tmp_path):
    proof={"acquisitionSource":{"commit":materialize.EXPECTED_ACQUISITION_SHA},"applicationSource":{"commit":materialize.EXPECTED_APP_SHA},"applicationMaterialization":{"sha256":"a"*64},"sharedContract":{"goalRef":"modules/online-boutique/goals/homepage-path.json","goalSha256":"b"*64,"activationRef":"modules/online-boutique/activation/catalog.json","activationSha256":"c"*64},"generatedConfigSha256":{"application.yaml":"d"*64},"kustomize":{"command":["kubectl","kustomize"],"targets":{"none":"postures/none","selected":"postures/selected","full":"postures/full"}}}
    (tmp_path/".obsplacement-lgtm-materialized").write_text(json.dumps(proof))
    plan=campaign.build(args(tmp_path)); assert plan["configuration"]["sharedContract"]==proof["sharedContract"]
    assert plan["configuration"]["fault"]=="productcatalog-kubernetes-scale-zero"
    assert plan["configuration"]["visibilitySafetyMarginSeconds"]==5
    assert plan["configuration"]["chartSha256"]==campaign.CHART_SHA256
    assert plan["configuration"]["kindNodeImage"]==kind_smoke.NODE_IMAGE
    assert plan["lifecycle"]["executor"].endswith("kind_smoke.py")
    try: campaign.build(args(tmp_path,tempo_chart_version="latest")); assert False
    except ValueError: pass
    try: campaign.build(args(tmp_path,rate=math.inf)); assert False
    except ValueError: pass
    try: campaign.build(args(tmp_path,fault_at=5)); assert False
    except ValueError: pass

def test_preflight_and_synthetic_gates():
    snap={"python":"3.13.5","tools":{tool:{"path":f"/bin/{tool}","versionExit":0} for tool in preflight.TOOLS},"kindClusters":[],"kindListExit":0}
    assert preflight.blockers(snap,"obsplacement-test")==[]
    assert preflight.blockers({**snap,"tools":{}},"obsplacement-test")
    failed={**snap,"tools":{**snap["tools"],"kubectl":{"path":"/bin/kubectl","versionExit":1}}}
    assert "tool version check failed: kubectl" in preflight.blockers(failed,"obsplacement-test")
    assert "unable to list kind clusters" in preflight.blockers({**snap,"kindListExit":1},"obsplacement-test")
    assert synthetic.proof("kind: Deployment\nname: frontend",["frontend-1"],[{"serviceName":"frontend"}],True)["passed"]
    assert not synthetic.proof("name: loadgenerator",[],[])["passed"]

def test_receipt_requires_runtime_provenance_and_exclusion():
    rows=[{"startedAtEpoch":10,"endedAtEpoch":11,"error":None},{"startedAtEpoch":25,"endedAtEpoch":26,"error":"HTTP 500"},{"startedAtEpoch":36,"endedAtEpoch":37,"error":None}]
    endpoint=endpoint_fixture()
    valid={"source":{"applicationUpstreamSha":receipt.APP_SHA,"acquisitionUpstreamSha":receipt.LGTM_SHA,"applicationMaterializedSha256":"a"*64,"frameworkDirty":False},"sharedContract":{"goalSha256":"b"*64,"activationSha256":"c"*64},"workload":{"offered":3,"completed":2,"failed":1,"requests":rows},"intervention":{"evidenceSource":"scheduled-measured-workload-only","scaledToZero":True,"scaledToZeroAtEpoch":20,"scaleOneAtEpoch":30,"rolloutReadyAtEpoch":35,"preFaultSuccessfulCount":1,"scaleZeroFailureCount":1,"postRecoverySuccessfulCount":1,"commands":[{"action":"scale-zero","returnCode":0},{"action":"scale-one","returnCode":0}],"manifested":True,"recovered":True,"successful":True},"posture":"full","postureProof":{"sourceGuarded":True,"sourceGuardSetExact":True,"sourceGuardChangeIds":sorted(receipt.EXPECTED_GUARDS)},"serviceEndpoints":endpoint,"telemetry":{"tempoSpans":5,"lokiRecords":2},"runtimeImages":[{"service":"frontend","imageID":"sha256:"+"d"*64}],"configSha256":{"application.yaml":"e"*64},"configurationBinding":{"scheduleSha256":"1","plannerSha256":"2","executorSha256":"3","frameworkCommit":"4","frameworkBundleSha256":"5","helmValueSha256":{"v":"6"},"chartArchiveSha256":{"c":"7"},"kindNodeImage":"image@sha256:8","buildkitImage":"buildkit@sha256:8","hostToolProofSha256":"9"},"visibility":{"verdict":"pass","measurementWindow":{"bounded":True},"minimumCompletePathTraceCount":1,"completePathTraceCount":1,"requestTraceCompleteness":"descriptive-only"},"appliedKustomize":{"posture":"full","command":["kubectl","kustomize"],"renderedSha256":"sha256:"+"f"*64},"acquisitionProof":{"tempo":{"passed":True,"queryWindowBounded":True,"limitReached":False,"nativeSpanIdentityPreserved":True},"loki":{"passed":True,"queryWindowBounded":True,"limitReached":False}},"syntheticTraceExclusion":{"passed":True,"queryWindowBounded":True}}
    valid["acquisitionProof"]["tempoGlobal"]={"passed":True,"queryWindowBounded":True,
        "limitReached":False,"globalTelemetryDisabled":False,
        "claimBoundary":"targeted-source-built-services-only"}
    valid["telemetry"]["tempoGlobalTraces"]=5
    assert receipt.blockers(valid)==[]
    valid["runtimeImages"][0]["imageID"]="frontend:latest"; assert "runtime image IDs are not immutable" in receipt.blockers(valid)
    valid["runtimeImages"][0]["imageID"]="sha256:"+"d"*64
    valid["intervention"]["preFaultSuccessfulCount"]=2
    assert "intervention counts disagree with raw workload timestamps" in receipt.blockers(valid)
    valid["intervention"]["preFaultSuccessfulCount"]=1
    none=json.loads(json.dumps(valid)); none["posture"]="none"
    none["appliedKustomize"]["posture"]="none"
    none["telemetry"].update({"tempoSpans":0,"tempoTargetSourceSpans":0})
    none["visibility"].update({"verdict":"blocked","retainedRequiredSensors":[],
        "directParentLinkedEdgeTraceCount":0,"completePathTraceCount":0})
    assert receipt.blockers(none)==[]
    none["visibility"]["retainedRequiredSensors"]=["span:frontend:GET"]
    assert "none posture retained a targeted structural sensor or edge" in receipt.blockers(none)

def test_channel_boundaries_are_bounded_and_normalize_separately(tmp_path):
    assert "start=1" in tempo_collector.search_request("http://tempo",1,2)
    assert "limit=1000" in tempo_collector.search_request("http://tempo",1,2)
    assert "q=" not in tempo_collector.global_search_request("http://tempo",1,2)
    assert "start=1" in loki_collector.query_request("http://loki",1,2)
    trace_bytes=bytes.fromhex("00"+"11"*15)
    span_bytes=bytes.fromhex("22"*8)
    parent_bytes=bytes.fromhex("33"*8)
    trace_raw=base64.b64encode(trace_bytes).decode()
    span_raw=base64.b64encode(span_bytes).decode()
    parent_raw=base64.b64encode(parent_bytes).decode()
    trace={"batches":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"frontend"}}]},"scopeSpans":[{"spans":[{"traceId":trace_raw,"spanId":span_raw,"parentSpanId":parent_raw,"name":"GET /","kind":2,"startTimeUnixNano":"1200000000","endTimeUnixNano":"1300000000"}]}]}]}
    normalized=tempo_normalizer.normalize(trace)
    row=normalized[0]
    assert row["serviceName"]=="frontend"
    assert row["traceId"]==trace_bytes.hex() and row["traceIdRaw"]==trace_raw
    assert row["traceIdEncoding"]=="base64"
    assert row["spanId"]==span_bytes.hex() and row["spanIdRaw"]==span_raw
    assert row["parentSpanId"]==parent_bytes.hex() and row["parentSpanIdRaw"]==parent_raw
    logs={"data":{"result":[{"stream":{"pod":"frontend"},"values":[["2","b"],["1","a"]]}]}}
    assert [row["line"] for row in loki_normalizer.normalize(logs)]==["a","b"]
    # Tempo search drops the leading zero from this valid 16-byte trace ID.
    search_id=trace_bytes.hex().lstrip("0")
    tempo_proof=tempo_fixture_proof(trace,[search_id],normalized)
    assert tempo_proof["passed"] and tempo_proof["nativeSpanIdentityPreserved"]
    assert tempo_proof["completeTraceFetch"] and tempo_proof["rawIdentityPreserved"]
    assert tempo_proof["canonicalTraceIdEncoding"]=="fixed-width-lowercase-hex"
    loki_proof,_,_=write_loki_fixture(tmp_path/"loki")
    assert loki_proof["passed"]
    truncated=tempo_fixture_proof(trace,[search_id],normalized,limit=1)
    assert not truncated["passed"] and truncated["limitReached"]

def test_global_tempo_query_proves_none_zero_and_detects_backend_only_trace(tmp_path):
    empty=tmp_path/"empty"
    proof,workload=write_global_tempo_fixture(empty)
    targets=kind_smoke.targeted_source_services(json.loads(
        (ROOT/"modules/online-boutique/activation/catalog.json").read_text()))
    recomputed,window=kind_smoke.recompute_tempo_global_run(
        empty,proof,{"measurementSeconds":1},workload,targets)
    assert recomputed["returnedTraceCount"]==0 and window["startNs"]==1_100_000_000

    backend=tmp_path/"backend"
    background=tmp_path/"background"
    background_proof,_=write_global_tempo_fixture(background,["checkoutservice"])
    assert background_proof["returnedTraceCount"]==1
    assert background_proof["targetedSourceSpanCount"]==0
    assert background_proof["backgroundTraceCount"]==1

    backend_proof,_=write_global_tempo_fixture(backend,["productcatalogservice"])
    assert backend_proof["returnedTraceCount"]==1 and backend_proof["targetedSourceSpanCount"]==1
    candidate={"posture":"none","telemetry":{"tempoSpans":0,"tempoTargetSourceSpans":1},
               "acquisitionProof":{"tempoGlobal":backend_proof}}
    assert "none posture emitted spans from a targeted source-built service" in receipt.blockers(candidate)

def test_global_tempo_missing_service_identity_cannot_masquerade_as_background(tmp_path):
    run=tmp_path/"missing-service"
    proof,workload=write_global_tempo_fixture(run,["productcatalogservice"])
    trace_path=next((run/"tempo-global-traces").glob("*.json"))
    document=json.loads(trace_path.read_text())
    document["batches"][0]["resource"]["attributes"]=[]
    trace_path.write_text(json.dumps(document,indent=2,sort_keys=True)+"\n")
    forged=json.loads(json.dumps(proof))
    forged["targetedSourceSpanCount"]=0; forged["targetedSourceTraceIds"]=[]
    forged["backgroundTraceCount"]=1
    with pytest.raises(ValueError,match="service.name"):
        kind_smoke.recompute_tempo_global_run(
            run,forged,{"measurementSeconds":1},workload,
            kind_smoke.targeted_source_services(json.loads(
                (ROOT/"modules/online-boutique/activation/catalog.json").read_text())))

@pytest.mark.parametrize("mutation",["body","status","window","limit"])
def test_final_global_tempo_reread_rejects_joint_tamper(tmp_path,mutation):
    run=tmp_path/mutation
    proof,workload=write_global_tempo_fixture(run)
    request_path=run/"tempo-global-search-request.json"
    if mutation=="body":
        payload=json.dumps({"traces":[{"traceID":"ab"*16}]},indent=2,sort_keys=True)+"\n"
        (run/"tempo-global-search.json").write_text(payload)
        artifact=acquisition.raw_artifact_record("tempo-global-search.json",payload,1)
        proof["returnedTraceCount"]=1; proof["canonicalTraceIds"]=["ab"*16]
        proof["searchArtifact"]=artifact; proof["searchRequest"]["bodyArtifact"]=artifact
    else:
        request=json.loads(request_path.read_text())
        if mutation=="status": request["status"]=503
        elif mutation=="window":
            request["measurementWindow"]={"startNs":1_150_000_000,"endNs":1_950_000_000}
        else:
            request["requestedUrl"]=request["requestedUrl"].replace("limit=1000","limit=999")
            request["responseUrl"]=request["requestedUrl"]
            request["query"][2][1]="999"; proof["limit"]=999
        request_payload=json.dumps(request,indent=2,sort_keys=True)+"\n"
        request_path.write_text(request_payload)
        proof["searchRequest"]=request
        proof["searchRequestArtifact"]=acquisition.raw_artifact_record(
            "tempo-global-search-request.json",request_payload,1)
    with pytest.raises(RuntimeError):
        kind_smoke.recompute_tempo_global_run(
            run,proof,{"measurementSeconds":1},workload,
            kind_smoke.targeted_source_services(json.loads(
                (ROOT/"modules/online-boutique/activation/catalog.json").read_text())))

def test_tempo_identity_gates_reject_invalid_duplicate_or_unattributed_ids():
    trace_raw=base64.b64encode(bytes.fromhex("44"*16)).decode()
    span_raw=base64.b64encode(bytes.fromhex("55"*8)).decode()
    trace={"batches":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"frontend"}}]},"scopeSpans":[{"spans":[{
        "traceId":trace_raw,"spanId":span_raw,"name":"GET","kind":2,
        "startTimeUnixNano":"1200000000","endTimeUnixNano":"1300000000",
    }]}]}]}
    rows=tempo_normalizer.normalize(trace)
    trace_id=rows[0]["traceId"]

    duplicate=tempo_fixture_proof(trace,[trace_id],rows+rows)
    assert not duplicate["passed"] and duplicate["duplicateSpanIdentityCount"]==1

    unattributed=tempo_fixture_proof(trace,["6"*32],rows)
    assert not unattributed["passed"]
    assert "normalized span is not attributable to a fetched native trace" in unattributed["blockers"]

    tampered=[{**rows[0],"spanIdRaw":base64.b64encode(bytes.fromhex("77"*8)).decode()}]
    altered=tempo_fixture_proof(trace,[trace_id],tampered)
    assert not altered["nativeSpanIdentityPreserved"] and not altered["rawIdentityPreserved"]

    invalid=tempo_fixture_proof(trace,["not-hex"],rows)
    assert not invalid["passed"] and invalid["invalidSearchTraceIdCount"]==1

@pytest.mark.parametrize(("field","raw","message"),[
    ("traceId",base64.b64encode(b"short-trace-id!").decode(),"expected 16"),
    ("spanId","not-base64!","not canonical OTLP JSON base64"),
    ("parentSpanId",base64.b64encode(b"7-bytes").decode(),"expected 8"),
    ("spanId","11"*8,"expected 8"),
])
def test_tempo_normalizer_rejects_invalid_native_identity(field,raw,message):
    span={
        "traceId":base64.b64encode(bytes.fromhex("88"*16)).decode(),
        "spanId":base64.b64encode(bytes.fromhex("99"*8)).decode(),
        "parentSpanId":base64.b64encode(bytes.fromhex("aa"*8)).decode(),
        "name":"GET","kind":2,"startTimeUnixNano":"1200000000","endTimeUnixNano":"1300000000",
    }
    span[field]=raw
    document={"batches":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"frontend"}}]},"scopeSpans":[{"spans":[span]}]}]}
    with pytest.raises(ValueError,match=message):
        tempo_normalizer.normalize(document)

def test_tempo_normalizer_rejects_noncanonical_base64_alias():
    canonical=base64.b64encode(bytes.fromhex("11"*16)).decode()
    alias=canonical[:-3]+"R=="
    assert alias!=canonical and base64.b64decode(alias)==base64.b64decode(canonical)
    document={"batches":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"frontend"}}]},"scopeSpans":[{"spans":[{
        "traceId":alias,"spanId":base64.b64encode(bytes.fromhex("22"*8)).decode(),
        "name":"GET","kind":2,"startTimeUnixNano":"1200000000",
        "endTimeUnixNano":"1300000000"}]}]}]}
    with pytest.raises(ValueError,match="base64 is not canonical"):
        tempo_normalizer.normalize(document)

@pytest.mark.parametrize("mutation",[
    "multi-anyvalue","critical-bool","duplicate-critical","lowercase-kind",
    "numeric-time","timestamp-alias","reversed-time","dict-name","absent-service",
])
def test_tempo_normalizer_rejects_forged_wire_fields(mutation):
    document={"batches":[{"resource":{"attributes":[
        {"key":"service.name","value":{"stringValue":"frontend"}}]},
        "scopeSpans":[{"spans":[{
            "traceId":base64.b64encode(bytes.fromhex("11"*16)).decode(),
            "spanId":base64.b64encode(bytes.fromhex("22"*8)).decode(),
            "name":"GET","kind":"SPAN_KIND_SERVER",
            "startTimeUnixNano":"1200000000","endTimeUnixNano":"1300000000",
            "attributes":[
                {"key":"http.request.method","value":{"stringValue":"GET"}},
                {"key":"url.path","value":{"stringValue":"/"}},
            ]}]}]}]}
    batch=document["batches"][0]; span=batch["scopeSpans"][0]["spans"][0]
    if mutation=="multi-anyvalue":
        batch["resource"]["attributes"][0]["value"]["boolValue"]=True
    elif mutation=="critical-bool":
        span["attributes"][0]["value"]={"boolValue":True}
    elif mutation=="duplicate-critical":
        span["attributes"].append(
            {"key":"url.path","value":{"stringValue":"/forged"}})
    elif mutation=="lowercase-kind": span["kind"]="server"
    elif mutation=="numeric-time": span["startTimeUnixNano"]=1_200_000_000
    elif mutation=="timestamp-alias": span["startTimeUnixNano"]="01200000000"
    elif mutation=="reversed-time": span["endTimeUnixNano"]="1100000000"
    elif mutation=="dict-name": span["name"]={"forged":"GET"}
    else: batch["resource"]["attributes"]=[]
    with pytest.raises(ValueError):
        tempo_normalizer.normalize(document)

def test_tempo_normalizer_accepts_exact_supported_string_kind():
    document={"batches":[{"resource":{"attributes":[
        {"key":"service.name","value":{"stringValue":"frontend"}}]},
        "scopeSpans":[{"spans":[{
            "traceId":base64.b64encode(bytes.fromhex("11"*16)).decode(),
            "spanId":base64.b64encode(bytes.fromhex("22"*8)).decode(),
            "name":"GET","kind":"SPAN_KIND_SERVER",
            "startTimeUnixNano":"1200000000","endTimeUnixNano":"1300000000"}]}]}]}
    assert tempo_normalizer.normalize(document)[0]["kind"]=="Server"

@pytest.mark.parametrize("mutation",[
    "extra-file","missing-file","empty-native","normalized-subset",
    "wrong-file","search-body","raw-tamper","noncanonical-base64",
])
def test_final_tempo_reread_rejects_missing_extra_or_tampered_raw_artifacts(tmp_path,mutation):
    run=tmp_path/mutation
    proof,spans,search_id=write_tempo_fixture(run)
    configuration={"measurementSeconds":1}
    workload={"requests":[{"startedAtEpoch":1.1,"endedAtEpoch":1.9}]}
    recomputed,request,window=kind_smoke.recompute_tempo_run(run,proof,configuration,workload)
    assert recomputed==spans and request["status"]==200 and window["startNs"]==1_100_000_000
    trace_path=run/"tempo-traces"/f"{search_id}.json"
    if mutation=="extra-file":
        (run/"tempo-traces"/"extra.json").write_text("{}\n")
    elif mutation=="missing-file":
        trace_path.unlink()
    elif mutation=="empty-native":
        trace_path.write_text(json.dumps({"batches":[]})+"\n")
    elif mutation=="normalized-subset":
        (run/"spans-normalized.json").write_text("[]\n")
    elif mutation=="wrong-file":
        payload=trace_path.read_text(); trace_path.unlink()
        wrong="3"*32
        (run/"tempo-search.json").write_text(json.dumps(
            {"traces":[{"traceID":wrong}]},indent=2,sort_keys=True)+"\n")
        (run/"tempo-traces"/f"{wrong}.json").write_text(payload)
    elif mutation=="search-body":
        (run/"tempo-search.json").write_text(
            (run/"tempo-search.json").read_text()+"\n")
    elif mutation=="raw-tamper":
        trace_path.write_text(trace_path.read_text().replace('"name": "GET"','"name": "POST"'))
    elif mutation=="noncanonical-base64":
        payload=trace_path.read_text()
        canonical=base64.b64encode(bytes.fromhex("00"+"11"*15)).decode()
        alias=canonical[:-3]+"R=="
        assert base64.b64decode(alias)==base64.b64decode(canonical)
        trace_path.write_text(payload.replace(canonical,alias))
    with pytest.raises((RuntimeError,ValueError)):
        kind_smoke.recompute_tempo_run(run,proof,configuration,workload)

@pytest.mark.parametrize("mutation",[
    "status","rounding","start-bound","limit","window-50ms","unrelated-window",
])
def test_final_tempo_reread_rejects_simultaneous_query_receipt_tamper(tmp_path,mutation):
    run=tmp_path/mutation
    proof,_,_=write_tempo_fixture(run)
    request_path=run/"tempo-search-request.json"
    request=json.loads(request_path.read_text())
    if mutation=="status":
        request["status"]=503
    elif mutation=="rounding":
        request["rounding"]["end"]="floor-nanoseconds-to-seconds"
    elif mutation=="start-bound":
        request["requestedUrl"]=request["requestedUrl"].replace("start=1","start=2")
        request["responseUrl"]=request["requestedUrl"]
        request["query"][1][1]="2"
    elif mutation=="limit":
        request["requestedUrl"]=request["requestedUrl"].replace("limit=1000","limit=999")
        request["responseUrl"]=request["requestedUrl"]
        request["query"][3][1]="999"
    elif mutation=="window-50ms":
        request["measurementWindow"]={"startNs":1_050_000_000,"endNs":2_050_000_000}
        request["requestedUrl"]=request["requestedUrl"].replace("start=1","start=1").replace(
            "end=2","end=3")
        request["responseUrl"]=request["requestedUrl"]
        request["query"][2][1]="3"
        proof["startNs"]=1_050_000_000; proof["endNs"]=2_050_000_000
    elif mutation=="unrelated-window":
        request["measurementWindow"]={"startNs":10_000_000_000,"endNs":11_000_000_000}
        request["requestedUrl"]=request["requestedUrl"].replace("start=1","start=10").replace(
            "end=2","end=11")
        request["responseUrl"]=request["requestedUrl"]
        request["query"][1][1]="10"; request["query"][2][1]="11"
    payload=json.dumps(request,indent=2,sort_keys=True)+"\n"
    request_path.write_text(payload)
    # Change both the on-disk request and the embedded receipt proof. The
    # frozen schedule/workload semantics, not hash equality alone, must reject.
    proof["searchRequest"]=request
    proof["searchRequestArtifact"]=acquisition.raw_artifact_record(
        "tempo-search-request.json",payload,1)
    if mutation=="unrelated-window":
        proof["startNs"]=10_000_000_000; proof["endNs"]=11_000_000_000
    with pytest.raises(RuntimeError):
        kind_smoke.recompute_tempo_run(
            run,proof,{"measurementSeconds":1},
            {"requests":[{"startedAtEpoch":1.1,"endedAtEpoch":1.9}]})

@pytest.mark.parametrize("mutation",[
    "missing","empty","normalized","body","status","api-status","result-type","namespace",
    "numeric-timestamp","bool-timestamp","timestamp-alias","object-line","null-line",
    "numeric-label","window-50ms","limit",
])
def test_final_loki_reread_rejects_missing_empty_or_joint_tamper(tmp_path,mutation):
    run=tmp_path/mutation
    proof,records,workload=write_loki_fixture(run)
    recomputed,request,window=kind_smoke.recompute_loki_run(
        run,proof,{"measurementSeconds":1},workload)
    assert recomputed==records and request["status"]==200 and window["startNs"]==1_100_000_000
    if mutation=="missing":
        (run/"logs-normalized.json").unlink()
    elif mutation=="empty":
        (run/"loki.json").write_text(json.dumps({"data":{"result":[]}})+"\n")
    elif mutation=="normalized":
        (run/"logs-normalized.json").write_text("[]\n")
    elif mutation=="body":
        (run/"loki.json").write_text((run/"loki.json").read_text()+"\n")
    elif mutation in {"api-status","result-type","namespace","numeric-timestamp",
                      "bool-timestamp","timestamp-alias","object-line","null-line",
                      "numeric-label"}:
        changed=json.loads((run/"loki.json").read_text())
        if mutation=="api-status":
            changed["status"]="error"
        elif mutation=="result-type":
            changed["data"]["resultType"]="matrix"
        elif mutation=="namespace":
            changed["data"]["result"][0]["stream"]["namespace"]="foreign"
        elif mutation=="numeric-timestamp":
            changed["data"]["result"][0]["values"][0][0]=2_000_000_000
        elif mutation=="bool-timestamp":
            changed["data"]["result"][0]["values"][0][0]=True
        elif mutation=="timestamp-alias":
            changed["data"]["result"][0]["values"][0][0]="02000000000"
        elif mutation=="object-line":
            changed["data"]["result"][0]["values"][0][1]={"message":"homepage"}
        elif mutation=="null-line":
            changed["data"]["result"][0]["values"][0][1]=None
        else:
            changed["data"]["result"][0]["stream"]["pod"]=7
        payload=json.dumps(changed,indent=2,sort_keys=True)+"\n"
        (run/"loki.json").write_text(payload)
        proof["rawArtifact"]=acquisition.raw_artifact_record("loki.json",payload,1)
        proof["queryRequest"]["bodyArtifact"]=proof["rawArtifact"]
    else:
        request_path=run/"loki-query-request.json"
        changed=json.loads(request_path.read_text())
        if mutation=="status":
            changed["status"]=503
        elif mutation=="window-50ms":
            changed["measurementWindow"]={"startNs":1_150_000_000,"endNs":2_950_000_000}
            changed["requestedUrl"]=changed["requestedUrl"].replace(
                "start=1100000000","start=1150000000").replace(
                "end=2900000000","end=2950000000")
            changed["responseUrl"]=changed["requestedUrl"]
            changed["query"][1][1]="1150000000"; changed["query"][2][1]="2950000000"
            proof["startNs"]=1_150_000_000; proof["endNs"]=2_950_000_000
        elif mutation=="limit":
            changed["requestedUrl"]=changed["requestedUrl"].replace("limit=5000","limit=4999")
            changed["responseUrl"]=changed["requestedUrl"]
            changed["query"][3][1]="4999"; proof["limit"]=4999
        payload=json.dumps(changed,indent=2,sort_keys=True)+"\n"
        request_path.write_text(payload)
        proof["queryRequest"]=changed
        proof["queryRequestArtifact"]=acquisition.raw_artifact_record(
            "loki-query-request.json",payload,1)
    with pytest.raises((RuntimeError,ValueError)):
        kind_smoke.recompute_loki_run(run,proof,{"measurementSeconds":1},workload)

def test_bound_run_inputs_rejects_simultaneous_receipt_request_shift(tmp_path):
    run=tmp_path/"run"; run.mkdir()
    workload={"requests":[
        {"startedAtEpoch":1.1,"endedAtEpoch":1.2,"error":None},
        {"startedAtEpoch":2.1,"endedAtEpoch":2.2,"error":"HTTP 500"},
        {"startedAtEpoch":3.1,"endedAtEpoch":3.2,"error":None},
    ]}
    intervention={"scaledToZeroAtEpoch":2.0,"scaleOneAtEpoch":3.0,
                  "rolloutReadyAtEpoch":3.0,"preFaultSuccessfulCount":1,
                  "scaleZeroFailureCount":1,"postRecoverySuccessfulCount":1}
    (run/"workload.json").write_text(json.dumps(workload))
    (run/"intervention.json").write_text(json.dumps(intervention))
    receipt_row={"workload":workload,"intervention":intervention,
                 "acquisitionProof":{"tempo":{"searchRequest":{"measurementWindow":{
                     "startNs":1_000_000_000,"endNs":4_000_000_000}}}}}
    assert kind_smoke.load_bound_run_inputs(run,receipt_row)==(workload,intervention)
    shifted=json.loads(json.dumps(receipt_row))
    for row in shifted["workload"]["requests"]:
        row["startedAtEpoch"]+=100; row["endedAtEpoch"]+=100
    shifted["acquisitionProof"]["tempo"]["searchRequest"]["measurementWindow"]={
        "startNs":101_000_000_000,"endNs":104_000_000_000}
    with pytest.raises(RuntimeError,match="workload artifact differs"):
        kind_smoke.load_bound_run_inputs(run,shifted)
    shifted=json.loads(json.dumps(receipt_row))
    shifted["intervention"]["scaledToZeroAtEpoch"]+=100
    shifted["acquisitionProof"]["tempo"]["searchRequest"]["measurementWindow"]={
        "startNs":101_000_000_000,"endNs":104_000_000_000}
    with pytest.raises(RuntimeError,match="intervention artifact differs"):
        kind_smoke.load_bound_run_inputs(run,shifted)

@pytest.mark.parametrize("tampered",[
    {"startNs":12_000_000_000,"endNs":50_000_000_000,"bounded":True},
    {"startNs":12_000_000_000,"endNs":60_000_000_000,"bounded":True},
])
def test_visibility_window_rejects_flattering_subwindow_or_postfault_extension(tampered):
    request={"measurementWindow":{"startNs":12_000_000_000,"endNs":60_000_000_000,
                                  "executorStartNs":10_000_000_000}}
    intervention={"scaledToZeroAtEpoch":55.0}
    derived=kind_smoke.derived_visibility_window(
        request,intervention,{"faultAtSeconds":45,"visibilitySafetyMarginSeconds":5})
    assert derived=={"startNs":12_000_000_000,"endNs":52_000_000_000,
                     "bounded":True,
                     "endSource":"first-request-start-plus-frozen-faultAt-minus-safety-margin"}
    assert tampered!=derived

def test_visibility_end_uses_frozen_fault_offset_not_actual_scale_completion():
    request={"measurementWindow":{"startNs":12_000_000_000,"endNs":60_000_000_000,
                                  "executorStartNs":10_000_000_000}}
    configuration={"faultAtSeconds":45,"visibilitySafetyMarginSeconds":5}
    scheduled=kind_smoke.derived_visibility_window(
        request,{"scaledToZeroAtEpoch":20.0},configuration)
    delayed=kind_smoke.derived_visibility_window(
        request,{"scaledToZeroAtEpoch":24.9},configuration)
    assert scheduled==delayed
    assert scheduled["endNs"]==52_000_000_000

def test_visibility_boundary_accounts_for_workload_startup_lag():
    request={"measurementWindow":{"executorStartNs":10_000_000_000,
                                  "startNs":12_000_000_000,"endNs":60_000_000_000}}
    boundary=kind_smoke.derived_visibility_window(
        request,{"startedAtEpoch":55.1},
        {"faultAtSeconds":45,"visibilitySafetyMarginSeconds":5})
    assert boundary["startNs"]==12_000_000_000
    assert boundary["endNs"]==52_000_000_000
    delayed={"measurementWindow":{"executorStartNs":10_000_000_000,
                                   "startNs":15_000_000_001,"endNs":70_000_000_000}}
    with pytest.raises(RuntimeError,match="startup lag exceeds"):
        kind_smoke.derived_visibility_window(
            delayed,{}, {"faultAtSeconds":45,"visibilitySafetyMarginSeconds":5})

def test_measurement_window_is_exactly_derived_from_raw_workload(tmp_path):
    run=tmp_path/"run"; run.mkdir()
    workload={"requests":[{"startedAtEpoch":10.1,"endedAtEpoch":10.2},
                          {"startedAtEpoch":11.1,"endedAtEpoch":11.9}]}
    (run/"workload.json").write_text(json.dumps(workload,indent=2,sort_keys=True)+"\n")
    record,_=kind_smoke.write_measurement_window(
        run,10_000_000_000,12_000_000_000,{"measurementSeconds":2})
    assert record["startNs"]==10_100_000_000 and record["endNs"]==11_900_000_000
    assert kind_smoke.load_measurement_window(
        run,workload,{"measurementSeconds":2})[0]==record
    changed=json.loads((run/"measurement-window.json").read_text())
    changed["startNs"]+=50_000_000; changed["endNs"]+=50_000_000
    (run/"measurement-window.json").write_text(json.dumps(changed,indent=2,sort_keys=True)+"\n")
    with pytest.raises(RuntimeError,match="deterministic workload bounds"):
        kind_smoke.load_measurement_window(run,workload,{"measurementSeconds":2})

@pytest.mark.parametrize("mutation",["scenario","scheduled-at","outage","phase-time"])
def test_intervention_schedule_binding_rejects_frozen_drift(mutation):
    configuration={"fault":"productcatalog-kubernetes-scale-zero",
                   "faultAtSeconds":45,"visibilitySafetyMarginSeconds":5,
                   "outageSeconds":15}
    window={"executorStartNs":10_000_000_000,
            "startNs":12_000_000_000,"endNs":80_000_000_000}
    intervention={"scenario":"productcatalog-kubernetes-scale-zero",
                  "scheduledAtSeconds":45,"scheduledScaleZeroSeconds":15,
                  "startedAtEpoch":55,"scaledToZeroAtEpoch":60,
                  "scaleOneAtEpoch":70,"rolloutReadyAtEpoch":75}
    assert kind_smoke.intervention_schedule_blockers(intervention,configuration,window)==[]
    changed=json.loads(json.dumps(intervention))
    if mutation=="scenario": changed["scenario"]="different"
    elif mutation=="scheduled-at": changed["scheduledAtSeconds"]=46
    elif mutation=="outage": changed["scheduledScaleZeroSeconds"]=14
    else: changed["scaleOneAtEpoch"]=90
    assert kind_smoke.intervention_schedule_blockers(changed,configuration,window)

@pytest.mark.parametrize("mutation",["pod","span"])
def test_final_synthetic_exclusion_recomputes_raw_manifest_pods_and_spans(tmp_path,mutation):
    run=tmp_path/mutation; run.mkdir()
    manifest="apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: frontend\n"
    (run/"applied.yaml").write_text(manifest)
    readiness={"pods":["frontend-1"],"readyOrSucceeded":True,"podCount":1}
    (run/"application-readiness.json").write_text(json.dumps(readiness)+"\n")
    spans=[{"serviceName":"frontend"}]
    frozen=synthetic.proof(manifest,readiness["pods"],spans,True)
    assert kind_smoke.recompute_synthetic_exclusion(run,spans,frozen)==frozen
    if mutation=="pod":
        readiness["pods"].append("loadgenerator-1")
        (run/"application-readiness.json").write_text(json.dumps(readiness)+"\n")
    else:
        spans.append({"serviceName":"synthetic-load-generator"})
    forged=json.loads(json.dumps(frozen)); forged["passed"]=True
    with pytest.raises(RuntimeError,match="synthetic-trace exclusion differs"):
        kind_smoke.recompute_synthetic_exclusion(run,spans,forged)

def test_every_lgtm_file_is_classified_and_contract_not_copied():
    module=ROOT/"modules/online-boutique-lgtm"; result=module_audit.audit(module)
    assert result["verdict"]=="pass",result
    assert result["classified_files"]==17
    assert not (module/"goal.json").exists() and not (module/"activation/catalog.json").exists()

def test_generated_overlays_reference_a_kustomize_base_inside_materialization(tmp_path, monkeypatch):
    monkeypatch.setattr(materialize,"verify_checkout",lambda path,commit,label:{"commit":commit})
    monkeypatch.setattr(materialize,"verify_shared_materialization",lambda path:{"sha256":"a"*64})
    monkeypatch.setattr(materialize,"sha256",lambda path: materialize.EXPECTED_MANIFEST_SHA256 if path==materialize.ACQUISITION_UPSTREAM/materialize.UPSTREAM_MANIFEST else "b"*64)
    out=tmp_path/"generated"
    materialize.materialize(out,tmp_path/"app")
    assert (out/"base/kustomization.yaml").is_file()
    for posture in ("none","selected","full"):
        text=(out/f"postures/{posture}/kustomization.yaml").read_text()
        assert "../../base" in text and "../../application.yaml" not in text
        assert "patches:\n  - path: posture-01.yaml" in text
        assert len(list((out/f"postures/{posture}").glob("posture-*.yaml")))==3
        assert "patchesStrategicMerge" not in text
        result=subprocess.run(["kubectl","kustomize",str(out/f"postures/{posture}")],capture_output=True,text=True)
        assert result.returncode==0,result.stderr
        assert "kind: Deployment" in result.stdout
        assert "kind: Ingress" not in result.stdout
        assert result.stdout.count("name: SHOPPING_ASSISTANT_SERVICE_ADDR")==1
        assert result.stdout.count("name: ENABLE_ASSISTANT")==1
        assert "value: shoppingassistantservice:80" in result.stdout
        assert 'value: "false"' in result.stdout
        runtime=materialize.audit_runtime_contract(
            result.stdout,materialize.POSTURE_TRACING[posture])
        assert runtime["status"]=="passed"
        for service in ("frontend","productcatalogservice","currencyservice"):
            assert f"name: {service}" in result.stdout
        assert "name: ENABLE_STATS" not in "\n---\n".join(
            materialize._single_document(materialize.yaml_documents(result.stdout),"Deployment",service)
            for service in ("frontend","productcatalogservice","currencyservice"))
    proof=json.loads((out/materialize.SENTINEL).read_text())
    assert proof["kustomize"]["renderStatus"]=="passed"
    assert set(proof["kustomize"]["renders"])=={"none","selected","full"}
    assert proof["transformation"]["removedIngresses"]==["ingress-microservices"]
    assert proof["transformation"]["runtimeCompatibility"]["status"]=="passed"
    assert proof["transformation"]["runtimeCompatibilityChanges"]["removedLegacyNoOpEnvironment"]=={
        "ENABLE_STATS":["currencyservice","frontend","productcatalogservice"]}
    for posture,expected in materialize.POSTURE_TRACING.items():
        runtime=proof["kustomize"]["renders"][posture]["runtimeCompatibility"]
        assert runtime["status"]=="passed"
        assert runtime["expectedTracing"]==expected
        assert {service:row["environment"]["ENABLE_TRACING"]
                for service,row in runtime["sourceBuiltDeployments"].items()}==expected

    bad_overlay=out/"postures/none/posture-01.yaml"
    payload=bad_overlay.read_text()
    mutated=payload.replace('name: ENABLE_TRACING, value: "0"',
                            'name: ENABLE_TRACING, value: "1"',1)
    assert mutated!=payload
    bad_overlay.write_text(mutated)
    with pytest.raises(RuntimeError,match="frontend literal environment differs"):
        materialize.render_postures(out)
    bad_overlay.write_text(payload)

    routing_overlay=out/"postures/none/posture-02.yaml"
    routing_payload=routing_overlay.read_text()
    routing_mutation=routing_payload.replace(
        "spec: {template: {spec:",
        "spec: {selector: {matchLabels: {app: disconnectedcatalog}}, "
        "template: {metadata: {labels: {app: disconnectedcatalog}}, spec:",1)
    assert routing_mutation!=routing_payload
    routing_overlay.write_text(routing_mutation)
    with pytest.raises(RuntimeError,match="productcatalogservice does not resolve to exactly"):
        materialize.render_postures(out)

def test_shared_materialization_accepts_the_current_currency_guard_id(tmp_path):
    app = tmp_path / "app"
    app.mkdir()
    (app / "source.txt").write_text("pinned materialization\n")
    digest = materialize.tree_sha256(app)
    proof = {
        "upstreamCommit": materialize.EXPECTED_APP_SHA,
        "materializedSourceSha256": digest,
        "sourceGuardChanges": [
            *[{"id": item} for item in sorted(materialize.EXPECTED_SOURCE_GUARDS)],
        ],
    }
    (app / ".obsplacement-materialized").write_text(json.dumps(proof))
    (app / ".source.sha256").write_text(digest + "\n")
    observed = materialize.verify_shared_materialization(app)
    assert observed["sha256"] == digest
    assert "currency-grpc-source-guard" in observed["sourceGuards"]

def test_tool_bootstrap_and_runtime_pins_are_exact(tmp_path):
    assert bootstrap.safe_prefix(tmp_path / "owned" / "tools").is_absolute()
    assert bootstrap.TOOL_VERSIONS == kind_smoke.EXPECTED_TOOLS
    assert bootstrap.PYTHON_INVOCATION_FLAGS == kind_smoke.PYTHON_INVOCATION_FLAGS == ["-I","-B","-S"]
    assert bootstrap.PYTHON_INSTALL_KEY == kind_smoke.PYTHON_INSTALL_KEY == "cpython-3.13.5-linux-x86_64-gnu"
    assert bootstrap.PYTHON_ALIAS_KEY == kind_smoke.PYTHON_ALIAS_KEY == "cpython-3.13-linux-x86_64-gnu"
    assert all(len(row["sha256"])==64 for row in bootstrap.TOOLS.values())
    assert all(len(value)==64 for value in kind_smoke.CHART_SHA256.values())


def managed_tool_receipt(tmp_path):
    managed_root=tmp_path/"python"/kind_smoke.PYTHON_INSTALL_KEY
    managed_bin=managed_root/"bin"; managed_bin.mkdir(parents=True)
    managed_interpreter=managed_bin/"python3.13"; managed_interpreter.write_text("python-runtime")
    stdlib=managed_root/"lib/python3.13/os.py"; stdlib.parent.mkdir(parents=True)
    stdlib.write_text("pinned-stdlib")
    registry=tmp_path/"python"
    (registry/".gitignore").write_text("*\n"); (registry/".lock").write_text("")
    (registry/".temp").mkdir(); alias=registry/kind_smoke.PYTHON_ALIAS_KEY
    alias.symlink_to(managed_root)
    binary_dir=tmp_path/"bin"; binary_dir.mkdir()
    tools={}
    for name,version in kind_smoke.EXPECTED_TOOLS.items():
        path=binary_dir/name
        if name=="python3.13": path.symlink_to(managed_interpreter)
        else: path.write_text(name)
        output=f"Python {version}" if name=="python3.13" else f"{name} {version}"
        tools[name]={"versionPin":version,"installedPath":str(path),
                     "installedSha256":kind_smoke.sha256(path),"reportedVersion":output}
    tools["python3.13"].update({
        "managedInstallPath":str(managed_root),
        "managedInterpreterPath":str(managed_interpreter),
        "managedInstallKey":kind_smoke.PYTHON_INSTALL_KEY,
        "managedRegistryPath":str(registry),
        "managedAliasPath":str(alias),
        "managedAliasKey":kind_smoke.PYTHON_ALIAS_KEY,
        "requiredInvocationFlags":["-I","-B","-S"],
        "managedTree":kind_smoke.managed_tree_proof(managed_root),
        "managedRegistryTree":kind_smoke.managed_tree_proof(registry),
        "runtimeProof":{"version":[3,13,5],"executable":str(binary_dir/"python3.13"),
            "prefix":str(managed_root),"basePrefix":str(managed_root),
            "isolated":1,"dontWriteBytecode":1,"noSite":1},
        "acquisition":{"command":["uv","--no-config","python","install","3.13.5",
            "--install-dir",str(tmp_path/"python"),"--no-bin","--no-cache"],
            "uvInstalledSha256":tools["uv"]["installedSha256"],
            "managedInstallKey":kind_smoke.PYTHON_INSTALL_KEY,
            "managedAliasKey":kind_smoke.PYTHON_ALIAS_KEY,
            "sanitizedEnvironmentPrefixes":["PYTHON","UV_","LD_"],
            "sanitizedEnvironmentKeys":["LD_LIBRARY_PATH","LD_PRELOAD"],
            "evidenceCeiling":"pinned-uv-https-plus-installed-tree-noncanonical"},
    })
    tools["python3.13"]["installedArtifact"]={"kind":"deterministic-directory-tree-v1",
        **tools["python3.13"]["managedTree"]}
    receipt_path=tmp_path/"toolchain.json"
    receipt_path.write_text(json.dumps({"platform":"linux-amd64","prefix":str(tmp_path),"tools":tools}))
    return receipt_path,tools,managed_root,managed_interpreter,stdlib


def test_tool_bootstrap_rejects_preexisting_python_destination(tmp_path):
    install_dir=tmp_path/"python"; entry=tmp_path/"bin/python3.13"
    install_dir.mkdir()
    with pytest.raises(RuntimeError,match="must be absent"):
        bootstrap.require_fresh_python_destination(install_dir,entry)


def bind_managed_runtime(monkeypatch,tools,managed_root):
    class Result:
        def __init__(self,stdout): self.stdout=stdout; self.stderr=""; self.returncode=0
    monkeypatch.setattr(kind_smoke.shutil,"which",lambda name:tools[name]["installedPath"])
    by_path={str(Path(item["installedPath"]).absolute()):item for item in tools.values()}
    monkeypatch.setattr(kind_smoke,"command",
        lambda argv,**kwargs:Result(by_path[str(Path(argv[0]).absolute())]["reportedVersion"]))
    monkeypatch.setattr(kind_smoke.sys,"executable",tools["python3.13"]["installedPath"])
    monkeypatch.setattr(kind_smoke.sys,"version_info",(3,13,5,"final",0))
    monkeypatch.setattr(kind_smoke.sys,"prefix",str(managed_root))
    monkeypatch.setattr(kind_smoke.sys,"base_prefix",str(managed_root))
    monkeypatch.setattr(kind_smoke.sys,"flags",types.SimpleNamespace(
        isolated=1,dont_write_bytecode=1,no_site=1))
    for key in list(os.environ):
        if (key.startswith("PYTHON") or key.startswith("UV_") or key.startswith("LD_") or
                key in {"LD_LIBRARY_PATH","LD_PRELOAD"}): monkeypatch.delenv(key)


def test_tool_receipt_binds_exact_managed_tree_and_runtime(monkeypatch,tmp_path):
    receipt_path,tools,managed_root,_,_=managed_tool_receipt(tmp_path)
    bind_managed_runtime(monkeypatch,tools,managed_root)
    assert kind_smoke.verify_tool_receipt(receipt_path)["tools"]["python3.13"]["versionPin"]=="3.13.5"


def test_tool_receipt_rejects_non_executable_stdlib_tamper(monkeypatch,tmp_path):
    receipt_path,tools,managed_root,_,stdlib=managed_tool_receipt(tmp_path)
    bind_managed_runtime(monkeypatch,tools,managed_root)
    assert bootstrap.managed_tree_proof(managed_root)==kind_smoke.managed_tree_proof(managed_root)
    stdlib.write_text("tampered-stdlib")
    with pytest.raises(RuntimeError,match="runtime tree changed"):
        kind_smoke.verify_tool_receipt(receipt_path)


def test_managed_tree_rejects_external_symlink(monkeypatch,tmp_path):
    receipt_path,tools,managed_root,_,_=managed_tool_receipt(tmp_path)
    bind_managed_runtime(monkeypatch,tools,managed_root)
    external=tmp_path/"external-runtime"; external.write_text("unbound")
    (managed_root/"lib/python3.13/external.py").symlink_to(external)
    with pytest.raises(RuntimeError,match="symlink escapes"):
        kind_smoke.verify_tool_receipt(receipt_path)


def test_tool_receipt_rejects_uv_registry_alias_or_lock_drift(monkeypatch,tmp_path):
    receipt_path,tools,managed_root,_,_=managed_tool_receipt(tmp_path)
    bind_managed_runtime(monkeypatch,tools,managed_root)
    (tmp_path/"python/.lock").write_text("drift")
    with pytest.raises(RuntimeError,match="registry tree changed"):
        kind_smoke.verify_tool_receipt(receipt_path)


def test_tool_receipt_rejects_wrong_patch_version(monkeypatch,tmp_path):
    receipt_path,tools,managed_root,_,_=managed_tool_receipt(tmp_path)
    tools["python3.13"]["reportedVersion"]="Python 3.13.6"
    receipt_path.write_text(json.dumps({"platform":"linux-amd64","tools":tools}))
    bind_managed_runtime(monkeypatch,tools,managed_root)
    with pytest.raises(RuntimeError,match="exact pinned patch version"):
        kind_smoke.verify_tool_receipt(receipt_path)


def test_tool_receipt_rejects_venv_and_equivalent_symlink(monkeypatch,tmp_path):
    receipt_path,tools,managed_root,managed_interpreter,_=managed_tool_receipt(tmp_path)
    bind_managed_runtime(monkeypatch,tools,managed_root)
    venv=tmp_path/"venv"; venv.mkdir(); alternate=venv/"python3.13"
    alternate.symlink_to(managed_interpreter)
    monkeypatch.setattr(kind_smoke.sys,"executable",str(alternate))
    monkeypatch.setattr(kind_smoke.sys,"prefix",str(venv))
    with pytest.raises(RuntimeError,match="exact receipted Python entry point"):
        kind_smoke.verify_tool_receipt(receipt_path)
    monkeypatch.setattr(kind_smoke.sys,"executable",tools["python3.13"]["installedPath"])
    with pytest.raises(RuntimeError,match="virtual environment"):
        kind_smoke.verify_tool_receipt(receipt_path)


def test_tool_receipt_rejects_missing_isolation_flags(monkeypatch,tmp_path):
    receipt_path,tools,managed_root,_,_=managed_tool_receipt(tmp_path)
    bind_managed_runtime(monkeypatch,tools,managed_root)
    monkeypatch.setattr(kind_smoke.sys,"flags",types.SimpleNamespace(
        isolated=1,dont_write_bytecode=0,no_site=1))
    with pytest.raises(RuntimeError,match="-I -B -S"):
        kind_smoke.verify_tool_receipt(receipt_path)


@pytest.mark.parametrize("variable",["PYTHONPATH","UV_PYTHON_DOWNLOADS_JSON_URL",
                                      "LD_PRELOAD","LD_LIBRARY_PATH","LD_AUDIT"])
def test_tool_receipt_rejects_runtime_environment_injection(monkeypatch,tmp_path,variable):
    receipt_path,tools,managed_root,_,_=managed_tool_receipt(tmp_path)
    bind_managed_runtime(monkeypatch,tools,managed_root)
    monkeypatch.setenv(variable,"/tmp/untrusted")
    with pytest.raises(RuntimeError,match="runtime environment overrides"):
        kind_smoke.verify_tool_receipt(receipt_path)

def test_runtime_image_receipt_preserves_every_native_id(monkeypatch,tmp_path):
    document={"items":[{"metadata":{"name":"frontend-abc"},"spec":{"containers":[{"name":"server","image":"frontend:pin"}]},"status":{"containerStatuses":[{"name":"server","imageID":"docker-pullable://frontend@sha256:"+"a"*64}]}}]}
    class Result:
        stdout=json.dumps(document)
    monkeypatch.setenv("OBSPLACEMENT_KUBECTL_CACHE_DIR",str(tmp_path/"kubectl-cache"))
    monkeypatch.setattr(kind_smoke,"command",lambda argv,check=True:Result())
    rows=kind_smoke.runtime_images("kind-owned")
    assert rows==[{"pod":"frontend-abc","container":"server","declaredImage":"frontend:pin","imageIDRaw":"docker-pullable://frontend@sha256:"+"a"*64,"imageID":"sha256:"+"a"*64}]

def test_goal_visibility_requires_every_sensor_and_shared_native_trace():
    goal=json.loads((ROOT/"modules/online-boutique/goals/homepage-path.json").read_text())
    spans=[
        {"traceId":"aa","spanId":"01","parentSpanId":"","serviceName":"frontend","name":"GET","kind":"Server",
         "attributes":{"http.request.method":"GET","url.path":"/"}},
        {"traceId":"aa","spanId":"02","parentSpanId":"01","serviceName":"frontend","name":"hipstershop.ProductCatalogService/ListProducts","kind":"Client"},
        {"traceId":"aa","spanId":"03","parentSpanId":"02","serviceName":"productcatalogservice","name":"hipstershop.ProductCatalogService/ListProducts","kind":"Server"},
    ]
    assert kind_smoke.goal_visibility(spans,goal)["verdict"]=="pass"
    assert kind_smoke.goal_visibility(spans[:-1],goal)["verdict"]=="blocked"

def test_workload_denominator_gate_rejects_dropped_raw_rows():
    configuration={"measurementSeconds":10,"requestsPerSecond":2,"concurrency":4}
    valid={"durationSeconds":10,"ratePerSecond":2,"concurrency":4,"offered":20,"completed":18,"failed":2,"requests":[{}]*20}
    assert kind_smoke.workload_blockers(valid,configuration)==[]
    valid["requests"].pop()
    assert "raw request rows do not equal offered" in kind_smoke.workload_blockers(valid,configuration)

def test_port_ownership_preflight_is_bounded(monkeypatch):
    events=[]
    class Probe:
        def setsockopt(self,*args): events.append(("option",args))
        def bind(self,address): events.append(("bind",address))
        def close(self): events.append(("close",))
    monkeypatch.setattr(kind_smoke.socket,"socket",Probe)
    kind_smoke.assert_ports_free((18080,13100,13200))
    assert [event[1] for event in events if event[0]=="bind"]==[("127.0.0.1",18080),("127.0.0.1",13100),("127.0.0.1",13200)]
    assert sum(event[0]=="close" for event in events)==3

def test_every_kubectl_invocation_uses_owned_cache(monkeypatch,tmp_path):
    monkeypatch.setenv("OBSPLACEMENT_KUBECTL_CACHE_DIR",str(tmp_path/"kubectl-cache"))
    argv=kind_smoke.kube("kind-owned","get","pods")
    assert argv[:5]==["kubectl","--cache-dir",str(tmp_path/"kubectl-cache"),"--context","kind-owned"]

def test_helm_and_kubectl_share_only_owned_client_state(monkeypatch,tmp_path):
    monkeypatch.delenv("KUBECACHEDIR",raising=False)
    kubeconfig,helm_home,kube_cache,docker_config=kind_smoke.configure_owned_client_state(tmp_path)
    assert kind_smoke.os.environ["KUBECONFIG"]==str(kubeconfig)
    assert kind_smoke.os.environ["KUBECACHEDIR"]==str(kube_cache)
    assert kind_smoke.os.environ["OBSPLACEMENT_KUBECTL_CACHE_DIR"]==str(kube_cache)
    assert kind_smoke.os.environ["HELM_CONFIG_HOME"].startswith(str(helm_home))
    assert kind_smoke.os.environ["DOCKER_CONFIG"]==str(docker_config)
    assert kube_cache.is_dir()

def test_kind_image_inspection_uses_crictl_flag_before_image(monkeypatch,tmp_path):
    calls=[]; image_id="sha256:"+"a"*64; source="b"*64
    class Result:
        def __init__(self,stdout=""): self.stdout=stdout; self.stderr=""; self.returncode=0
    def fake_command(argv,**kwargs):
        calls.append(argv)
        if argv[:3]==["docker","image","inspect"]:
            return Result(json.dumps([{"Id":image_id,"Config":{"Labels":{"com.observability-placement.materialized-source":source}}}]))
        if argv[:4]==["docker","exec","owned-control-plane","crictl"]:
            return Result(json.dumps({"status":{"id":image_id,"repoDigests":["docker.io/library/import@sha256:"+"c"*64]}}))
        if argv[:3]==["docker","buildx","ls"]:
            return Result(json.dumps({"Name":"owned-builder","Driver":"docker-container"})+"\n")
        return Result()
    monkeypatch.setattr(kind_smoke,"command",fake_command)
    kind_smoke.build_images(tmp_path,tmp_path,source,"owned")
    crictl=[argv for argv in calls if argv[:4]==["docker","exec","owned-control-plane","crictl"]]
    assert all(argv[4:7]==["inspecti","-o","json"] for argv in crictl)


def test_schedule_requires_exact_block_posture_set_and_live_shared_hashes(tmp_path):
    generated=tmp_path/"application.yaml"; generated.write_text("kind: List\nitems: []\n")
    shared={"goalRef":"modules/online-boutique/goals/homepage-path.json",
            "goalSha256":kind_smoke.sha256(ROOT/"modules/online-boutique/goals/homepage-path.json"),
            "activationRef":"modules/online-boutique/activation/catalog.json",
            "activationSha256":kind_smoke.sha256(ROOT/"modules/online-boutique/activation/catalog.json")}
    proof={"acquisitionSource":{"commit":materialize.EXPECTED_ACQUISITION_SHA},
           "applicationSource":{"commit":materialize.EXPECTED_APP_SHA},
           "applicationMaterialization":{"sha256":"a"*64},"sharedContract":shared,
           "generatedConfigSha256":{"application.yaml":kind_smoke.sha256(generated)},
           "kustomize":{"command":["kubectl","kustomize"],"renders":{
               posture:{"sha256":str(index)*64} for index,posture in enumerate(("none","selected","full"),1)}}}
    marker=tmp_path/".obsplacement-lgtm-materialized"; marker.write_text(json.dumps(proof))
    plan=campaign.build(args(tmp_path,tempo_chart_version="1.61.3",
                             loki_chart_version="0.80.6",promtail_chart_version="6.17.1"))
    schedule=tmp_path/"schedule.json"; schedule.write_text(json.dumps(plan))
    assert kind_smoke.verify_schedule(schedule,tmp_path,"obsplacement-test")["runs"]==plan["runs"]
    plan["configuration"]["visibilitySafetyMarginSeconds"]=4
    schedule.write_text(json.dumps(plan))
    with pytest.raises(RuntimeError,match="workload/fault domain"):
        kind_smoke.verify_schedule(schedule,tmp_path,"obsplacement-test")
    plan["configuration"]["visibilitySafetyMarginSeconds"]=5
    plan["runs"]=[{"block":1,"posture":"full"} for _ in plan["runs"]]
    schedule.write_text(json.dumps(plan))
    with pytest.raises(RuntimeError,match="exact posture permutation"):
        kind_smoke.verify_schedule(schedule,tmp_path,"obsplacement-test")


def test_posture_proof_binds_exact_guards_and_runtime_repo_digest(monkeypatch,tmp_path):
    runtime="docker.io/library/import@sha256:"+"a"*64
    image_id="sha256:"+"b"*64
    build={"images":{name:{"tag":f"obs/{name}:pin","imageID":image_id,
                            "nodeImageID":image_id,"nodeRepoDigests":[runtime]}
                     for name in ("frontend","productcatalogservice","currencyservice")}}
    proof={"applicationMaterialization":{"sourceGuards":sorted(materialize.EXPECTED_SOURCE_GUARDS)}}
    wrong={"value":False}
    class Result:
        def __init__(self,stdout): self.stdout=stdout; self.stderr=""; self.returncode=0
    def fake_command(argv,**kwargs):
        if "deployment" in argv:
            service=argv[argv.index("deployment")+1]
            control={"frontend":"frontend","productcatalogservice":"productcatalog",
                     "currencyservice":"currency"}[service]
            expected=json.loads((ROOT/"modules/online-boutique/activation/catalog.json").read_text())["postures"]["full"][control]
            return Result(json.dumps({"spec":{"template":{"spec":{"containers":[{
                "image":build["images"][service]["tag"],"env":[{"name":"ENABLE_TRACING","value":expected}]}]}}}}))
        label=argv[argv.index("-l")+1]
        service={"app.kubernetes.io/name=frontend":"frontend","app=productcatalogservice":"productcatalogservice",
                 "app=currencyservice":"currencyservice"}[label]
        observed="docker.io/library/wrong@sha256:"+"c"*64 if wrong["value"] and service=="currencyservice" else runtime
        return Result(json.dumps({"items":[{"status":{"containerStatuses":[{"imageID":observed}]}}]}))
    monkeypatch.setenv("OBSPLACEMENT_KUBECTL_CACHE_DIR",str(tmp_path/"cache"))
    monkeypatch.setattr(kind_smoke,"command",fake_command)
    valid=kind_smoke.posture_proof("kind-owned","full",build,proof)
    assert valid["sourceGuarded"] and valid["sourceGuardSetExact"]
    assert set(valid["sourceGuardChangeIds"])==materialize.EXPECTED_SOURCE_GUARDS
    wrong["value"]=True
    assert not kind_smoke.posture_proof("kind-owned","full",build,proof)["sourceGuarded"]


def test_service_endpoint_gate_requires_both_ready_native_views(monkeypatch,tmp_path):
    expected={"frontend-service":{"targetPort":8080},"productcatalogservice":{"targetPort":3550}}
    slices={"items":[
        {"metadata":{"labels":{"kubernetes.io/service-name":"frontend-service"}},
         "ports":[{"port":8080}],"endpoints":[{"conditions":{"ready":True},"addresses":["10.0.0.1"]}]},
        {"metadata":{"labels":{"kubernetes.io/service-name":"productcatalogservice"}},
         "ports":[{"port":3550}],"endpoints":[{"conditions":{"ready":True},"addresses":["10.0.0.2"]}]},
    ]}
    endpoints={"items":[
        {"metadata":{"name":"frontend-service"},"subsets":[{"ports":[{"port":8080}],"addresses":[{"ip":"10.0.0.1"}]}]},
        {"metadata":{"name":"productcatalogservice"},"subsets":[{"ports":[{"port":3550}],"addresses":[{"ip":"10.0.0.2"}]}]},
    ]}
    class Result:
        def __init__(self,document): self.returncode=0; self.stdout=json.dumps(document); self.stderr=""
    def fake(argv,check=False):
        return Result(slices if "endpointslices.discovery.k8s.io" in argv else endpoints)
    monkeypatch.setenv("OBSPLACEMENT_KUBECTL_CACHE_DIR",str(tmp_path/"cache"))
    monkeypatch.setattr(kind_smoke,"command",fake)
    observed=kind_smoke.service_endpoint_readiness("kind-owned",expected)
    assert observed["passed"] and set(observed["services"])==set(expected)
    assert receipt.endpoint_proof_blockers(observed)==[]
    assert all(row["stdoutSha256"]==hashlib.sha256(row["stdout"].encode()).hexdigest()
               for row in observed["queries"].values())
    slices["items"][1]["endpoints"][0]["conditions"]["ready"]=False
    blocked=kind_smoke.service_endpoint_readiness("kind-owned",expected)
    assert not blocked["passed"] and any("productcatalogservice" in row for row in blocked["blockers"])


def test_endpoint_gate_rejects_udp_and_split_port_address_association():
    expected={"adservice":9555}
    udp=endpoint_fixture(expected)
    for query_name in ("endpointSlices","endpoints"):
        document=json.loads(udp["queries"][query_name]["stdout"])
        if query_name=="endpointSlices": document["items"][0]["ports"][0]["protocol"]="UDP"
        else: document["items"][0]["subsets"][0]["ports"][0]["protocol"]="UDP"
        payload=json.dumps(document)
        udp["queries"][query_name]["stdout"]=payload
        udp["queries"][query_name]["stdoutSha256"]=hashlib.sha256(payload.encode()).hexdigest()
    udp_recomputed=receipt.build_endpoint_proof(expected,udp["queries"])
    assert not udp_recomputed["passed"]

    split=endpoint_fixture(expected)
    slices=json.loads(split["queries"]["endpointSlices"]["stdout"])
    original=slices["items"][0]
    slices["items"]=[{**original,"metadata":{**original["metadata"],"name":"port-only"},
                      "endpoints":[]},
                     {**original,"metadata":{**original["metadata"],"name":"address-only"},
                      "ports":[]}]
    endpoints=json.loads(split["queries"]["endpoints"]["stdout"])
    endpoints["items"][0]["subsets"]=[{"ports":[{"port":9555,"protocol":"TCP"}],
                                         "addresses":[]},
                                        {"ports":[],"addresses":[{"ip":"10.0.0.1"}]}]
    for query_name,document in (("endpointSlices",slices),("endpoints",endpoints)):
        payload=json.dumps(document)
        split["queries"][query_name]["stdout"]=payload
        split["queries"][query_name]["stdoutSha256"]=hashlib.sha256(payload.encode()).hexdigest()
    split_recomputed=receipt.build_endpoint_proof(expected,split["queries"])
    assert not split_recomputed["passed"]
    assert not split_recomputed["services"]["adservice"]["overlappingReadyAddresses"]


def test_fault_evidence_comes_only_from_scheduled_workload_rows():
    intervention={"scaledToZero":True,"scaledToZeroAtEpoch":20.0,"scaleOneAtEpoch":30.0,
                  "rolloutReadyAtEpoch":35.0,"commands":[{"returnCode":0},{"returnCode":0}],"error":None}
    workload={"requests":[
        {"startedAtEpoch":10.0,"endedAtEpoch":11.0,"error":None},
        {"startedAtEpoch":25.0,"endedAtEpoch":26.0,"error":"HTTP 500"},
        {"startedAtEpoch":36.0,"endedAtEpoch":37.0,"error":None},
    ]}
    bound=kind_smoke.bind_intervention_to_workload(intervention,workload)
    assert bound["successful"] is True
    assert bound["evidenceSource"]=="scheduled-measured-workload-only"
    workload["requests"][-1]["error"]="HTTP 500"
    assert kind_smoke.bind_intervention_to_workload(intervention,workload)["successful"] is False


def test_visibility_is_bounded_to_pre_fault_measured_window():
    goal=json.loads((ROOT/"modules/online-boutique/goals/homepage-path.json").read_text())
    def trace(trace_id,start):
        return [
            {"traceId":trace_id,"spanId":"01","parentSpanId":"","serviceName":"frontend","name":"GET","kind":"Server","startTimeUnixNano":start,
             "attributes":{"http.request.method":"GET","url.path":"/"}},
            {"traceId":trace_id,"spanId":"02","parentSpanId":"01","serviceName":"frontend","name":"hipstershop.ProductCatalogService/ListProducts","kind":"Client","startTimeUnixNano":start},
            {"traceId":trace_id,"spanId":"03","parentSpanId":"02","serviceName":"productcatalogservice","name":"hipstershop.ProductCatalogService/ListProducts","kind":"Server","startTimeUnixNano":start},
        ]
    spans=trace("aa",150)+trace("bb",250)
    observed=kind_smoke.goal_visibility(spans,goal,start_ns=100,end_ns=200)
    assert observed["verdict"]=="pass" and observed["directParentLinkedTraceIdsForRequiredEdge"]==["aa"]
    assert observed["completePathTraceCount"]==1 and observed["observedHomepageRootTraceCount"]==1
    assert kind_smoke.goal_visibility(spans,goal,start_ns=300,end_ns=400)["verdict"]=="blocked"

@pytest.mark.parametrize("posture",["selected","full"])
def test_live_and_final_visibility_use_identical_workload_derived_bounds(posture):
    goal=json.loads((ROOT/"modules/online-boutique/goals/homepage-path.json").read_text())
    spans=[
        {"traceId":"aa","spanId":"01","parentSpanId":"","serviceName":"frontend",
         "name":"GET","kind":"Server","startTimeUnixNano":20_000_000_000,
         "attributes":{"http.request.method":"GET","url.path":"/"}},
        {"traceId":"aa","spanId":"02","parentSpanId":"01","serviceName":"frontend",
         "name":"hipstershop.ProductCatalogService/ListProducts","kind":"Client",
         "startTimeUnixNano":20_000_000_000},
        {"traceId":"aa","spanId":"03","parentSpanId":"02",
         "serviceName":"productcatalogservice",
         "name":"hipstershop.ProductCatalogService/ListProducts","kind":"Server",
         "startTimeUnixNano":20_000_000_000},
    ]
    measurement={"source":"deterministic-bound-raw-workload-request-timestamps",
                 "executorStartNs":10_000_000_000,"startNs":12_000_000_000,
                 "endNs":60_000_000_000}
    intervention={"scaledToZeroAtEpoch":55.0}
    configuration={"faultAtSeconds":45,"visibilitySafetyMarginSeconds":5}
    live=kind_smoke.measured_goal_visibility(
        spans,goal,measurement,intervention,configuration)
    shifted_measurement={**measurement,"executorStartNs":10_050_000_000}
    final=kind_smoke.measured_goal_visibility(
        spans,goal,shifted_measurement,{"scaledToZeroAtEpoch":59.95},configuration)
    assert posture in {"selected","full"}
    assert live==final and live["measurementWindow"]=={
        "startNs":12_000_000_000,"endNs":52_000_000_000,"bounded":True}


def test_namespace_absence_requires_a_successful_authoritative_query(monkeypatch,tmp_path):
    class Result:
        def __init__(self,rc,stdout="",stderr=""): self.returncode=rc; self.stdout=stdout; self.stderr=stderr
    monkeypatch.setenv("OBSPLACEMENT_KUBECTL_CACHE_DIR",str(tmp_path/"cache"))
    monkeypatch.setattr(kind_smoke,"command",lambda argv,check=False:Result(1,stderr="connection refused"))
    assert kind_smoke.namespace_absence_proof("kind-owned","online-boutique")["namespaceAbsent"] is False
    monkeypatch.setattr(kind_smoke,"command",lambda argv,check=False:Result(0))
    assert kind_smoke.namespace_absence_proof("kind-owned","online-boutique")["namespaceAbsent"] is True


def test_cleanup_removes_only_owned_tags_volume_and_empty_new_kind_network(monkeypatch):
    tags=["obs/a:pin","obs/b:pin"]; images={*tags,kind_smoke.BUILDKIT_IMAGE}
    volumes={"owned-data","buildx_buildkit_owned-builder0_state"}; networks={"kind"}
    builders={"owned-builder"}; containers={"buildx_buildkit_owned-builder0"}
    calls=[]
    class Result:
        def __init__(self,rc=0,stdout="",stderr=""): self.returncode=rc; self.stdout=stdout; self.stderr=stderr
    def fake(argv,check=True,**kwargs):
        calls.append(argv)
        if argv[:3]==["docker","image","inspect"]:
            return Result(0,"[]") if argv[3] in images else Result(1,stderr="No such image")
        if argv[:3]==["docker","image","rm"]:
            images.discard(argv[3]); return Result()
        if argv[:3]==["docker","volume","ls"]: return Result(stdout="\n".join(sorted(volumes)))
        if argv[:3]==["docker","volume","rm"]: volumes.discard(argv[3]); return Result()
        if argv[:3]==["docker","volume","inspect"]:
            return Result(0,"[]") if argv[3] in volumes else Result(1,stderr="no such volume")
        if argv[:3]==["docker","network","ls"]: return Result(stdout="\n".join(sorted(networks)))
        if argv[:3]==["docker","network","inspect"]: return Result(stdout=json.dumps([{"Name":"kind","Containers":{}}]))
        if argv[:3]==["docker","network","rm"]: networks.discard(argv[3]); return Result()
        if argv[:3]==["docker","buildx","ls"]:
            rows=[{"Name":"default","Driver":"docker"},
                  *[{"Name":name,"Driver":"docker-container"} for name in sorted(builders)]]
            return Result(stdout="\n".join(json.dumps(row) for row in rows)+"\n")
        if argv[:3]==["docker","buildx","rm"]: builders.discard(argv[-1]); return Result()
        if argv[:3]==["docker","ps","-a"]: return Result(stdout="\n".join(sorted(containers)))
        if argv[:3]==["docker","rm","-f"]: containers.discard(argv[3]); return Result()
        raise AssertionError(argv)
    monkeypatch.setattr(kind_smoke,"command",fake)
    pre={"kindNetworkPresent":False,"ownedImageRefsPresent":{
        **{tag:False for tag in tags},kind_smoke.NODE_IMAGE:True,kind_smoke.BUILDKIT_IMAGE:False}}
    result=kind_smoke.cleanup_owned_host_state(tags,pre,"owned")
    assert result["passed"] and not images and not volumes and not networks and not builders and not containers
    assert [row[3] for row in calls if row[:3]==["docker","image","rm"]]==[*tags,kind_smoke.BUILDKIT_IMAGE]


def test_allocated_port_gate_detects_a_leaked_listener(monkeypatch):
    class Busy:
        def setsockopt(self,*args): pass
        def bind(self,address): raise OSError("address already in use")
        def close(self): pass
    monkeypatch.setattr(kind_smoke.socket,"socket",Busy)
    observed=kind_smoke.allocated_ports_free((18080,))
    assert not observed["passed"] and observed["blocked"][0]["port"]==18080


def test_early_validation_failure_still_removes_owned_client_state(monkeypatch,tmp_path):
    output=tmp_path/"fresh-output"
    for key in ("KUBECONFIG","KUBECACHEDIR","OBSPLACEMENT_KUBECTL_CACHE_DIR",
                "HELM_CONFIG_HOME","HELM_CACHE_HOME","HELM_DATA_HOME"):
        monkeypatch.setenv(key,os.environ.get(key,""))
    monkeypatch.setattr(kind_smoke,"verify_tool_receipt",
                        lambda path: (_ for _ in ()).throw(RuntimeError("tool drift")))
    exit_code=kind_smoke.main(["--output",str(output),"--schedule",str(tmp_path/"schedule.json"),
        "--source",str(tmp_path/"source"),"--app-source",str(tmp_path/"app"),
        "--tool-receipt",str(tmp_path/"tools.json"),"--cluster","owned-test"])
    assert exit_code==2
    assert not (output/"owned-kubeconfig").exists()
    assert not (output/"owned-helm-home").exists()
    assert not (output/"owned-kubectl-cache").exists()
    assert json.loads((output/"completion-validation.json").read_text())["passed"] is False


def test_final_receipt_set_rejects_irregular_extra_receipts(monkeypatch,tmp_path):
    scheduled={"block":1,"posture":"full"}
    schedule={"configuration":{"sharedContract":{}},"runs":[scheduled]}
    run=tmp_path/"b01-full"; run.mkdir(); (run/"receipt.json").write_text(
        json.dumps({"finalValidation":{"passed":True}}))
    monkeypatch.setattr(kind_smoke,"validate_completed_receipt",
                        lambda path,planned,schedule,source:{"finalValidation":{"passed":True}})
    monkeypatch.setattr(kind_smoke,"verify_shared_contract",lambda shared:{})
    assert kind_smoke.validate_evidence_set(tmp_path,schedule,tmp_path)["passed"]
    stale=tmp_path/"irregular-stale"; stale.mkdir(); (stale/"receipt.json").write_text("{}")
    observed=kind_smoke.validate_evidence_set(tmp_path,schedule,tmp_path)
    assert not observed["passed"]
    assert any("on-disk receipt set differs" in blocker for blocker in observed["blockers"])

def test_final_receipt_set_rehashes_shared_contract_at_both_boundaries(monkeypatch,tmp_path):
    scheduled={"block":1,"posture":"full"}
    schedule={"configuration":{"sharedContract":{}},"runs":[scheduled]}
    run=tmp_path/"b01-full"; run.mkdir()
    (run/"receipt.json").write_text(json.dumps({"finalValidation":{"passed":True}}))
    monkeypatch.setattr(kind_smoke,"validate_completed_receipt",
                        lambda path,planned,schedule,source:{"finalValidation":{"passed":True}})
    calls={"count":0}
    def boundary_verify(shared):
        calls["count"]+=1
        if calls["count"]==2:
            raise RuntimeError("goal bytes drifted during finalization")
        return {}
    monkeypatch.setattr(kind_smoke,"verify_shared_contract",boundary_verify)
    result=kind_smoke.validate_evidence_set(tmp_path,schedule,tmp_path)
    assert not result["passed"]
    assert any("end hash verification failed" in blocker for blocker in result["blockers"])


def test_exact_receipt_binding_rejects_changed_hash_teardown_and_workload(monkeypatch,tmp_path):
    evidence=tmp_path/"evidence"; run=evidence/"b01-full"; run.mkdir(parents=True)
    source=tmp_path/"source"; values=source/"helm-values"; values.mkdir(parents=True)
    (values/"tempo-values.yaml").write_text("tempo: pinned\n")
    shared={"goalRef":"modules/online-boutique/goals/homepage-path.json",
            "goalSha256":kind_smoke.sha256(ROOT/"modules/online-boutique/goals/homepage-path.json"),
            "activationRef":"modules/online-boutique/activation/catalog.json",
            "activationSha256":kind_smoke.sha256(ROOT/"modules/online-boutique/activation/catalog.json")}
    applied_payload="apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: frozen\n"
    (run/"applied.yaml").write_text(applied_payload)
    applied_sha=kind_smoke.sha256(run/"applied.yaml")
    configuration={"applicationUpstreamSha":receipt.APP_SHA,"acquisitionUpstreamSha":receipt.LGTM_SHA,
        "applicationMaterializedSha256":"a"*64,"sharedContract":shared,
        "generatedConfigSha256":{"application.yaml":"b"*64},"plannerSha256":"c"*64,
        "executorSha256":"d"*64,"chartSha256":{"tempo":"e"*64},
        "cluster":"owned-test",
        "kindNodeImage":"kind@sha256:"+"f"*64,"buildkitImage":kind_smoke.BUILDKIT_IMAGE,
        "measurementSeconds":3,"requestsPerSecond":1,
        "fault":"productcatalog-kubernetes-scale-zero","faultAtSeconds":45,
        "visibilitySafetyMarginSeconds":5,"outageSeconds":15,
        "concurrency":1,"kustomize":{"renders":{"full":{"sha256":applied_sha,
            "runtimeCompatibility":{"services":{"frontend-service":{"targetPort":8080}}}}}}}
    schedule={"configuration":configuration,"runs":[{"block":1,"posture":"full"}]}
    (evidence/"schedule.json").write_text(json.dumps(schedule))
    (evidence/"host-tools.json").write_text("{}")
    (evidence/"toolchain.json").write_text("{}")
    framework={"commit":"2"*40,"dirty":False,"bundleSha256":"3"*64}
    (evidence/"framework.json").write_text(json.dumps(framework))
    charts={"tempo":{"version":"pinned"}}; (evidence/"charts.json").write_text(json.dumps(charts))
    image_id="sha256:"+"4"*64; runtime="import@sha256:"+"5"*64
    images={name:{"tag":f"{kind_smoke.SOURCE_IMAGES[name]}:{configuration['applicationMaterializedSha256'][:16]}",
                  "imageID":image_id,"nodeImageID":image_id,"nodeRepoDigests":[runtime],
                  "sourceSha256Label":configuration["applicationMaterializedSha256"]}
            for name in ("frontend","productcatalogservice","currencyservice")}
    builder_name=kind_smoke.buildx_builder_name(configuration["cluster"])
    (evidence/"images.json").write_text(json.dumps({"buildCount":3,"images":images,"builder":{
        "name":builder_name,"driver":"docker-container","driverImage":kind_smoke.BUILDKIT_IMAGE,
        "inventory":{"Name":builder_name,"Driver":"docker-container"}}}))
    catalog=json.loads((ROOT/"modules/online-boutique/activation/catalog.json").read_text())
    services={}
    for name,control in {"frontend":"frontend","productcatalogservice":"productcatalog","currencyservice":"currency"}.items():
        expected=catalog["postures"]["full"][control]; image=images[name]
        services[name]={"enableTracing":expected,"expectedEnableTracing":expected,"declaredImage":image["tag"],
            "expectedDeclaredImage":image["tag"],"expectedLocalImageID":image_id,"nodeImageID":image_id,
            "expectedRuntimeImageIDs":[runtime],"runtimeImageIDRaw":runtime}
    rows=[{"startedAtEpoch":12,"endedAtEpoch":13,"error":None},
          {"startedAtEpoch":62,"endedAtEpoch":63,"error":"HTTP 500"},
          {"startedAtEpoch":76,"endedAtEpoch":77,"error":None}]
    teardown={"queryReturnCode":0,"queryStdout":"","queryStderr":"","namespaceAbsent":True}
    workload_document={"offered":3,"completed":2,"failed":1,"requests":rows,
                       "ratePerSecond":1,"durationSeconds":3,"concurrency":1}
    intervention_document={"scenario":"productcatalog-kubernetes-scale-zero",
        "scheduledAtSeconds":45,"scheduledScaleZeroSeconds":15,"startedAtEpoch":55,
        "scaledToZeroAtEpoch":60,"scaleOneAtEpoch":70,
        "rolloutReadyAtEpoch":75,"preFaultSuccessfulCount":1,"scaleZeroFailureCount":1,
        "postRecoverySuccessfulCount":1}
    (run/"workload.json").write_text(json.dumps(workload_document))
    (run/"intervention.json").write_text(json.dumps(intervention_document))
    (run/"teardown.json").write_text(json.dumps(teardown))
    endpoint_proof=endpoint_fixture()
    (run/"service-endpoints.json").write_text(json.dumps(endpoint_proof))
    document={"runId":"b01-full","block":1,"posture":"full","source":{
        "applicationUpstreamSha":receipt.APP_SHA,"acquisitionUpstreamSha":receipt.LGTM_SHA,
        "applicationMaterializedSha256":"a"*64,"frameworkCommit":framework["commit"],"frameworkDirty":False},
        "sharedContract":shared,"configSha256":configuration["generatedConfigSha256"],
        "configurationBinding":{"scheduleSha256":kind_smoke.sha256(evidence/"schedule.json"),
            "plannerSha256":configuration["plannerSha256"],"executorSha256":configuration["executorSha256"],
            "frameworkCommit":framework["commit"],"frameworkBundleSha256":framework["bundleSha256"],
            "helmValueSha256":{"tempo-values.yaml":kind_smoke.sha256(values/"tempo-values.yaml")},
                "chartArchiveSha256":configuration["chartSha256"],"kindNodeImage":configuration["kindNodeImage"],
                "buildkitImage":configuration["buildkitImage"],
            "hostToolProofSha256":kind_smoke.sha256(evidence/"host-tools.json")},
        "toolchainReceiptSha256":kind_smoke.sha256(evidence/"toolchain.json"),"charts":charts,
        "appliedKustomize":{"posture":"full","renderedSha256":"sha256:"+applied_sha},
        "postureProof":{"services":services},"serviceEndpoints":endpoint_proof,"teardown":teardown,
        "telemetry":{"tempoSpans":0,"tempoTraces":0,"tempoGlobalTraces":0,
                     "tempoGlobalSpans":0,"tempoTargetSourceSpans":0,
                     "tempoBackgroundTraces":0,"lokiRecords":0},
        "visibility":{"measurementWindow":{"startNs":12_000_000_000,
                                              "endNs":52_000_000_000,"bounded":True},
                      "verdict":"pass"},
        "workload":workload_document,"intervention":intervention_document,
        "technicalBlockers":[],"functionalVerdict":"pass"}
    monkeypatch.setattr(kind_smoke,"load",lambda name,path:type("Validator",(),{
        "blockers":staticmethod(lambda row:[]),
        "endpoint_proof_blockers":staticmethod(receipt.endpoint_proof_blockers),
        "intervention_counts":staticmethod(receipt.intervention_counts)})())
    monkeypatch.setattr(kind_smoke,"recompute_tempo_run",lambda run_dir,proof,configuration,workload:
                        ([],{}, {"startNs":12_000_000_000,"endNs":77_000_000_000,
                                 "executorStartNs":10_000_000_000,
                                 "source":"deterministic-bound-raw-workload-request-timestamps"}))
    monkeypatch.setattr(kind_smoke,"recompute_tempo_global_run",lambda run_dir,proof,configuration,workload,targets:
                        ({"returnedTraceCount":0,"normalizedSpanCount":0,
                          "targetedSourceSpanCount":0,"backgroundTraceCount":0},
                         {"startNs":12_000_000_000,
                                                   "executorStartNs":10_000_000_000,
                                                   "endNs":77_000_000_000,
                                                   "source":"deterministic-bound-raw-workload-request-timestamps"}))
    monkeypatch.setattr(kind_smoke,"recompute_loki_run",lambda run_dir,proof,configuration,workload:
                        ([],{}, {"startNs":12_000_000_000,"endNs":77_000_000_000,
                                 "executorStartNs":10_000_000_000,
                                 "source":"deterministic-bound-raw-workload-request-timestamps"}))
    monkeypatch.setattr(kind_smoke,"recompute_synthetic_exclusion",lambda *args:{})
    monkeypatch.setattr(kind_smoke,"goal_visibility",lambda spans,goal,**window:document["visibility"])
    path=run/"receipt.json"; path.write_text(json.dumps(document))
    planned={"block":1,"posture":"full"}
    validated=kind_smoke.finalize_completed_receipt(path,planned,schedule,source)
    assert validated["finalValidation"]["passed"],validated["finalValidation"]["blockers"]
    (evidence/"evidence-manifest.json").write_text(
        json.dumps({"schemaVersion":1,"files":[]},sort_keys=True)+"\n")
    sealed_paths=(path,evidence/"evidence-manifest.json")
    sealed_bytes={item:item.read_bytes() for item in sealed_paths}
    for _ in range(2):
        reread=kind_smoke.validate_evidence_set(evidence,schedule,source)
        assert reread["passed"],reread["blockers"]
        assert {item:item.read_bytes() for item in sealed_paths}==sealed_bytes
    document=json.loads(path.read_text()); document["configurationBinding"]["plannerSha256"]="tampered"
    path.write_text(json.dumps(document))
    changed=kind_smoke.validate_completed_receipt(path,planned,schedule,source)
    assert "receipt configuration binding differs from frozen artifacts" in changed["finalValidation"]["blockers"]
    document["configurationBinding"]["plannerSha256"]=configuration["plannerSha256"]
    document["workload"]["ratePerSecond"]=2; document["teardown"]["queryStdout"]="namespace/online-boutique"
    path.write_text(json.dumps(document))
    changed=kind_smoke.validate_completed_receipt(path,planned,schedule,source)
    assert "workload echoed configuration differs from schedule" in changed["finalValidation"]["blockers"]
    assert "receipt teardown is not an authoritative empty namespace query" in changed["finalValidation"]["blockers"]
    document["workload"]["ratePerSecond"]=1; document["teardown"]=teardown
    tampered=json.loads(json.dumps(endpoint_proof))
    tampered["queries"]["endpointSlices"]["returnCode"]=1
    tampered["services"]["frontend-service"]["endpointSlices"]={
        "count":0,"ports":[],"readyAddresses":[]}
    tampered["passed"]=True; tampered["blockers"]=[]
    document["serviceEndpoints"]=tampered
    (run/"service-endpoints.json").write_text(json.dumps(tampered))
    path.write_text(json.dumps(document))
    changed=kind_smoke.validate_completed_receipt(path,planned,schedule,source)
    assert any("endpoint proof fails semantic recomputation" in row
               for row in changed["finalValidation"]["blockers"])
