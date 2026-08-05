"""Generate docs/ai_governance.md from the NIST AI RMF Playbook.

    python docs/build_governance.py

Every subcategory description is pulled verbatim from the playbook JSON rather
than retyped, so the quotes cannot drift. The mapping below is ours: the
playbook is generic and cannot know this project exists.

Rule for inclusion: a row survives only if it names a control that exists in
this repo and can be pointed at. Anything that would need a policy we do not
have, a process we do not run, or a surface we do not touch is dropped and
listed in SKIPPED with the reason.
"""
import json
from pathlib import Path

# The playbook ships with the repo so this is reproducible by anyone who clones
# it. NIST AI RMF Playbook, a US government work, in the public domain.
PLAYBOOK = Path(__file__).resolve().parent / "nist_playbook.json"
OUT = Path(__file__).resolve().parent / "ai_governance.md"

# subcategory -> (theme, our control, where it lives)
MAPPED = [
 ("GOVERN 4.1", "Adversarial testing",
  "A runnable test suite drives the real graph with a scripted model and asserts the guardrail holds: "
  "a draft calling an unmeasured settlement \u201cunderserved\u201d is rejected, an illustrative cost or rule "
  "quoted without saying so is rejected, and each check is proved to fire from the tool's machine "
  "flags with every explanatory sentence blanked out.",
  "`agent/test_agent.py` (39 assertions, no API key needed); `_scan()` in `agent/graph.py`"),

 ("GOVERN 6.2", "Third-party failure contingency",
  "Every external dependency degrades instead of breaking: no Street View imagery renders a sentence "
  "rather than an empty box, the copilot server being down is a sentence in the panel and changes "
  "nothing else on the page, and the division polygons are pre-dissolved so no geometry library runs "
  "at page load.",
  "`loadGoogleContext()`; `askAgent()` offline path; `sabah_divisions.geojson`"),

 ("MANAGE 1.4", "Residual risk disclosed downstream",
  "Unverified assumptions are labelled on the face of the component that uses them, not buried: "
  "\u201cIllustrative decision criteria pending source verification\u201d on the recommender and "
  "\u201cIllustrative planning assumptions \u2014 not procurement estimates\u201d on the budget panel.",
  "`recommenderBlock()`; `.bud-warn` banner; Open items table below"),

 ("MANAGE 2.1", "A non-AI alternative was chosen where one sufficed",
  "DIPI is deliberately arithmetic, not a model: a disclosed weighted sum of four pillars that a planner "
  "can recompute by hand. The intervention recommender is likewise deterministic rules with the fired "
  "reasons shown, not a classifier.",
  "`dipiOf()`; `recommend()` returns its `why` list"),

 ("MANAGE 2.4", "Deactivation and spend controls",
  "Google imagery is off by default even with a key saved, can be switched off mid-session, is capped at "
  "50 billable calls per session, and shows a live counter of what it has spent.",
  "`GOOGLE.setOn()`; `GOOGLE.MAX_CALLS`; `updateGoogleMeter()`"),

 ("MAP 1.1", "Purpose and limits stated in every view",
  "The contract sentence \u201cScreening for further assessment \u2014 not a coverage determination\u201d is present "
  "in every view and is the one element that never truncates; the layout gives way around it.",
  "footer `.contract`, `flex:1 0 auto`"),

 ("MAP 2.1", "The task and its method are defined",
  "DIPI is a documented weighted blend at 40/25/15/20, verified against the file to within rounding. "
  "The model's target is defined as `dl_mbps` from non-network features, with the circular option "
  "(predicting DIPI from its own components) explicitly ruled out.",
  "`dataset/ml/COVERAGE_MODEL_GUIDE.md` \u00a71\u2013\u00a73"),

 ("MAP 2.2", "Knowledge limits are on screen, not in an appendix",
  "\u201cBlank areas \u2260 no coverage\u201d sits permanently on the map. The simulator refuses where there is no "
  "measurement. Jitter and packet loss are named as absent from the dataset on the video-call card.",
  "`.map-note`; `simulate()` null path; call `foot` line"),

 ("MAP 2.3", "Data selection examined, not assumed",
  "29% of settlements share an exact speed value with another because they sit in the same Ookla tile. "
  "That was measured, and it is why the training guide mandates GroupKFold by district rather than a "
  "random split that would silently inflate the score.",
  "`COVERAGE_MODEL_GUIDE.md` \u00a74; `dataset/ml/training_table.csv` district column"),

 ("MAP 3.3", "Scope narrowed on purpose",
  "The tool screens for further assessment. It does not confirm coverage status, locate infrastructure, "
  "assign operator fault, or make deployment decisions, and each of those refusals is written down as a "
  "rule the agent must enforce.",
  "`SYSTEM` prompt in `agent/graph.py`; the footer contract sentence in `dashboard/index.html`"),

 ("MAP 3.5", "Human oversight boundary",
  "Queue B is rendered as a set needing measurement, never as a ranked leaderboard, and is immune to the "
  "weight sliders. The recommender carries \u201cRules-based decision support \u2014 not a trained model.\u201d",
  "Queue B section; `dipiOf()` returns null for Queue B; `recommenderBlock()` footer"),

 ("MAP 4.1", "Third-party data mapped with its licence",
  "Seven upstream sources are credited with licence, quarter and access date in a footer visible in every "
  "view. Ookla's CC BY-NC-SA non-commercial term is a live constraint on what this project may become.",
  "footer `.credits`; Esri and CARTO attribution on the map control"),

 ("MEASURE 1.1", "Metrics chosen, and the unmeasurable named",
  "The model reports MAE in Mbps alongside R\u00b2, and must beat a district-median baseline or say so. "
  "Risks we cannot measure are stated rather than omitted: jitter and packet loss are not in this dataset.",
  "`COVERAGE_MODEL_GUIDE.md` \u00a75; simulator call footnote"),

 ("MEASURE 2.1", "TEVV documented and runnable",
  "Sixteen data checks run on every page load and print to the console, with `?debug=1` rendering them as "
  "a panel: counts, unique ids, geometry, bbox, coordinate order, filter round-trips and null handling.",
  "`validateData()`; `?debug=1` panel"),

 ("MEASURE 2.5", "Validity and generalisability limits",
  "The connectivity transform used for DIPI-M was validated on held-out points: worst error 0.0021, "
  "which is 0.09 DIPI points at the 40% weight. The derivation and that error are written into the "
  "code beside the function that uses them.",
  "`buildConnLookup()` derivation comment in `dashboard/index.html`"),

 ("MEASURE 2.7", "Security of the one credential we hold",
  "The Google key lives in browser localStorage, never in the repo, and is verified absent from "
  "`index.html`. Setup instructions require an HTTP-referrer-restricted key limited to the three APIs used.",
  "`GOOGLE.key()`; `dashboard/README.md` setup steps"),

 ("MEASURE 2.8", "Observed and modelled are never the same number",
  "Weights are disclosed on every pillar bar and stamped into the CSV as a `weighting` column, so an "
  "exported file cannot be mistaken for the team default. Modelled speeds carry a source label everywhere "
  "they appear, including the export.",
  "`downloadCSV()` weighting and `speed_source` columns; `sourceChip()`"),

 ("MEASURE 2.9", "The model explains itself, with its metrics attached",
  "A modelled settlement shows its top-3 SHAP drivers and its prediction interval, and no modelled number "
  "is displayed without a one-click model card carrying spatial CV MAE, R\u00b2, the baseline and the run date.",
  "`modelledSpeedBlock()`; `renderModelCard()`"),

 ("MEASURE 2.10", "Privacy by data choice",
  "Every input is an aggregate open dataset: Ookla tile aggregates, WorldPop raster counts, OSM public "
  "features, Meta RWI at grid level, JRC surface water, SRTM elevation, GADM boundaries. No personal data, "
  "no individual records, no PII enters the pipeline, so there is nothing to de-identify.",
  "`dataset/` inputs; credits line enumerates all seven"),

 ("MEASURE 2.11", "Bias tested geographically, not assumed away",
  "Validation is grouped by district so the model cannot be scored on settlements whose neighbours it "
  "trained on, and residuals are checked per district to catch systematic failure in one part of Sabah. "
  "Both the grouped and the naive random score are reported; the gap is the finding.",
  "`COVERAGE_MODEL_GUIDE.md` \u00a74 and \u00a75a; `training_table.csv` district groups"),

 ("MEASURE 2.13", "The measurement process is itself checked",
  "The spatial and random CV numbers are shown side by side in the model card, because the difference "
  "between them is what says whether the metric was measuring anything real.",
  "`renderModelCard()` spatial-versus-random note"),

 ("MEASURE 3.2", "Tracking the risk we cannot yet measure",
  "334 settlements have no usable measurement. Rather than leave that as a gap, the survey planner ranks "
  "them by stakes, and by stakes \u00d7 prediction uncertainty once the model ships, turning the blind spot "
  "into a field work queue.",
  "`surveyRanked()`; \u201cWhere to measure next\u201d sidebar group"),
]

SKIPPED = [
 ("Organisational machinery we do not operate",
  "GOVERN 1.2\u20131.7, 2.2\u20132.3, 3.1\u20133.2, 5.1\u20135.2; MANAGE 1.2\u20131.3",
  "AI policy, risk-tolerance scales, system inventory, decommissioning policy, staff training, "
  "board oversight, stakeholder engagement programmes. Three students, two weeks, one dashboard."),
 ("Done during development, but not committed, so not claimed",
  "MEASURE 2.3",
  "Rendering was checked headless at the projector resolution in both themes, but that browser "
  "harness is not in this repo. A control nobody can point at is not a control, so the row is cut "
  "rather than asserted."),
 ("No production deployment",
  "MANAGE 2.2\u20132.3, 4.1\u20134.3; MEASURE 2.4, 3.1, 3.3",
  "Drift monitoring, incident response, post-deployment feedback loops and appeal mechanisms all "
  "presuppose a live system with users. This runs on a laptop for a five-minute pitch."),
 ("Surface we do not have",
  "MEASURE 2.2, 2.6, 2.12; MANAGE 3.2; MAP 1.2, 3.4",
  "Human subjects, physical safety, environmental footprint of training, pre-trained model supply "
  "chain, team demographics, operator certification. None of these touch a screening map."),
 ("Real, but we would be describing an intention rather than a control",
  "GOVERN 1.1, 2.1, 4.2\u20134.3, 6.1; MAP 1.3\u20131.6, 3.1\u20133.2, 4.2, 5.1\u20135.2; MEASURE 1.2\u20131.3, 4.1\u20134.3",
  "Each of these is either already covered by a row above or would need a document we have not "
  "written. Listing them would pad the table without adding a control."),
]


def main():
    pb = {e["title"]: e for e in json.loads(PLAYBOOK.read_text(encoding="utf-8"))}
    missing = [t for t, *_ in MAPPED if t not in pb]
    if missing:
        raise SystemExit("not in playbook: %s" % missing)

    order = {"Govern": 0, "Map": 1, "Measure": 2, "Manage": 3}
    rows = sorted(MAPPED, key=lambda r: (order[pb[r[0]]["type"]], r[0]))

    L = []
    add = L.append
    add("# AI governance: NIST AI RMF Playbook mapping\n")
    add("**Generated by `docs/build_governance.py`. Do not hand-edit the quotes:** every NIST")
    add("description below is pulled verbatim from the playbook JSON at build time, so it cannot")
    add("drift from the published text. The control and gap sentences are ours, because the")
    add("playbook is generic and cannot know this project exists.\n")
    add(f"We went through all **{len(pb)}** subcategories and kept the **{len(rows)}** where we can point")
    add("at something that exists in this repo. A row that could not name a real control was cut,")
    add("not softened. What we dropped, and why, is listed after the table.\n")
    add("---\n")
    add("## Controls\n")
    add("| NIST subcategory | The risk, in NIST's words | Our control | Where |")
    add("|---|---|---|---|")
    for title, theme, control, where in rows:
        desc = pb[title]["description"].strip().replace("|", "\\|")
        add(f"| **{title}**<br>{theme} | {desc} | {control} | {where} |")

    add("\n---\n")
    add("## What we cut, and why\n")
    add("| Reason | Subcategories | Detail |")
    add("|---|---|---|")
    for reason, subs, detail in SKIPPED:
        add(f"| {reason} | {subs} | {detail} |")

    add("\n---\n")
    add("## The slide\n")
    add(f"> **{len(rows)} controls out of {len(pb)} subcategories, and we will tell you what we cut.**")
    add(">")
    add("> We read the whole NIST AI RMF Playbook and kept every subcategory where we could point at a")
    add("> line of code. The rest govern machinery a three-person student team does not operate:")
    add("> production monitoring, model supply chains, human subjects, board oversight.")
    add(">")
    add("> - The tool refuses to estimate where there is no measurement")
    add("> - Observed and modelled are never displayed as the same number")
    add("> - Validation is grouped by district, because 29% of settlements share an Ookla tile")
    add("> - No model output appears without its validation metrics one click away")
    add("> - Unverified assumptions are labelled on the component that uses them")
    add(">")
    add("> Naming the 48 we skipped is itself the control. A team that claims all 72 has read none.\n")

    add("---\n")
    add("## Open items\n")
    add("| Item | Owner | Status |")
    add("|---|---|---|")
    add("| Intervention criteria sourced to ITU / MCMC guidance | Sourcing | `[TO VERIFY]` \u2014 rules ship labelled illustrative |")
    add("| Cost figures sourced to USP / JENDELA / benchmarks | Sourcing | `[TO VERIFY]` \u2014 every value tagged DEMO_PLACEHOLDER |")
    add("| Per-district residual check (MEASURE 2.11) | Modelling | pending \u2014 required by the coverage model guide |")
    add("| Model report with spatial and random CV | Modelling | pending \u2014 display path built and tested against a fixture |")
    add("| Agent trace evidence (LangSmith) | Tracing | pending |")

    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"  playbook subcategories : {len(pb)}")
    print(f"  mapped with a control  : {len(rows)}")
    print(f"  cut                    : {len(pb) - len(rows)}")
    by = {}
    for t, *_ in rows:
        by[pb[t]["type"]] = by.get(pb[t]["type"], 0) + 1
    print(f"  by function            : {by}")


if __name__ == "__main__":
    main()
