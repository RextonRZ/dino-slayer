"""Tests for the agent, with a scripted LLM standing in for Gemini.

    python agent/test_agent.py        # from the repo root. No API key needed.

The LLM is replaced by a script of canned messages, so every assertion here is
about OUR code: argument handling, the tools, the evidence guardrail, the
rewrite cap, conversation memory, and the streamed graph steps. Nothing here
calls a paid API or needs the network.
"""
import json
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
from agent.graph import _coerce_args, rank_settlements as _rs
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

print(f"\n{ok} passed, {fail} failed")
sys.exit(1 if fail else 0)
