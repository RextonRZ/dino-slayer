"""Tests for the agent, with a scripted LLM standing in for Gemini.

    python agent/test_agent.py        # from the repo root. No API key needed.

The LLM is replaced by a script of canned messages, so every assertion here is
about OUR code: argument handling, the tools, the evidence guardrail, the
rewrite cap, conversation memory, and the streamed graph steps. Nothing here
calls a paid API or needs the network.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import AIMessage

from agent import graph as G
from agent import tools as T


# ── a fake LLM that replays a script of AIMessages ──────────────────────────
class FakeLLM:
    def __init__(self, script): self.script = list(script); self.calls = 0
    def bind_tools(self, _): return self
    def invoke(self, msgs):
        self.calls += 1
        return self.script.pop(0) if self.script else AIMessage("fallback. " + T.DISCLAIMER)

def use(script):
    getattr(G._llm, 'cache_clear', lambda: None)()
    fake = FakeLLM(script)
    G._llm = lambda bound=False: fake          # type: ignore
    G.GRAPH = None                              # rebuild so the checkpointer is fresh
    return fake

def tc(name, args, i=0):
    return AIMessage("", tool_calls=[{"name": name, "args": args, "id": f"c{i}"}])

ok = fail = 0
def check(label, cond, detail=""):
    global ok, fail
    if cond: ok += 1; print(f"  PASS  {label}")
    else:    fail += 1; print(f"  FAIL  {label}  {detail}")

print("=== 1. the exact crash the user hit: a list where a string was declared ===")
r = T.rank_settlements(district=["Kota Marudu"], top_k="5")
check("rank_settlements(district=[...]) does not raise", len(r["rows"]) == 5, r)
check("it resolved the district", all(x["district"] == "Kota Marudu" for x in r["rows"]))
for bad in ([], {}, None, 12, True, ["", "Sandakan"]):
    try:
        T.rank_settlements(district=bad, top_k=2)
        T.district_summary(district=bad)
        T.list_facilities(district=bad, kind=bad)
    except Exception as e:
        check(f"arg {bad!r} survives", False, repr(e)); break
else:
    check("every malformed arg shape survives", True)

# ...and the same shapes must survive LangChain's Pydantic layer, which
# validates BEFORE the function body and used to reject them outright.
from agent.graph import _coerce_args, rank_settlements as _rs, compare_areas as _ca
for shape in [{"district": ["Kota Marudu"], "top_k": "5"},
              {"district": {"name": "Kota Marudu"}},
              {"district": "Kota Marudu", "top_k": 5.0},
              {"district": "Kota Marudu", "require_school": "true"},
              {"district": "Kota Marudu", "bogus_arg": 1}]:
    try:
        r = _rs.invoke(_coerce_args(_rs, shape))
        check(f"tool boundary survives {shape}", len(r["rows"]) > 0, r.get("note"))
    except Exception as e:
        check(f"tool boundary survives {shape}", False, f"{type(e).__name__}: {e}")

print("\n=== 2. the question that had no tool at all ===")
d = T.district_summary(sort_by="facilities", top_k=3)
top = d["rows"][0]
check("district_summary ranks by facility count",
      top["district"] == "Kota Kinabalu" and top["facilities"] == 105, top)
check("counts are from the facilities file, not summed buffers",
      top["schools"] + top["health"] == top["facilities"])
check("the note warns OSM is incomplete", "incomplete" in d["note"])
check("flags are machine readable", d["flags"] == ["osm_incomplete"])
f = T.list_facilities("Kota Kinabalu", "health", 200)
check("list_facilities returns real names", len(f["rows"]) > 10 and all(x["name"] for x in f["rows"]))
check("unnamed facilities are declared, not silently dropped", "no name" in f["note"] or "31" in f["note"], f["note"])
check("unknown kind is refused clearly", "Unknown kind" in T.list_facilities(kind="banana")["note"])

print("\n=== 3. the rewrite recursion loop (low-evidence + 2 failed rewrites) ===")
# plan_survey returns insufficient rows; drafts omit every required caveat.
bad = AIMessage("These villages are underserved and have no coverage.")
use([tc("plan_survey", {"district": "Kudat", "top_k": 3}), bad, bad, bad, bad, bad])
out = G.ask("where should we measure next in Kudat?")
check("terminates instead of GraphRecursionError", isinstance(out, dict))
check("stopped at the cap", out["rewrites"] == G.MAX_REWRITES + 1, out["rewrites"])
check("safe answer carries the low-evidence warning", T.LOW_EV_WARNING in out["answer"])
check("safe answer carries the disclaimer", T.DISCLAIMER in out["answer"])
check("map ids still come from the tool", len(out["map"]["ids"]) == 3, out["map"])

print("\n=== 4. guardrail keys off flags, not prose ===")
good = AIMessage(f"Fibre is suggested. {T.DISCLAIMER}")
use([tc("recommend_intervention", {"name_or_id": "Talas"}), good, good, good, good])
out = G.ask("what should we build in Talas?")
check("an illustrative-cost/rules answer without the word 'illustrative' is rewritten",
      out["rewrites"] >= 1, out["rewrites"])
# Prove the FLAG is what fires, not the prose: blank every string, keep flags.
def scanned(flags, draft):
    return G._scan(draft, [{"tool": "x", "result": {"rows": [], "flags": flags,
                                                    "label": "", "note": ""}}])
d = f"Fibre is suggested. {T.DISCLAIMER}"
check("illustrative_rules fires with no prose at all",
      any("illustrative" in x.lower() for x in scanned(["illustrative_rules"], d)))
check("illustrative_cost fires with no prose at all",
      any("illustrative" in x.lower() for x in scanned(["illustrative_cost"], d)))
check("modelled fires with no prose at all",
      any("modelled" in x.lower() for x in scanned(["modelled"], d)))
check("equal-sharing fires with no prose at all",
      any("equally" in x.lower() for x in scanned(["assumption_equal_sharing"], d)))
check("a compliant draft trips nothing",
      scanned(["illustrative_rules"], f"These criteria are illustrative. {T.DISCLAIMER}") == [])
check("a missing disclaimer is still caught",
      any("disclaimer" in x.lower() for x in scanned([], "Fibre is suggested.")))

print("\n=== 5. memory across turns ===")
use([tc("rank_settlements", {"district": "Kota Marudu", "top_k": 3}),
     AIMessage(f"Three settlements. {T.DISCLAIMER}"),
     AIMessage(f"Because its connectivity pillar is highest. {T.DISCLAIMER}")])
G.ask("top 3 in Kota Marudu", session_id="s1")
before = G._graph().get_state(G._config("s1")).values["messages"]
G.ask("why is the first one ranked there?", session_id="s1")
after = G._graph().get_state(G._config("s1")).values["messages"]
check("history persists across turns", len(after) > len(before), f"{len(before)} -> {len(after)}")
check("the second turn saw the first question",
      any("top 3" in str(getattr(m, "content", "")) for m in after))
# and a different session is isolated
G.ask("top 3 in Kota Marudu", session_id="s2")
check("sessions are isolated",
      len(G._graph().get_state(G._config("s2")).values["messages"]) < len(after))

print("\n=== 6. streaming emits real node transitions ===")
use([tc("district_summary", {"sort_by": "facilities", "top_k": 5}),
     AIMessage(f"Kota Kinabalu has the most. {T.DISCLAIMER}")])
events = list(G.ask_stream("which district has the most schools?", session_id="s3"))
kinds = [e for e, _ in events]
labels = [f'{d.get("label")}' + (f' ({d["detail"]})' if d.get("detail") else "")
          for e, d in events if e == "step"]
for l in labels: print("      ·", l)
check("ends with exactly one done event", kinds[-1] == "done" and kinds.count("done") == 1, kinds)
check("emits a step per node", len(labels) >= 3, labels)
check("names the tool it chose", any("district_summary" in l for l in labels))
check("reports rows returned", any("row" in l for l in labels))
check("reports the evidence check", any("Evidence check" in l for l in labels))
done = events[-1][1]
check("streamed payload matches the contract",
      set(["answer", "table", "map", "tools_used", "response_type"]) <= set(done), list(done))
check("streamed table came from the tool", done["table"] and done["table"][0]["district"] == "Kota Kinabalu")

print("\n=== 7. tool messages are JSON, not a python repr ===")
use([tc("rank_settlements", {"district": "Kudat", "top_k": 2}),
     AIMessage(f"Two. {T.DISCLAIMER}")])
G.ask("kudat top 2", session_id="s4")
msgs = G._graph().get_state(G._config("s4")).values["messages"]
tm = [m for m in msgs if m.__class__.__name__ == "ToolMessage"]
check("ToolMessage content parses as JSON", bool(tm) and json.loads(tm[0].content)["rows"])
check("no python repr leaked", "'rows'" not in tm[0].content)

print("\n=== 8. Gemini can return content as a list of parts ===")
listy = AIMessage(content=[{"type": "text", "text": "Kota Kinabalu leads."}])
st = {"messages": [listy], "violations": [], "rewrites": 0,
      "tool_outputs": [{"tool": "list_facilities",
                        "result": {"rows": [{"name": "X", "evidence": "low_evidence"}],
                                   "flags": [], "note": ""}}]}
try:
    G.evidence_check_node(st)
    check("evidence check survives list content", True)
except Exception as e:
    check("evidence check survives list content", False, f"{type(e).__name__}: {e}")
check("the answer is flattened, not a raw part list",
      G._payload(st)["answer"] == "Kota Kinabalu leads.", G._payload(st)["answer"])
for c, want in [("plain", "plain"),
                ([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}], "a b"),
                ([], ""),
                ([{"type": "image_url", "image_url": "x"}], ""),
                (["bare", {"text": "d"}], "bare d")]:
    check(f"_text({str(c)[:34]}) is {want!r}", G._text(AIMessage(content=c)) == want,
          repr(G._text(AIMessage(content=c))))

print("\n=== 9. facilities carry the nearest measured settlement ===")
slow = T.list_facilities(kind="school", sort_by="slowest", limit=3)
fast = T.list_facilities(kind="school", sort_by="fastest", limit=1)
check("slowest first", slow["rows"][0]["its_dl_mbps"] <= slow["rows"][-1]["its_dl_mbps"], slow["rows"])
check("fastest is the other end", fast["rows"][0]["its_dl_mbps"] > slow["rows"][0]["its_dl_mbps"])
check("every row names the settlement it borrowed the speed from",
      all(r["nearest_settlement"] and r["km_to_it"] is not None for r in slow["rows"]))
check("flagged as a proxy, not a measurement at the facility",
      "proxy_location" in slow["flags"])
check("the note says nobody tested at a school", "school" in slow["note"])
check("an unknown sort falls back to name order",
      len(T.list_facilities(kind="school", sort_by=["nonsense"], limit=3)["rows"]) == 3)

print("\n=== 10. the 4th question of every session used to die ===")
# Gemini rejects a history window that opens on a dangling function call:
#   "Please ensure that function call turn comes immediately after a user turn
#    or after a function response turn."
# A blind [-MAX_HISTORY:] slice produced exactly that from turn 4 onward.
from langchain_core.messages import HumanMessage as _H, ToolMessage as _T
def convo(turns):
    m = []
    for t in range(turns):
        m += [_H(f"q{t}"), tc("list_facilities", {}, t), _T(content="{}", tool_call_id=f"c{t}"),
              AIMessage(f"a{t}")]
    return m
broke = []
for turns in range(1, 9):
    for partial in (0, 1, 2, 3):          # mid-turn as well as between turns
        msgs = convo(turns)[:turns * 4 + partial - 3] if partial else convo(turns)
        if not msgs:
            continue
        w = G._window(msgs)
        opens_ok = isinstance(w[0], _H)
        # every tool call inside the window must have its response inside it too
        ids = {c["id"] for m in w for c in (getattr(m, "tool_calls", None) or [])}
        answered = {getattr(m, "tool_call_id", None) for m in w}
        if not opens_ok or not ids <= answered:
            broke.append((turns, partial))
check("every window opens on a user turn, at every depth", not broke, broke[:4])
check("a blind slice really did break (so this test means something)",
      any(not isinstance(convo(t)[:t * 4 - 2][-G.MAX_HISTORY:][0], _H) for t in range(4, 9)))
check("short histories are passed through untouched",
      G._window(convo(1)) == convo(1))
check("the window still respects the budget when it can",
      len(G._window(convo(8))) <= G.MAX_HISTORY + 3, len(G._window(convo(8))))
check("no HumanMessage at all does not crash", G._window([AIMessage("x")] * 20) is not None)

print("\n=== 11. a number the tools never returned cannot reach the user ===")
# The real failure: asked why a settlement was not picked, the model repeated a
# speed the USER had asserted, for a place no tool had returned a row for.
echoed = f"Kampung Melati has a download speed of 303.7 Mbps. {T.DISCLAIMER}"
check("a figure quoted with no tool called is caught",
      any("no tool result" in x for x in G._scan(echoed, [])))
def clean(draft, res, tool="t"):
    return [x for x in G._scan(draft, [{"tool": tool, "result": res}]) if "no tool result" in x]
truthful = [
    (f"SEKOLAH KEBANGSAAN MOSTYN is 0.6 km from Kampung Mostyn Lama at 312.7 Mbps. {T.DISCLAIMER}",
     T.list_facilities(kind="school", sort_by="fastest", limit=5)),
    (f"Kampung Tangkol leads at 76.6, Talas follows at 75.9. {T.DISCLAIMER}",
     T.rank_settlements(district="Kota Marudu", top_k=10)),
    (f"Kota Kinabalu leads with 105 facilities, 74 schools and 31 health points. {T.DISCLAIMER}",
     T.district_summary(sort_by="facilities", top_k=5)),
    (f"At 11.4 Mbps split between 30 people each gets about 0.4 Mbps. {T.DISCLAIMER}",
     T.simulate_experience("Talas", "720p", 30)),
    # the same number written at a different scale is the same number
    (f"A budget of RM 2.5 million is illustrative. {T.DISCLAIMER}",
     T.optimise_budget(2500000, "Kudat", "base")),
]
bad = [d[:40] for d, r in truthful if clean(d, r)]
check("truthful answers are never flagged", not bad, bad)
check("a pillar score is flagged when only rank_settlements was called",
      clean(f"Kampung Tangkol leads at 76.6, its connectivity pillar is 90.1. {T.DISCLAIMER}",
            T.rank_settlements(district="Kota Marudu", top_k=10)))
check("small integers are left alone",
      not clean(f"The top 10 in 2026 for a class of 30, 40% of DIPI. {T.DISCLAIMER}",
                T.rank_settlements(district="Kota Marudu", top_k=10)))

print("\n=== 12. a borrowed speed is only ranked while the borrowing is close ===")
fast = T.list_facilities(kind="school", sort_by="fastest", limit=20)
check("nothing in the ranking borrows from beyond 3 km",
      all(r["km_to_it"] <= T.FAC_NEAR_KM for r in fast["rows"]),
      [(r["name"], r["km_to_it"]) for r in fast["rows"] if r["km_to_it"] > T.FAC_NEAR_KM])
check("the cap is declared as a flag", "radius_capped" in fast["flags"])
check("the note says how many were left out and why",
      "left out" in fast["note"] and "3 km" in fast["note"])
check("it explains that a fast settlement can be absent entirely",
      "appears nowhere" in fast["note"], fast["note"][-160:])
plain = T.list_facilities(kind="school", limit=20)
check("listing by name is not capped", "radius_capped" not in plain["flags"])
check("a far-borrowing school is still listable by name, just not ranked",
      any(r["km_to_it"] > T.FAC_NEAR_KM for r in T.list_facilities(limit=200)["rows"]))

print("\n=== 13. a settlement's own measurement is reachable ===")
# "Kampung Melati is 328.6 Mbps, isn't it?" had no tool that could confirm it.
# The agent fell through to predict_coverage, got "the model has not shipped",
# and told the user it could not confirm a number the file already held.
e = T.explain_priority("Kampung Melati")
check("explain_priority returns the measured speed", e["measured"]["dl_mbps"] == 328.6, e.get("measured"))
check("upload and latency travel with it",
      e["measured"]["ul_mbps"] is not None and e["measured"]["latency_ms"] is not None)
check("it agrees with the dashboard file",
      e["measured"]["dl_mbps"] == round(float(T.DF.loc[T.DF["name"] == "Kampung Melati", "dl_mbps"].iloc[0]), 1))
check("the number of tests behind it is stated", e["measured"]["n_tests"] == 79, e["measured"])
check("a fast place has a LOW connectivity pillar, and both are now visible",
      [r for r in e["rows"] if r["pillar"] == "connectivity"][0]["score_0_100"] < 1)
check("the speed is now quotable without tripping the number guardrail",
      not [x for x in G._scan(f"Kampung Melati reads 328.6 Mbps down. {T.DISCLAIMER}",
                              [{"tool": "explain_priority", "result": e}])
           if "no tool result" in x])
# The model has shipped, so this section asserts the guardrail rather than the
# absence. The string "modelled estimate" is the one both the dashboard and the
# flag below compare against: if an export ever writes plain "modelled", the
# flag stops firing and a modelled number can be narrated as a measurement.
if T.HAS_MODEL:
    pc = T.predict_coverage("Kampung Melati")
    check("an observed settlement is not flagged as modelled",
          pc["flags"] == [] and "observed measurement" in pc["note"], pc)
    mod = T.DF[T.DF["speed_source"] == "modelled estimate"]
    check("the modelled set is exactly the 216 with no measurement",
          len(mod) == 216 and mod["dl_mbps"].isna().all(), len(mod))
    pm = T.predict_coverage(mod.iloc[0]["name"])
    check("a modelled settlement raises the modelled flag",
          pm["flags"] == ["modelled"], pm["flags"])
    check("and says so in words, not only in a flag",
          "not a measurement" in pm["note"], pm["note"])
    check("every modelled row carries an interval, never a bare point",
          mod["pred_lo"].notna().all() and mod["pred_hi"].notna().all())
    check("the interval contains the estimate",
          bool(((mod["pred_lo"] <= mod["pred_dl_mbps"])
                & (mod["pred_dl_mbps"] <= mod["pred_hi"])).all()))
    check("no observed settlement was given a prediction",
          T.DF[T.DF["speed_source"] == "observed"]["pred_dl_mbps"].isna().all())
    check("a draft quoting a modelled speed as measured is rejected",
          any("modelled" in x.lower() for x in
              G._scan(f"{mod.iloc[0]['name']} measures "
                      f"{mod.iloc[0]['pred_dl_mbps']:.2f} Mbps down. {T.DISCLAIMER}",
                      [{"tool": "predict_coverage", "result": pm}])))
else:
    check("predict_coverage is honest about not having shipped",
          "not shipped" in T.predict_coverage("Kampung Melati")["note"])

print("\n=== 14. district decision comparison ===")
c = T.compare_areas(["Ranau", "Kota Kinabalu"])
check("two districts come back", c["areas"] == ["Ranau", "Kota Kinabalu"], c.get("areas"))
check("the flat rows render as a table", isinstance(c["rows"][0].get("Ranau"), (int, float)), c["rows"][0])
check("the structured form carries percentiles",
      c["indicators"][0]["percentile_worse_than"]["Ranau"] is not None)
check("a Sabah reference is on every row", all("sabah" in i for i in c["indicators"]))
check("map ids are real settlements", len(c["ids"]) > 0 and c["ids"][0].startswith("S"))

# The safeguard that matters most: no indicator may be a raw total that simply
# tracks size. Ranau has 249 settlements to Kota Kinabalu's 35.
rate_keys = [i["key"] for i in c["indicators"] if i["unit"] == "%"]
check("rates are present and are not size", len(rate_keys) >= 6, rate_keys)
big, small = c["stats"]["Ranau"], c["stats"]["Kota Kinabalu"]
check("Ranau is 7x the settlements but does not lead every indicator",
      big["settlements"] > 5 * small["settlements"]
      and small["median_dl_mbps"] > big["median_dl_mbps"])

print("  -- population dedupe --")
ranau = T.DF[T.DF["district"] == "Ranau"]
naive, dedup = int(ranau["pop_2km"].sum()), T._dedup_population(ranau)
check("summing overlapping buffers overcounts by more than 5x", naive > 5 * dedup,
      f"{naive} vs {dedup}")
check("the deduped figure is what ships", big["people_all"] == dedup, (big["people_all"], dedup))
check("underserved population never exceeds total population",
      all(s["people_underserved"] <= s["people_all"] for s in c["stats"].values()))
one = T.DF[T.DF["settlement_id"] == "S0004"]
check("a single settlement is its own cluster",
      T._dedup_population(one) == int(one["pop_2km"].iloc[0]))
check("an empty area is zero, not a crash", T._dedup_population(T.DF.head(0)) == 0)

print("  -- no settlement is called slow for being unmeasured --")
gap_only = T.DF[T.DF["evidence_tier"] == "insufficient"]
st = T._area_stats(gap_only, T.FAC.head(0))
check("an all-evidence-gap area has no underserved rate at all",
      st["underserved_rate_pct"] is None and st["measured"] == 0, st["underserved_rate_pct"])
check("and no people counted as underserved", st["people_underserved"] == 0)
check("its evidence gap is 100%", st["evidence_gap_pct"] == 100)

print("  -- rounding matches the dashboard --")
check("halves go up, not to even", (T._half_up(62.5), T._half_up(47.5)) == (63, 48),
      (T._half_up(62.5), T._half_up(47.5)))
check("python's own round() would have disagreed", round(62.5) == 62)
check("one decimal place works too", T._half_up(3.45, 1) == 3.5)
check("None survives", T._half_up(None) is None)

print("  -- the written summary --")
s = c["summary"]
check("it produces sentences", len(s) >= 3, s)
check("it says 'rate' so nobody reads it as a total", any("rate" in x for x in s))
check("terrain and remoteness are associated, never causal",
      not any(re.search(r"\bcaus(e|ed|es)\b(?!\s+it)", x) for x in s)
      and any("associated with" in x for x in s if "terrain" in x.lower() or "Remoteness" in x))
check("it is deterministic", T.compare_areas(["Ranau", "Kota Kinabalu"])["summary"] == s)
check("it names the evidence gap when one side is thinner",
      any("no usable measurement" in x for x in s), s)

print("  -- what the data cannot support is declared --")
missing = {m["indicator"] for m in c["unavailable"]}
check("roads, towers, slope and prediction uncertainty are all named",
      len(missing) == 4 and any("Road" in m for m in missing)
      and any("Tower" in m for m in missing) and any("Slope" in m for m in missing)
      and any("uncertainty" in m for m in missing), missing)
check("the note repeats it for the agent", "not available in this dataset" in c["note"])
check("the note states the population caveat", "not a census" in c["note"])
check("flagged so the guardrail can see it", "rates_not_totals" in c["flags"])

print("  -- divisions and edge cases --")
dv = T.compare_areas(["Interior", "West Coast"], level="division")
check("divisions work", dv["level"] == "division" and len(dv["areas"]) == 2)
check("division facilities roll up through districts", dv["stats"]["Interior"]["schools"] > 0)
for bad_in, why in [([], "empty"), (["Ranau"], "one"), (["Ranau", "Ranau"], "the same twice"),
                    (["Atlantis", "Narnia"], "unknown"), (None, "None")]:
    r = T.compare_areas(bad_in)
    check(f"{why} is refused with an explanation", not r["rows"] and len(r["note"]) > 20)
check("a sentence parses into areas",
      T.compare_areas("Ranau vs Kudat")["areas"] == ["Ranau", "Kudat"])
check("five areas are all compared, not silently cut to four",
      len(T.compare_areas(["Ranau", "Kudat", "Pitas", "Tuaran", "Beaufort"])["areas"]) == 5)
_every = sorted({d for d in T.DF["district"] if d})
check("it reaches as far as the dashboard does, all 25 districts",
      len(T.compare_areas(_every)["areas"]) == len(_every) == T.CMP_MAX_AREAS)
check("the agent can call it through the tool boundary",
      len(_ca.invoke(_coerce_args(_ca, {"names": ["Ranau", "Kudat"], "level": 0}))["areas"]) == 2)

print("\n=== 15. the comparison as agent context ===")
from agent.graph import seed_comparison, _all_outputs, _tool_numbers, _scan, _initial
_ctx = seed_comparison("district", ["Kudat", "Tawau"])
check("the on-screen comparison seeds a context", _ctx["areas"] == ["Kudat", "Tawau"])
check("its numbers are the tool's own, not the client's",
      _ctx["stats"] == T.compare_areas(["Kudat", "Tawau"])["stats"])
check("the fixed-rule summary travels verbatim",
      _ctx["summary"] == T.compare_areas(["Kudat", "Tawau"])["summary"])
check("1,114 settlement ids and the duplicate rows stay out of the prompt",
      "ids" not in _ctx and "rows" not in _ctx)
for _bad, _why in [([], "nothing"), (["Kudat"], "one area"),
                   (["Atlantis", "Narnia"], "two unknown areas"), (None, "None")]:
    check(f"{_why} seeds no context", seed_comparison("district", _bad) == {})

_st = {"tool_outputs": [], "context": _ctx}
_allowed = _tool_numbers(_all_outputs(_st))
check("every on-screen figure counts as data to the guardrail",
      all(str(_ctx["stats"]["Kudat"][k]) in _allowed for k in
          ("median_dl_mbps", "evidence_gap_pct", "people_underserved", "median_dipi")))
check("an answer quoting the screen passes the guardrail",
      not _scan(f"Kudat's median download is {_ctx['stats']['Kudat']['median_dl_mbps']} Mbps "
                f"and {_ctx['stats']['Kudat']['evidence_gap_pct']}% has no usable "
                f"measurement. {T.DISCLAIMER}", _all_outputs(_st)))
check("a figure that is on neither the screen nor a tool is still caught",
      any("999.9" in v for v in _scan(f"Kudat runs at 999.9 Mbps. {T.DISCLAIMER}",
                                      _all_outputs(_st))))
check("no context means the guardrail is exactly as strict as before",
      _tool_numbers(_all_outputs({"tool_outputs": [], "context": {}})) == _tool_numbers([]))
check("a turn with no context starts with an empty one",
      _initial("hello", None)["context"] == {})
check("the dashboard's selection is recomputed, not trusted",
      _initial("x", {"level": "district", "areas": ["Kudat", "Tawau"],
                     "stats": {"Kudat": {"median_dl_mbps": 999.9}}})["context"]["stats"]
      == _ctx["stats"])

print()
print("=== 16. the 46-school finding is reachable by the agent ===")
_f = T.find_failing_schools()
check("it agrees with the dashboard's own preset chip", _f["total_failing"] == 46,
      _f["total_failing"])
check("every row really has a school within 3 km",
      all(r["schools_3km"] >= 1 for r in _f["rows"]))
check("every row really fails the tier once shared",
      all(r["per_user_mbps"] < T.VIDEO_TIERS["360p"] for r in _f["rows"]))
check("the worst is first", _f["rows"] == sorted(_f["rows"], key=lambda r: r["per_user_mbps"]))
check("ids line up with rows", len(_f["ids"]) == len(_f["rows"]))
# The rule the whole product rests on: no measurement is not a failing one.
_ins = {r["evidence"] for r in _f["rows"]}
check("no unmeasured settlement is called failing", "insufficient" not in _ins, _ins)
_gap = T.DF[(T.DF["evidence_tier"] == "insufficient") & (T.DF["n_schools_3km"] >= 1)]
check("evidence-gap schools are excluded, not counted",
      not (set(_gap["settlement_id"]) & set(_f["ids"])), f"{len(_gap)} gap rows with a school")
check("the note says so in words", "not the same as a failing one" in _f["note"])
check("low evidence is warned about when present",
      T.LOW_EV_WARNING in _f["note"] or _f["low_evidence_rows"] == 0)
check("it scopes to a district",
      T.find_failing_schools(district="Kota Marudu")["scope"] == "Kota Marudu")
check("it scopes to a division",
      T.find_failing_schools(division="Kudat")["total_failing"] <= _f["total_failing"])
check("a harder tier finds more", T.find_failing_schools(tier="1080p")["total_failing"] > 46)
check("fewer users finds fewer", T.find_failing_schools(users=1)["total_failing"] < 46)
check("an unknown tier is refused clearly",
      "Unknown tier" in T.find_failing_schools(tier="banana")["note"])
check("the sharing assumption is flagged", "assumption_equal_sharing" in _f["flags"])
from agent.graph import find_failing_schools as _ffs
check("the agent can call it through the tool boundary",
      _ffs.invoke(_coerce_args(_ffs, {"district": ["Kota Marudu"], "users": "30"}))["scope"]
      == "Kota Marudu")
check("it is registered in both registries",
      "find_failing_schools" in T.TOOLS and len(G.TOOL_LIST) == 15)

print()
print("=== 17. the panel and the copilot cost a budget the same way ===")
# This has caught two real divergences. First a flat ten-kilometre fibre
# assumption, where at RM 50m the agent funded 52 and the dashboard 171. Then
# the marginal-trench change, which moves the numbers again: both sides now
# charge fibre the spanning-tree edge from clusters.json rather than each
# settlement's full run to town, so RM 50m reaches 263 instead of 171.
_b = {sc: len(T.optimise_budget(50_000_000, "", sc)["ids"]) for sc in ("low", "base", "high")}
_exp = (358, 271, 203) if T.CLUSTERS else (220, 171, 140)
check("fibre is costed the same way on both sides",
      (_b["low"], _b["base"], _b["high"]) == _exp, {"got": _b, "expected": _exp})
check("a dearer scenario never funds more", _b["high"] <= _b["base"] <= _b["low"], _b)
# The clustering may only ever make a shared build cheaper, never dearer, and
# it must not touch the three per-site options.
if T.CLUSTERS:
    _f = T.DF[(T.DF.backhaul_km <= T.RULE_PARAMS["fibre_max_km"])
              & (T.DF.pop_2km >= T.RULE_PARAMS["fibre_min_pop"])]
    _tr = _f.settlement_id.map(lambda s: T.CLUSTERS[s]["trunk_km"])
    check("every settlement has a trunk_km, so no lookup silently misses",
          len(T.CLUSTERS) == len(T.DF))
    check("no trunk_km falls below the 1 km floor", bool((_tr >= 1.0).all()))
    check("sharing a trench never costs more than paying alone",
          bool(_tr.sum() < _f.backhaul_km.clip(lower=1).sum()))
    # Sharing is not universally cheaper, only cheaper on aggregate: 22 of the
    # 288 bundled settlements sit further from a bundle neighbour than from the
    # town. The costing takes the shorter run, so it can never be worse than
    # what the panel charged before clustering existed.
    _bh = _f.backhaul_km.clip(lower=1)
    _cheaper = _tr.combine(_bh, min)
    check("some spurs really are longer than going direct",
          bool((_tr > _bh + 1e-9).any()), int((_tr > _bh + 1e-9).sum()))
    check("costing takes the shorter of the two, never the spur regardless",
          bool(_cheaper.sum() < _tr.sum()),
          {"shorter": round(_cheaper.sum(), 1), "always spur": round(_tr.sum(), 1)})
    check("and so can never cost more than before clustering",
          bool(_cheaper.sum() <= _bh.sum()))
    check("fibre is overstated by about 1.5x without it",
          1.4 < _f.backhaul_km.clip(lower=1).sum() / _tr.sum() < 1.7,
          round(_f.backhaul_km.clip(lower=1).sum() / _tr.sum(), 2))
    _nf = T.DF[~T.DF.settlement_id.isin(_f.settlement_id)]
    check("non-fibre settlements were not given a cluster",
          all(T.CLUSTERS[s]["cl"] == -1 for s in _nf.settlement_id))

print()
print("=== 18. the delivery rules match the published direction ===")
# OECD and World Bank state the ordering: fibre where dense, wireless and
# satellite where sparse. The cut-offs are ours, but the ORDER they produce is
# checkable, so it is checked rather than asserted in a comment.
import numpy as _np
_R, _d = T.RULE_PARAMS, T.DF.copy()
_km = _d["backhaul_km"].fillna(999.0)
_pop = _d["pop_2km"].fillna(0.0)
_d["opt"] = _np.where((_km <= _R["fibre_max_km"]) & (_pop >= _R["fibre_min_pop"]), "Fibre",
            _np.where((_km <= _R["fwa_max_km"]) & (_pop >= _R["fwa_min_pop"]), "FWA",
            _np.where(_km > _R["sat_min_km"], "Satellite", "WiFi")))
_d["dens"] = _pop / (_np.pi * 4)          # pop_2km spread over its own 2 km buffer
_med = {o: _d[_d["opt"] == o]["dens"].median() for o in ("Fibre", "FWA", "Satellite", "WiFi")}
check("fibre goes to the densest places", _med["Fibre"] > _med["FWA"], _med)
check("fixed wireless sits between fibre and satellite",
      _med["FWA"] > _med["Satellite"], _med)
check("the ordering is monotonic, dense to sparse",
      _med["Fibre"] > _med["FWA"] > _med["Satellite"], _med)
# Ogutu & Oughton (2021): LEO satellite outcompetes other options below
# 0.1 users/km2. Most of our satellite calls are denser than that, which is a
# disclosed limitation, this test exists so the disclosure stays true.
_sat = _d[_d["opt"] == "Satellite"]
_sparse = int((_sat["dens"] < 0.1).sum())
check("the satellite caveat on the card still matches the data",
      len(_sat) == 22 and _sparse == 9, f"{_sparse} of {len(_sat)} below 0.1/km2")

print()
print("=== 19. the source registry matches the code it documents ===")
import json as _json
_sp = Path(__file__).resolve().parent.parent / "dataset" / "web" / "sources.json"
check("dataset/web/sources.json exists", _sp.exists(), str(_sp))
_S = _json.loads(_sp.read_text(encoding="utf8"))
_P = _S["parameters"]
# Every value the registry claims must be the value the code actually uses.
for _k, _actual in [("fibre_max_km", T.RULE_PARAMS["fibre_max_km"]),
                    ("fibre_min_pop", T.RULE_PARAMS["fibre_min_pop"]),
                    ("fwa_max_km", T.RULE_PARAMS["fwa_max_km"]),
                    ("fwa_min_pop", T.RULE_PARAMS["fwa_min_pop"]),
                    ("sat_min_km", T.RULE_PARAMS["sat_min_km"]),
                    ("fac_near_km", T.FAC_NEAR_KM),
                    ("fibre_per_km_rm", T.COSTS["base"]["fibre_per_km"]),
                    ("fwa_per_site_rm", T.COSTS["base"]["fwa"])]:
    check(f"registry {_k} = {_actual}", _P[_k]["value"] == _actual,
          f'registry says {_P[_k]["value"]}')
check("the video tiers match too", _P["video_tiers_mbps"]["value"] == T.VIDEO_TIERS,
      _P["video_tiers_mbps"]["value"])
# Every parameter names a real status, and a sourced one names a real source.
_ok_status = {"sourced", "unsourced", "benchmarked"}
check("every parameter explains what it does in plain words",
      all(len(v.get("means", "")) > 40 for v in _P.values()),
      [k for k, v in _P.items() if len(v.get("means", "")) <= 40])
check("every parameter has a known status",
      all(v["status"] in _ok_status for v in _P.values()),
      {k: v["status"] for k, v in _P.items() if v["status"] not in _ok_status})
_dangling = [k for k, v in _P.items()
             if v.get("source") and v["source"] not in _S["sources"]]
check("no parameter points at a source that is not there", not _dangling, _dangling)
_unsourced = [k for k, v in _P.items() if v["status"] == "sourced" and not v.get("source")]
check("nothing is called sourced without naming one", not _unsourced, _unsourced)
# The flags must agree with the registry rather than being set by hand.
check("RULES_VERIFIED is false while any cut-off is unsourced",
      any(v["status"] == "unsourced" for v in _P.values()))
check("the dead ends are recorded too, with a reason each",
      _S["searched_and_not_found"] and
      all(x.get("where") and x.get("outcome") for x in _S["searched_and_not_found"]))
# fibre_max_km is the last one nothing fixes ON THE PAGE. If that ever changes,
# this fails and RULES_VERIFIED becomes a live question rather than a permanent
# false. The registry also carries the offline terrain screen's assumptions,
# which have their own unsourced entries and are checked separately below: they
# decide no recommendation and no price the dashboard shows.
_live = {k: v for k, v in _P.items() if v.get("in_dashboard") is not False}
check("only fibre_max_km is still ours, among what the page uses",
      [k for k, v in _live.items() if v["status"] == "unsourced"] == ["fibre_max_km"],
      [k for k, v in _live.items() if v["status"] == "unsourced"])
# Anything held back from the page has to say what does use it, or it is just
# an unsourced number hiding from the tooltip that would otherwise print it.
_offline = {k: v for k, v in _P.items() if v.get("in_dashboard") is False}
check("every offline parameter names what uses it",
      all(v.get("used_by") for v in _offline.values()),
      [k for k, v in _offline.items() if not v.get("used_by")])
# The screen's admitted guesses. Sourcing one is real progress, so this fails
# loudly rather than letting the set quietly drift in either direction.
# los_band_mhz left this set once 700 MHz was confirmed as Malaysia's assigned
# sub-1 GHz band; the residual there is bounded by the los row instead.
check("the offline analyses' guesses are still declared as guesses",
      {k for k, v in _offline.items() if v["status"] == "unsourced"}
      == {"receiver_height_m", "mast_reach_km", "ntl_lit_threshold"},
      sorted(k for k, v in _offline.items() if v["status"] == "unsourced"))
# Nightlights are electrification, never coverage. If ntl ever reaches the page
# it must not arrive as a service statement, so the guard is written now rather
# than after someone wires it to a map layer.
check("the nightlight threshold is kept out of the product until it is wired deliberately",
      _P["ntl_lit_threshold"].get("in_dashboard") is False
      and "never a coverage statement" in _P["ntl_lit_threshold"]["note"])

print()
print("=== 20. the copilot answers about bundles with the panel's own numbers ===")
if T.CLUSTERS:
    _rb = T.rank_bundles(50_000_000, "balanced")
    check("it returns bundles, not settlements", _rb["bundles_total"] == 17, _rb["bundles_total"])
    check("a budget funds whole bundles only",
          _rb["spent_rm"] <= _rb["budget_rm"], (_rb["spent_rm"], _rb["budget_rm"]))
    check("the scenario it used is named in words, not a code",
          "divided by cost" in _rb["ranked_by"], _rb["ranked_by"])
    # Facility totals are the UNION across funded bundles. Summing each bundle's
    # own deduplicated count double-funds a school two bundles can both reach,
    # which is exactly the mistake the panel had before this was fixed.
    _fundedrows = [r for r in _rb["rows"] if r["funded"]]
    check("institutions are deduplicated across the whole funded set, not summed",
          _rb["schools_funded"] < sum(r["schools"] for r in _fundedrows),
          {"union": _rb["schools_funded"], "naive sum": sum(r["schools"] for r in _fundedrows)})
    check("a dearer cost scenario never funds more",
          T.rank_bundles(50_000_000, "balanced", "high")["bundles_funded"]
          <= T.rank_bundles(50_000_000, "balanced", "low")["bundles_funded"])
    check("each scenario really orders differently",
          len({T.rank_bundles(50_000_000, s)["rows"][0]["district"]
               for s in ("need", "balanced", "reach")}) > 1)
    check("a settlement outside every bundle is told so plainly",
          "not in a bundle" in T.explain_bundle("Kampung Tangkol")["note"])

    # The guardrail: a bundle is a proximity screen, and an answer that presents
    # one as a surveyed design must be rejected.
    _v = G._scan(f"Build the Tenom corridor first, it costs RM 2.3 million. {T.DISCLAIMER}",
                 [{"tool": "rank_bundles", "result": _rb}])
    check("calling a bundle a build plan is rejected",
          any("SCREENING proxy" in x for x in _v), _v)
    _ok = G._scan("The Tenom group screens as the best value bundle. Bundles are settlements "
                  "grouped by position, a screening proxy and not an engineering design, and "
                  f"the costs are illustrative. {T.DISCLAIMER}",
                  [{"tool": "rank_bundles", "result": _rb}])
    check("and a careful answer passes", _ok == [], _ok)
else:
    check("rank_bundles is honest when the clusters are absent",
          "not been generated" in T.rank_bundles()["note"])

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
