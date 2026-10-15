import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
QUEST = ROOT / "learning" / "observability-placement-quest"


class AssetParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.assets = []
        self.ids = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if "id" in values:
            self.ids.add(values["id"])
        if tag == "script" and values.get("src"):
            self.assets.append(values["src"])
        if tag == "link" and values.get("href"):
            self.assets.append(values["href"])


def load_questions():
    return json.loads((QUEST / "questions.json").read_text())["questions"]


def load_next_phase_path():
    return json.loads((QUEST / "next-paper-phases.json").read_text())


def run_mastery_node(source):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required to execute the quiz mastery engine")
    program = (
        f"const m=require({json.dumps(str(QUEST / 'mastery.js'))});"
        + source
    )
    return json.loads(subprocess.check_output(
        [node, "-e", program], text=True, cwd=ROOT,
    ))


def test_question_bank_is_deterministic_and_evidence_grounded():
    questions = load_questions()
    assert len(questions) == 125
    assert [q["id"] for q in questions] == [f"q{i:03d}" for i in range(1, 126)]
    visible = set(subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT, text=True).splitlines())
    for question in questions:
        assert set(question) == {
            "id", "category", "difficulty", "prompt", "choices", "answer",
            "explanation", "sourceRef",
        }
        assert question["category"] in {
            "Foundations", "Evidence", "Modules", "Lifecycle",
            "Optimization", "Retrospective", "Migration", "Next Phase",
            "Science Practice", "Math and Theory", "Practitioner Bridge",
            "AI in the Loop",
        }
        assert question["difficulty"] in {"beginner", "intermediate", "advanced"}
        assert len(question["choices"]) == 4
        assert len(set(question["choices"])) == 4
        assert type(question["answer"]) is int and 0 <= question["answer"] < 4
        assert len(question["prompt"]) >= 20 and len(question["explanation"]) >= 40
        source = question["sourceRef"].split("#", 1)[0]
        assert source in visible, question["id"]
        assert (ROOT / source).is_file()
        assert not source.startswith((".local/", "upstream/"))


def test_corrected_evidence_ceilings_are_explicit():
    by_id = {q["id"]: q for q in load_questions()}
    inventory = json.loads((ROOT / "research" / "evidence-inventory.json").read_text())
    ml = json.loads((ROOT / "research" / "ml-readiness.json").read_text())
    current = inventory["summary"]
    assert by_id["q013"]["choices"][by_id["q013"]["answer"]] == str(current["campaigns"])
    qualification = current["curatedScientificQualification"]
    assert by_id["q014"]["choices"][by_id["q014"]["answer"]] == (
        f'{qualification["candidate-evidence"]} candidate, '
        f'{qualification["smoke-validation"]} smoke, '
        f'{qualification["unlisted-evidence"]} unlisted'
    )
    assert by_id["q029"]["choices"][by_id["q029"]["answer"]] == "Smoke validation"
    assert by_id["q030"]["choices"][by_id["q030"]["answer"]] == "Smoke validation"
    assert by_id["q032"]["choices"][by_id["q032"]["answer"]] == "Smoke"
    assert "desk-only" not in by_id["q028"]["explanation"]
    assert "kind lifecycle executor" in by_id["q033"]["choices"][by_id["q033"]["answer"]]
    assert "Serialized traces.json artifact size" == by_id["q016"]["choices"][by_id["q016"]["answer"]]
    assert "Null for all observed SUTs" == by_id["q048"]["choices"][by_id["q048"]["answer"]]
    assert f'{ml["summary"]["rows"]} total, 30 eligible' == by_id["q044"]["choices"][by_id["q044"]["answer"]]


def test_context_tour_is_complete_and_ordered():
    retrospective = [q for q in load_questions() if q["category"] == "Retrospective"]
    migration = [q for q in load_questions() if q["category"] == "Migration"]
    assert [q["id"] for q in retrospective] == [f"q{i:03d}" for i in range(56, 68)]
    assert [q["id"] for q in migration] == [f"q{i:03d}" for i in range(68, 86)]
    assert {q["difficulty"] for q in retrospective} == {
        "beginner", "intermediate", "advanced",
    }
    assert {q["difficulty"] for q in migration} == {
        "beginner", "intermediate", "advanced",
    }


def test_next_paper_phase_is_ordered_and_has_exit_artifacts():
    questions = {q["id"]: q for q in load_questions()}
    path = load_next_phase_path()
    assert path["schemaVersion"] == 2
    assert path["snapshot"] == "2026-08-17"
    assert path["authority"] == "research/NEXT_PHASE_EXPERIMENT_PLAN_20260816.md"
    assert len(path["transferPrompt"]) >= 120
    assert "Solution architect" in path["audience"]
    assert "Goal-conditioned, control-valid" in path["northStar"]
    assert "orientation only" in path["readinessPolicy"]
    assert (ROOT / path["authority"]).is_file()
    assert len(path["primaryReading"]) == 5
    assert all(item["externalUrl"].startswith("https://") for item in path["primaryReading"])
    assert len(path["sections"]) == 8
    ids = []
    for section in path["sections"]:
        assert set(section) == {
            "id", "title", "intent", "workAnalogy", "mathCheckpoint",
            "humanLoopCheck", "deliverable", "exitCriterion", "questionIds",
        }
        assert all(len(section[key]) >= 20 for key in (
            "intent", "workAnalogy", "mathCheckpoint", "humanLoopCheck",
            "deliverable", "exitCriterion",
        ))
        assert section["questionIds"]
        ids.extend(section["questionIds"])
    assert ids == [
        "q086", "q087", "q093", "q104",
        "q105", "q108", "q109", "q110", "q111",
        "q088", "q089", "q090", "q091", "q092", "q112", "q113",
        "q114", "q115", "q116",
        "q094", "q106", "q107", "q118",
        "q095", "q096", "q097", "q098", "q117", "q119",
        "q099", "q100", "q120", "q121",
        "q101", "q102", "q103", "q125",
        "q122", "q123", "q124",
    ]
    assert len(ids) == len(set(ids))
    assert all(question_id in questions for question_id in ids)
    assert {questions[question_id]["difficulty"] for question_id in ids} == {
        "beginner", "intermediate", "advanced",
    }
    positions = [questions[question_id]["answer"] for question_id in ids]
    for period in range(1, 7):
        assert any(
            positions[index] != positions[index % period]
            for index in range(period, len(positions))
        )


def test_next_phase_questions_preserve_methodological_boundaries():
    by_id = {q["id"]: q for q in load_questions()}
    answer = lambda question_id: by_id[question_id]["choices"][by_id[question_id]["answer"]]
    assert answer("q086") == "Five execution modules across four application families"
    assert "P0b exposed the invalid whole-carrier quiescence assumption" in answer("q093")
    assert "P0c passed a bounded claim projection" in answer("q093")
    assert "real causal overhead and interference" in by_id["q093"]["explanation"]
    assert answer("q095").startswith("Explore feasible configurations, freeze candidates")
    assert "equal physical-evaluation budgets" in answer("q098")
    assert answer("q099").startswith("The frozen set of catalog-admissible")
    assert "after isolation or calibration" in answer("q102")
    assert "one none-selected-full smoke" in answer("q104")
    assert answer("q105").startswith(
        "A bounded TeaStore-independent logical objective"
    )
    assert "broader legacy cases and CLIs remain open" in answer("q076")
    assert "c31fd12" in by_id["q075"]["explanation"]
    assert "dependency-closed" in answer("q107")
    assert "marginal gain increases" in by_id["q110"]["explanation"]
    assert answer("q117").startswith("Equal physical-evaluation budgets")
    assert "Operational goals" in answer("q124")
    assert answer("q125").startswith("Goal-conditioned, control-valid")
    assert by_id["q090"]["sourceRef"] == (
        "research/NEXT_PHASE_EXPERIMENT_PLAN_20260816.md#2-vocabulary-for-the-next-paper"
    )
    assert by_id["q091"]["sourceRef"] == by_id["q090"]["sourceRef"]


def test_next_phase_plan_keeps_observation_and_theory_boundaries_explicit():
    plan = (ROOT / "research" / "NEXT_PHASE_EXPERIMENT_PLAN_20260816.md").read_text()
    normalized = " ".join(plan.split())
    assert "five execution modules spanning four independent application families" in normalized
    assert "diagnostic quarantine, not a replacement" in plan
    assert "ob-compose-p0b-20260817" in plan
    assert "ob-compose-p0c-20260817" in plan
    assert "Multi-block trace-volume or cost inference is a hard no-go" in normalized
    assert "Logical evidence item" in plan
    assert "Probe design" in plan
    assert "Structural activation assignment" in plan
    assert "Realized sensor instance" in plan
    assert all(f"### Stage {stage}" in plan for stage in range(6))
    assert all(f"`K{policy}`" in plan for policy in range(5))
    assert "A plateau is not a convergence proof" in plan
    assert "freeze the `K0`–`K4` selector implementations" in normalized
    assert "Do not redesign a selector after inspecting the Stage 3 archive" in normalized
    assert "requires an explicit reduction" in normalized
    assert "do not inherit that guarantee automatically" in normalized
    assert "Energy is a separate objective only after attribution" in normalized


def test_answer_key_does_not_expose_a_single_trivial_pattern():
    questions = load_questions()
    positions = [sum(question["answer"] == index for question in questions) for index in range(4)]
    assert min(positions) >= 6
    longest = sum(
        len(question["choices"][question["answer"]])
        == max(map(len, question["choices"]))
        for question in questions
    )
    assert longest / len(questions) < 0.7
    science_positions = [question["answer"] for question in questions[-22:]]
    counts = [science_positions.count(index) for index in range(4)]
    assert max(counts) - min(counts) <= 1
    assert not any(
        all(
            science_positions[index] == science_positions[index % period]
            for index in range(period, len(science_positions))
        )
        for period in range(1, 7)
    )


def test_static_app_is_local_complete_and_has_learning_controls():
    parser = AssetParser()
    html = (QUEST / "index.html").read_text()
    parser.feed(html)
    assert set(parser.assets) == {
        "app.js", "mastery.js", "styles.css", "enhancements.css",
    }
    assert all((QUEST / asset).is_file() for asset in parser.assets)
    required_ids = {
        "category", "difficulty", "session-length", "shuffle-questions",
        "shuffle-options", "score", "progress", "streak", "feedback",
        "review", "restart", "resume", "fatal", "orientation",
        "context-tour", "next-phase-tour", "phase-gate", "phase-gate-title",
        "phase-gate-deliverable", "phase-gate-exit", "phase-summary",
        "phase-gate-analogy", "phase-gate-math", "phase-gate-human",
        "phase-summary-list", "transfer-prompt", "bridge-title",
        "mastery-summary", "selection-reason", "question-mastery",
        "question-visual", "visual-caption", "visual-lanes", "visual-note",
        "command-drill", "drill-title", "drill-instruction", "drill-command",
        "copy-command", "summary-mastery",
        "mastery-review",
    }
    assert required_ids <= parser.ids
    js = (QUEST / "app.js").read_text()
    assert 'fetch("questions.json")' in js
    assert 'fetch("next-paper-phases.json")' in js
    assert "localStorage" in js and "state.missed" in js
    assert "Mastery.weightedOrder(pool, mastery)" in js
    assert "Mastery.applyAttempt" in js
    assert "syncMasteryAttempts()" in js
    assert "Mastery.applyCompletedSession" in js
    assert "Mastery priority is mixed with random variety" in js
    assert "function masteryReview()" in js
    assert "Weak, developing, and unseen questions precede maintenance samples" in js
    assert "Explicit review: missed" in js
    assert 'const MASTERY_KEY = "observability-placement-quest-mastery-v1"' in js
    assert 'question.category === "Migration" || question.category === "Retrospective"' in js
    assert "function nextPhaseTour()" in js
    assert 'source.href = `../../${question.sourceRef}`' in js
    assert 'const SESSION_KEY = "observability-placement-quest-v4-20260817"' in js
    assert "observability-placement-quest-v3" not in js
    assert "render(true)" in js and "state.selectedOriginal" in js
    assert '$("streak").hidden = state.mode === "next-phase"' in js
    assert "paperPath.transferPrompt" in js
    assert "This score is orientation only." in js
    assert "event.key" not in js or "keydown" in js
    styles = (QUEST / "styles.css").read_text() + (QUEST / "enhancements.css").read_text()
    assert not re.search(r"https?://", html + js + styles)
    assert not any((QUEST / name).exists() for name in ("package.json", "node_modules", "vite.config.js"))
    if node := shutil.which("node"):
        subprocess.run([node, "--check", str(QUEST / "app.js")], check=True, capture_output=True, text=True)
        subprocess.run([node, "--check", str(QUEST / "mastery.js")], check=True, capture_output=True, text=True)


def test_mastery_attempts_are_incremental_idempotent_and_session_completion_is_separate():
    report = run_mastery_node("""
let p=m.emptyProfile();
p=m.applyAttempt(p,"s1:0:q001",{questionId:"q001",correct:false},"2026-08-17T01:00:00Z");
const afterMiss=JSON.parse(JSON.stringify(p));
p=m.applyAttempt(p,"s1:0:q001",{questionId:"q001",correct:true},"2026-08-17T01:01:00Z");
const afterReplay=JSON.parse(JSON.stringify(p));
p=m.completeSession(p,"s1");
p=m.completeSession(p,"s1");
console.log(JSON.stringify({afterMiss,afterReplay,completed:p}));
""")
    if report is None:
        return
    miss = report["afterMiss"]
    assert miss["completedSessions"] == 0
    assert miss["questions"]["q001"] == {
        "attempts": 1,
        "correct": 0,
        "misses": 1,
        "lastResult": "missed",
        "lastAttemptAt": "2026-08-17T01:00:00Z",
        "lastCorrectAt": None,
    }
    assert report["afterReplay"] == miss
    assert report["completed"]["completedSessions"] == 1


def test_mastery_counts_stale_parallel_attempt_without_replacing_latest_result():
    report = run_mastery_node("""
let p=m.emptyProfile();
p=m.applyAttempt(p,"newer",{questionId:"q001",correct:true},"2026-08-17T02:00:00Z");
p=m.applyAttempt(p,"older",{questionId:"q001",correct:false},"2026-08-17T01:00:00Z");
console.log(JSON.stringify(p.questions.q001));
""")
    assert report == {
        "attempts": 2,
        "correct": 1,
        "misses": 1,
        "lastResult": "correct",
        "lastAttemptAt": "2026-08-17T02:00:00Z",
        "lastCorrectAt": "2026-08-17T02:00:00Z",
    }


def test_mastery_shuffle_prioritizes_weak_questions_but_keeps_random_variety():
    report = run_mastery_node("""
let p=m.emptyProfile();
p=m.applyAttempt(p,"a1",{questionId:"q001",correct:false},"2026-08-17T01:00:00Z");
p=m.applyAttempt(p,"a2",{questionId:"q003",correct:true},"2026-08-17T01:00:00Z");
p=m.applyAttempt(p,"a3",{questionId:"q003",correct:true},"2026-08-17T01:01:00Z");
function fixed(values){let i=0;return()=>values[i++];}
const items=[{id:"q001"},{id:"q002"},{id:"q003"}];
console.log(JSON.stringify({
  weights:items.map(q=>m.selectionWeight(m.entryFor(p,q.id))),
  first:m.weightedOrder(items,p,fixed([.99,.3,.1])).map(q=>q.id),
  second:m.weightedOrder(items,p,fixed([.01,.99,.2])).map(q=>q.id),
  summary:m.profileSummary(p,items.map(q=>q.id)),
  reasons:items.map(q=>m.selectionReason(m.entryFor(p,q.id)))
}));
""")
    if report is None:
        return
    missed, unseen, mastered = report["weights"]
    assert missed > unseen > mastered
    assert report["first"][0] == "q001"
    assert report["second"][0] == "q002"
    assert report["first"] != report["second"]
    assert report["summary"] == {
        "completedSessions": 0,
        "attempts": 3,
        "unseen": 1,
        "weak": 1,
        "developing": 0,
        "mastered": 1,
    }
    assert report["reasons"][0].startswith("Priority review: missed last time")
    assert report["reasons"][1].startswith("New question")


def test_app_persists_each_attempt_before_feedback_and_resyncs_on_resume():
    js = (QUEST / "app.js").read_text()
    answer_body = js[js.index("function answer(button)"):js.index("function next()")]
    assert answer_body.index("state.results.push") < answer_body.index("saveSession()")
    assert answer_body.index("saveSession()") < answer_body.index("syncMasteryAttempts()")
    assert answer_body.index("syncMasteryAttempts()") < answer_body.index("presentAnswer")
    resume_body = js[js.index('$("resume").onclick'):js.index('$("next").onclick')]
    assert "hydrateState" in resume_body and "syncMasteryAttempts()" in resume_body
    restart_body = js[js.index("function restart()"):js.index("function reviewMissed()")]
    assert "SESSION_KEY" in restart_body
    assert "MASTERY_KEY" not in restart_body
    review_body = js[js.index("function reviewMissed()"):js.index("async function boot()")]
    assert "new Set(state.missed)" in review_body
    assert 'begin(deck, "review")' in review_body
    key_body = js[js.index('document.addEventListener("keydown"'):]
    assert "event.target.closest" in key_body
    assert "interactive) return" in key_body


def test_science_visuals_and_command_drills_are_bounded_and_copy_only():
    js = (QUEST / "app.js").read_text()
    visual_ids = set(re.findall(r"^  (q\d{3}): \{\n    caption:", js, re.MULTILINE))
    assert visual_ids == {
        "q068",
        "q093", "q094", "q098", "q107", "q108",
        "q109", "q110", "q113", "q118", "q123",
    }
    assert "renderVisual(question)" in js
    assert "document.createElement" in js
    assert "innerHTML" not in js
    assert 'document.createElement("ol")' in js
    assert 'document.createElement("li")' in js
    assert "navigator.clipboard.writeText" in js
    assert "The browser never executes repository commands" in (QUEST / "index.html").read_text()
    assert "git rev-parse --show-toplevel && git branch --show-current" in js
    assert "git submodule status upstream/teastore" in js
    assert "uv run python tools/five_module_readiness.py" in js
    assert ".highestScientificQualification" in js
    assert "uv run pytest -q tests/test_configuration_oracle.py" in js
    assert "tests/test_phase1_control_universe.py tests/test_control_universe.py" in js
    assert not re.search(r"child_process|\bexec\(|\bspawn\(", js)


def test_repository_guide_contains_review_and_mermaid_flows():
    guide = (QUEST / "REPOSITORY_GUIDE.md").read_text()
    assert guide.count("```mermaid") == 10
    assert "## Migration status, not just architecture" in guide
    assert "## Methodology timeline" in guide
    assert "## How the work branched" in guide
    assert "## Evaluation ladder" in guide
    assert "## Operational readiness and scientific qualification" in guide
    assert "## What could have been better" in guide
    assert "## What remains outstanding" in guide
    assert "## Next-phase sensor model" in guide
    assert "## Offline enrichment without target leakage" in guide
    assert "## North-star contribution and immediate order" in guide
    assert "## Practitioner-to-researcher bridge" in guide
    assert "## Mathematical bridge: from deployment closure to regime maps" in guide
    assert "## Staying in the loop with AI" in guide
    assert "## Primary reading ladder" in guide
    assert "\\Delta_f(e\\mid A)\\geq\\Delta_f(e\\mid B)" in guide
    assert "positive value witnesses a diminishing-returns violation" in guide
    assert "oracle returns `Omega`" in guide
    assert "## Re-entry path and exit artifacts" in guide
    assert "Commit `c31fd12` added a bounded pure" in guide
    assert "The next code task is the open" not in guide


def test_migration_audit_is_explicit_about_verified_and_open_work():
    audit = (ROOT / "research" / "TEASTORE_MIGRATION_AND_SHIFT_AUDIT_20260812.md").read_text()
    assert "selective rewrite, not a complete" in audit
    assert "## Port matrix" in audit
    assert "## Methodology shift timeline" in audit
    assert "## Open completeness gates" in audit
    assert "Pure logical objectives and solver behavior" in audit
    assert "Ansible provision/deploy/sync playbooks" in audit
