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
check("predict_coverage is still honest about not having shipped",
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
check("more than four is capped at four",
      len(T.compare_areas(["Ranau", "Kudat", "Pitas", "Tuaran", "Beaufort"])["areas"]) == 4)
check("the agent can call it through the tool boundary",
      len(_ca.invoke(_coerce_args(_ca, {"names": ["Ranau", "Kudat"], "level": 0}))["areas"]) == 2)

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
