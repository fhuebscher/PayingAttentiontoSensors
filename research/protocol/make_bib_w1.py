"""Regenerates LIT_SYSTEMATIC_SEARCH_W1.bib from the W1 working data (tmp/lit-w1/, gitignored).

Run from anywhere:  uv run --no-project python -I research/protocol/make_bib_w1.py [out.bib]
Revised 2026-10-09 after independent review: the three entries that were added to the .bib by hand
(gias2022samplehst, zhu2025unisage, grabher2025modeling) and the jacob->roberts key rename are now
produced here, HTML entities in names/titles are unescaped, and the output path is a parameter.
Inputs (in tmp/lit-w1/data/): bib_meta.json (OpenAlex + doi.org handle + Crossref/DataCite title check,
built by build_bib.py and add_meta.py), unique.json. Network is used only for the arXiv-only entries
(abs page fetched, title matched). Without the working data the script cannot run; the .bib is the record.
"""
import json, re, unicodedata, pathlib, sys, time, html, urllib.request

REPO = pathlib.Path(__file__).resolve().parents[2]
D = REPO / "tmp" / "lit-w1"
OUT = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "research" / "protocol" / "LIT_SYSTEMATIC_SEARCH_W1.bib"
meta = json.load(open(D / "data/bib_meta.json"))
u = {x["n"]: x for x in json.load(open(D / "data/unique.json"))}
readdirs = {p.name for p in (D / "pdf").iterdir() if (p / "paper.txt").exists() or (p / "README.md").exists()}

def ascii_(s): return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
def fix_name(a):  # OpenAlex sometimes returns "Last, First"
    a = html.unescape(a)
    return " ".join(reversed([p.strip() for p in a.split(",", 1)])) if "," in a else a
def lastname(a): return ascii_(a.split()[-1]).lower() if a else "anon"
STOP = {"a","an","the","of","on","for","and","in","to","with","via","toward","towards","using","from"}
def firstword(t):
    for w in re.findall(r"[A-Za-z]+", ascii_(t)):
        if w.lower() not in STOP: return w.lower()
    return "x"
def esc(s): return html.unescape(s).replace("&", "\\&").replace("%", "\\%").replace("_", "\\_").replace("#", "\\#")
entries = []; skipped = []; keys = set()
def add(key, typ, fields):
    k = key; i = 2
    while k in keys: k = key + chr(96 + i); i += 1
    keys.add(k); entries.append((k, typ, fields))
AX = lambda d: d and d.lower().startswith("10.48550/arxiv.")
SKIP = {"n817", "n676", "n785"}
# per-key status overrides; everything else: text layer present -> read, else abstract only
NOT_OPENED = {"n305": "abstract only; full text NOT read (SSRN returned HTTP 403); coded from the Crossref abstract",
              "n143": "abstract only; full text NOT read (SSRN returned HTTP 403)",
              "n356": "SSRN 2024 version of Wang et al. (TAAS 2026, n357); not opened (HTTP 403)",
              "Grabher": "abstract only; full text NOT read; surfaced by full-text probe F2 (D7)"}
for key, r in meta.items():
    if key in SKIP: skipped.append((key, r.get("title"), "E3 thesis/dissertation chapter, not counted")); continue
    n = int(key[1:]) if re.fullmatch(r"n\d+", key) else None
    if not r.get("verify", "").startswith("resolves"):
        skipped.append((key, r.get("title") or (u[n]["title"] if n else key), r.get("verify"))); continue
    authors = [fix_name(a) for a in (r.get("authors") or [])]
    if key in NOT_OPENED: status = NOT_OPENED[key]
    elif key == "Roberts": status = "full text read (text layer, arXiv PDF)"
    else: status = "full text read (text layer)" if str(n) in readdirs else "abstract only; full text NOT read"
    doi = r["doi"]; venue = r.get("venue") or ""
    f = {"author": " and ".join(esc(a) for a in authors) if authors else "{Unknown}", "title": "{" + esc(r["title"]) + "}", "year": str(r["year"]), "doi": doi}
    if AX(doi) or "zenodo" in doi.lower() or "preprints" in doi.lower() or "techrxiv" in doi.lower() or "ssrn" in doi.lower() or "rs.3.rs" in doi.lower():
        typ = "misc"; f["howpublished"] = esc(venue or ("arXiv" if AX(doi) else "preprint/repository"))
        if AX(doi): f["eprint"] = doi.split("rxiv.", 1)[-1] if "rxiv." in doi else ""; f["archivePrefix"] = "arXiv"
    elif re.search(r"conference|symposium|proceedings|workshop|IEEE|ACM|ICDCS|NOMS|SoCC|Joint European|AAAI|CLOUD", venue, re.I) and not re.search(r"transactions|journal", venue, re.I):
        typ = "inproceedings"; f["booktitle"] = esc(venue)
    else:
        typ = "article"; f["journal"] = esc(venue)
    f["note"] = "W1 status: " + status
    if doi.lower() == "10.5281/zenodo.20561280": f["author"] = "{mhmdevan (GitHub handle; real name not given on the page read)}"; f["url"] = "https://github.com/mhmdevan/TraceForge"
    add(f"{lastname(authors[0]) if authors else 'anon'}{r['year']}{firstword(r['title'])}", typ, f)

# arXiv-only entries (no DOI in the records): verify via the arXiv abs page. (record number or None, arXiv id, note)
ARXIV = [(475, None, "arXiv abs page fetched and title matched"), (591, None, "arXiv abs page fetched and title matched"),
         (None, "2509.26336", "arXiv abs page fetched; found via web search S3"), (None, "2210.04595", "arXiv abs page fetched; found via web search S3")]
for n, aid, note in ARXIV:
    if aid is None: aid = re.sub(r"v\d+$", "", u[n]["arxiv"].split("/abs/")[-1])
    page = urllib.request.urlopen(urllib.request.Request(f"https://arxiv.org/abs/{aid}", headers={"User-Agent": "Mozilla/5.0 (w1-lit-search mailto:fhuebscher@users.noreply.github.com)"}), timeout=60).read().decode("utf-8", "ignore")
    t = " ".join(html.unescape(re.search(r'name="citation_title" content="([^"]+)"', page).group(1)).split())
    au = [fix_name(x) for x in re.findall(r'name="citation_author" content="([^"]+)"', page)]
    yr = re.search(r'name="citation_date" content="(\d{4})', page).group(1)
    if n is not None: assert t.lower()[:30] == u[n]["title"].lower()[:30], (t, u[n]["title"])
    add(f"{lastname(au[0])}{yr}{firstword(t)}", "misc", {"author": " and ".join(esc(a) for a in au), "title": "{" + esc(t) + "}", "year": yr, "eprint": aid, "archivePrefix": "arXiv", "howpublished": "arXiv preprint", "note": "W1 status: full text read (text layer, arXiv PDF); " + note})
    time.sleep(3)
out = ["% W1 systematic search (2026-10-09, revised 2026-10-09 after independent review). GENERATED by research/protocol/make_bib_w1.py; do not hand-edit. Only entries whose DOI resolves (doi.org handle API, responseCode 1) with a registry title match (Crossref/DataCite), or whose arXiv record was fetched.",
       "% Entries already in LIT_HARDENING_20261003.bib are NOT repeated here (e.g. AIOpsLab, ITBench, Saha 2026, Srinivas 2024, Borges 2024). Not verified/omitted: see LIT_SYSTEMATIC_SEARCH_W1.md section 6.", ""]
for k, typ, f in sorted(entries):
    out.append(f"@{typ}{{{k},")
    out += [f"  {a} = {{{b}}}," if a != "title" else f"  {a} = {b}," for a, b in f.items()]
    out.append("}\n")
OUT.write_text("\n".join(out))
print(len(entries), "entries written to", OUT, "; skipped:", [(k, why) for k, _, why in skipped])
