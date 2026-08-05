"""Tanya Dino: LangGraph state machine over the grounded tools.

    agent → tools → evidence_check → (rewrite, capped) → respond

The point of the graph is the evidence_check node: it is plain Python, it sees
the RAW tool rows rather than the model's prose, and the model cannot reach the
user without passing it. If the draft breaks an evidence rule, the answer is
sent back to be rewritten with the violations named — and after two attempts a
hard-templated safe answer is emitted instead.

Nothing here computes a number. Numbers come from agent/tools.py.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from . import tools as T

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# The LangSmith key is the only switch. There is no separate on/off flag to get
# out of step with it: a key means trace, no key means do not. Set here because
# langchain reads LANGSMITH_TRACING from the environment rather than from us,
# and a placeholder key would otherwise make it retry every run against an
# endpoint that will never accept it.
TRACING = os.getenv("LANGSMITH_API_KEY", "").strip().startswith("ls")
os.environ["LANGSMITH_TRACING"] = "true" if TRACING else "false"

MAX_REWRITES = 2
# Conversation history is trimmed rather than allowed to grow without bound: a
# long session would otherwise resend every tool result on every turn.
MAX_HISTORY = 12
FORBIDDEN_FOR_INSUFFICIENT = re.compile(
    r"\b(underserved|poor coverage|no coverage|confirmed|definitely|proven)\b", re.I)

SYSTEM = f"""You are Tanya Dino, the planning copilot for the Dino Slayer digital-inclusion
screening tool for Sabah, Malaysia. You answer ONLY by calling the provided tools and
summarising what they return.

Rules you must follow:
- Never compute, estimate or recall a number yourself. Every number in your answer must
  appear in a tool result. If a tool did not return it, do not say it.
- Ranking is the Digital Inclusion Priority Index (DIPI), a transparent weighted blend:
  connectivity need 40%, population at stake 25%, institutions served 15%, equity 20%.
  It screens communities for FURTHER ASSESSMENT.
- Respect evidence tiers exactly. "insufficient" means say "evidence needed" — never
  "underserved", "poor coverage" or "confirmed". "low_evidence" means include the
  limited-tests warning.
- Data is crowdsourced quarterly aggregates (Ookla 2025 Q1-Q4), not live measurement.
- Cost and intervention outputs are illustrative. Never give a single confident price.
- This tool does not confirm coverage status, locate infrastructure, assign operator
  fault, or make deployment decisions. If asked, say what the data can and cannot
  support, then answer the nearest question it can.
- Be concise and plain, for a district officer. End every answer with exactly:
  "{T.DISCLAIMER}"

How to write the answer:
- The rows a tool returns are shown to the user as a TABLE next to your reply. Do not
  restate that table in prose. Listing ten settlements with their scores inline makes a
  wall of text the user has to parse twice.
- Instead say what the rows MEAN in two or three sentences: how many there are, what the
  top one is and why, and anything that stands out (a very low speed, a low_evidence row,
  a district that dominates the list). Then stop.
- Name at most three settlements in prose. The rest are in the table.
- Never use markdown headings, bullets or code fences. Plain sentences only.
"""


# ── the nine tools, as LangChain tools ───────────────────────────────────────
@tool
def rank_settlements(district: str = "", division: str = "", top_k: int = 10,
                     require_school: bool = False) -> dict:
    """Highest-priority settlements by DIPI. Optionally filter by district or division,
    or to those with at least one school within 3 km."""
    return T.rank_settlements(district, division, top_k, require_school)


@tool
def explain_priority(name_or_id: str) -> dict:
    """Why one settlement is ranked where it is: the four pillar scores and their weights."""
    return T.explain_priority(name_or_id)


@tool
def compare_settlements(name_a: str, name_b: str) -> dict:
    """Compare two settlements pillar by pillar."""
    return T.compare_settlements(name_a, name_b)


@tool
def simulate_experience(name_or_id: str, task: str = "720p", users: int = 5) -> dict:
    """What people can actually do online, given the measured speed shared between
    `users` people. Tasks: 360p, 480p, 720p, 1080p, 4k."""
    return T.simulate_experience(name_or_id, task, users)


@tool
def predict_coverage(name_or_id: str) -> dict:
    """Modelled speed estimate and its uncertainty, where no measurement exists."""
    return T.predict_coverage(name_or_id)


@tool
def recommend_intervention(name_or_id: str) -> dict:
    """Suggested connectivity option and the rules that fired. Illustrative criteria."""
    return T.recommend_intervention(name_or_id)


@tool
def optimise_budget(budget_rm: float, district: str = "", scenario: str = "base") -> dict:
    """Which settlements a budget could fund. Scenario is low, base or high.
    Costs are illustrative placeholders, not procurement estimates."""
    return T.optimise_budget(budget_rm, district, scenario)


@tool
def plan_survey(district: str = "", top_k: int = 10) -> dict:
    """Where to measure next: settlements with no usable measurement, ranked by stakes."""
    return T.plan_survey(district, top_k)


@tool
def generate_validation_report(district: str = "", top_k: int = 10) -> dict:
    """A markdown field-validation shortlist for a district."""
    return T.generate_validation_report(district, top_k)


@tool
def district_summary(district: str = "", sort_by: str = "facilities", top_k: int = 25) -> dict:
    """Compare districts: settlements, evidence gap, median speed, and how many schools
    and health points actually sit inside each one. Use this for "which district has the
    most schools / hospitals / settlements / evidence gap". Sort by facilities, schools,
    health, settlements, evidence_gap or priority."""
    return T.district_summary(district, sort_by, top_k)


@tool
def list_facilities(district: str = "", kind: str = "", limit: int = 50) -> dict:
    """The actual NAMES of schools and health points, optionally within one district.
    Use this when asked to list or name facilities. kind: school, health, hospital,
    clinic, doctors, or empty for all."""
    return T.list_facilities(district, kind, limit)


TOOL_LIST = [rank_settlements, explain_priority, compare_settlements, simulate_experience,
             predict_coverage, recommend_intervention, optimise_budget, plan_survey,
             generate_validation_report, district_summary, list_facilities]


class TDState(TypedDict):
    messages: Annotated[list, add_messages]
    tool_outputs: list
    violations: list
    rewrites: int


@lru_cache(maxsize=2)
def _llm(bound: bool = False):
    """Cached. A new ChatGoogleGenerativeAI per node call rebuilt the client and
    re-read credentials on every hop of the ReAct loop."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    key = os.getenv("GOOGLE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GOOGLE_API_KEY missing. Copy agent/.env.example to agent/.env "
                           "and put your Gemini key in it.")
    llm = ChatGoogleGenerativeAI(model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
                                 google_api_key=key, temperature=0,
                                 max_retries=3)      # transient 429/503 must not end the turn
    return llm.bind_tools(TOOL_LIST) if bound else llm


def agent_node(state: TDState):
    msgs = [SystemMessage(SYSTEM)] + state["messages"][-MAX_HISTORY:]
    return {"messages": [_llm(bound=True).invoke(msgs)]}


def _coerce_args(fn, args) -> dict:
    """Bend the model's arguments to the tool's declared types before Pydantic sees them.

    The schema says `district: str`, and Gemini sometimes sends
    {"district": ["Kota Marudu"]}. LangChain validates against that schema
    BEFORE the function body runs, so the defensive coercion inside tools.py
    never got a chance: the call died as a ValidationError, tools_node caught it,
    and the turn came back with an empty table and no explanation.

    The schema stays strict, because it is what tells the model what to send.
    Sanitising happens here instead.
    """
    if not isinstance(args, dict):
        return {}
    fields = getattr(getattr(fn, "args_schema", None), "model_fields", None)
    if not fields:
        return args
    out = {}
    for k, v in args.items():
        f = fields.get(k)
        if f is None:
            continue                       # an argument this tool does not take
        ann = f.annotation
        if ann is str and not isinstance(v, str):
            v = T._s(v)
        elif ann is bool and not isinstance(v, bool):
            v = T._s(v).lower() in ("1", "true", "yes", "y")
        elif ann is int and not isinstance(v, int):
            v = T._i(v, 0)
        elif ann is float and not isinstance(v, (int, float)):
            v = T._f(v, 0.0)
        out[k] = v
    return out


def tools_node(state: TDState):
    """Run the requested tools and keep the RAW rows, which evidence_check needs."""
    last = state["messages"][-1]
    out_msgs, raw = [], list(state.get("tool_outputs") or [])
    by_name = {t.name: t for t in TOOL_LIST}
    for call in getattr(last, "tool_calls", []) or []:
        fn = by_name.get(call["name"])
        try:
            result = (fn.invoke(_coerce_args(fn, call["args"])) if fn
                      else {"note": f"unknown tool {call['name']}"})
        except Exception as e:                      # a broken tool must not crash the graph
            result = {"rows": [], "ids": [], "note": f"tool error: {e}"}
        raw.append({"tool": call["name"], "result": result})
        # JSON, not str(dict). A Python repr sends single quotes and None, which
        # the model then has to guess at; JSON is unambiguous and cheaper.
        out_msgs.append(ToolMessage(content=json.dumps(result, default=str),
                                    tool_call_id=call["id"]))
    return {"messages": out_msgs, "tool_outputs": raw}


def _scan(draft: str, outputs: list) -> list:
    """The guardrail. Pure Python, reading raw tool rows — not the model's word for it.

    Detection keys off the machine-readable `flags` a tool returns. It used to
    key off the prose in `label` and `note`, which meant rewording a sentence in
    tools.py could silently disarm a rule. The prose checks are kept as a
    fallback so an un-flagged tool still trips the right wire.
    """
    v = []
    ids_insufficient = []
    has_low = has_modelled = has_illustrative = has_sharing = False
    for o in outputs:
        r = o.get("result") or {}
        flags = set(r.get("flags") or [])
        for row in (r.get("rows") or []):
            ev = str(row.get("evidence", ""))
            if ev == "low_evidence":
                has_low = True
            if ev == "insufficient":
                ids_insufficient.append(row.get("name", ""))
        # ANY illustrative output, cost or rules. The prose check used to be
        # startswith("Illustrative planning"), which matched optimise_budget but
        # silently missed recommend_intervention's "Illustrative decision
        # criteria" — so rule-based advice was never required to say so.
        if flags & {"illustrative_cost", "illustrative_rules"} \
                or str(r.get("label", "")).lower().startswith("illustrative"):
            has_illustrative = True
        if "modelled" in flags or "modelled estimate" in str(r.get("note", "")).lower():
            has_modelled = True
        if "assumption_equal_sharing" in flags:
            has_sharing = True
        if o["tool"] == "plan_survey" and r.get("rows"):
            ids_insufficient += [x.get("name", "") for x in r["rows"]]

    if ids_insufficient and FORBIDDEN_FOR_INSUFFICIENT.search(draft):
        v.append("Settlements with insufficient evidence are described as underserved or "
                 "confirmed. They must be described as 'evidence needed'.")
    if has_low and "limited tests" not in draft.lower():
        v.append(f"A low-evidence row is present. Add: {T.LOW_EV_WARNING}")
    if has_modelled and not re.search(r"modelled|estimate", draft, re.I):
        v.append("A modelled value is used without calling it a modelled estimate.")
    if has_illustrative and "illustrative" not in draft.lower():
        v.append("An illustrative cost or rule-based recommendation is present. Say plainly "
                 "that the criteria and figures are illustrative, not procurement estimates.")
    if has_sharing and not re.search(r"shar|assum|each|per person|per user", draft, re.I):
        v.append("A shared-connection figure is quoted without saying it assumes the link is "
                 "split equally between users. Name the assumption.")
    if T.DISCLAIMER.rstrip(".").lower() not in draft.lower():
        v.append(f"The closing disclaimer is missing: {T.DISCLAIMER}")
    return v


def evidence_check_node(state: TDState):
    draft = state["messages"][-1].content or ""
    return {"violations": _scan(draft, state.get("tool_outputs") or [])}


def rewrite_node(state: TDState):
    n = state.get("rewrites", 0) + 1
    if n > MAX_REWRITES:
        # Hard-templated safe answer. The model does not get a third attempt.
        # It carries EVERY caveat _scan can ask for, because this text is the
        # terminal state — if it tripped a rule of its own there would be
        # nothing left to rewrite it into.
        rows = [o for o in (state.get("tool_outputs") or []) if (o.get("result") or {}).get("rows")]
        body = "\n".join(f"- {o['tool']}: {len((o['result'] or {}).get('rows', []))} row(s)"
                         for o in rows) or "- no tool returned rows"
        safe = ("I could not phrase that within the evidence rules, so here is the tool output "
                f"unedited:\n{body}\n\nSettlements without enough measurement are 'evidence "
                f"needed', not underserved. {T.LOW_EV_WARNING} Any modelled estimate is an "
                f"estimate, not a measurement, and any cost is illustrative. {T.DISCLAIMER}")
        return {"messages": [AIMessage(safe)], "violations": [], "rewrites": n}
    fix = ("Your draft broke these rules:\n- " + "\n- ".join(state["violations"]) +
           "\n\nRewrite it fixing ONLY these. Change no numbers.")
    llm = _llm()
    out = llm.invoke([SystemMessage(SYSTEM), *state["messages"], HumanMessage(fix)])
    return {"messages": [out], "rewrites": n}


def route_agent(state: TDState):
    last = state["messages"][-1]
    return "tools" if getattr(last, "tool_calls", None) else "check"


def route_check(state: TDState):
    return "rewrite" if state.get("violations") else "ok"


def route_rewrite(state: TDState):
    """Once the cap is spent the answer is terminal. Sending it back through
    evidence_check would let a rule the safe text cannot satisfy bounce it
    forever, which surfaced to the user as a GraphRecursionError rather than an
    answer."""
    return "done" if state.get("rewrites", 0) > MAX_REWRITES else "check"


def build():
    g = StateGraph(TDState)
    g.add_node("agent", agent_node)
    g.add_node("tools", tools_node)
    g.add_node("evidence_check", evidence_check_node)
    g.add_node("rewrite", rewrite_node)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route_agent, {"tools": "tools", "check": "evidence_check"})
    g.add_edge("tools", "agent")
    g.add_conditional_edges("evidence_check", route_check,
                            {"rewrite": "rewrite", "ok": END})
    g.add_conditional_edges("rewrite", route_rewrite,
                            {"check": "evidence_check", "done": END})
    # In-process conversation memory, keyed by thread_id. A follow-up like "why
    # is that one ranked first?" needs the previous turn to resolve "that one".
    return g.compile(checkpointer=MemorySaver())


GRAPH = None


def _graph():
    global GRAPH
    if GRAPH is None:
        GRAPH = build()
    return GRAPH


def _config(session_id: str | None):
    """One LangGraph thread per chat panel. Without a session the turn is
    isolated, which is the old stateless behaviour."""
    return {"configurable": {"thread_id": session_id or "stateless"},
            "recursion_limit": 30}


def _trace_url(run_id) -> str:
    """The dashboard has always rendered a "View the trace" link if we send one.
    Until now nothing ever did."""
    if not run_id or not TRACING:
        return ""
    project = os.getenv("LANGSMITH_PROJECT", "").strip()
    return (f"https://smith.langchain.com/o/-/projects/p/{project}/r/{run_id}"
            if project else f"https://smith.langchain.com/public/{run_id}/r")


def _payload(state: dict, trace_url: str = "") -> dict:
    """The dashboard contract, built from TOOL OUTPUT rather than the model's text."""
    answer = state["messages"][-1].content or ""
    outs = state.get("tool_outputs") or []
    # map ids and the table come from TOOL OUTPUT, never from the model's text.
    ids, table, notes = [], [], []
    for o in outs:
        r = o.get("result") or {}
        ids += [i for i in (r.get("ids") or []) if i not in ids]
        if r.get("note"):
            notes.append(str(r["note"]))
        if not table and r.get("rows"):
            table = r["rows"]

    # response_type drives the mascot. Derived from what the TOOLS returned, so
    # the character reacts to the data rather than to the model's tone.
    joined = " ".join(notes).lower()
    if any(w in joined for w in ("evidence needed", "not scored", "has not shipped",
                                "no settlement matches", "insufficient")):
        rtype = "no_evidence"
    elif not outs:
        rtype = "refusal"          # answered from the rules without calling a tool
    elif ids:
        rtype = "location"         # something to point at on the map
    elif table:
        rtype = "answer"
    else:
        rtype = "no_evidence"

    out = {"answer": answer, "table": table,
           "map": {"action": "select" if len(ids) == 1 else "highlight", "ids": ids},
           "tools_used": [o["tool"] for o in outs],
           "response_type": rtype,
           "notes": notes,
           "rewrites": state.get("rewrites", 0)}
    if trace_url:
        out["trace_url"] = trace_url
    return out


def ask(question: str, session_id: str | None = None) -> dict:
    """Run one turn. Returns the dashboard contract: answer, table, map.ids."""
    from langchain_core.tracers.context import collect_runs
    with collect_runs() as cb:
        state = _graph().invoke({"messages": [HumanMessage(question)],
                                 "tool_outputs": [], "violations": [], "rewrites": 0},
                                config=_config(session_id))
        run_id = cb.traced_runs[0].id if cb.traced_runs else None
    return _payload(state, _trace_url(run_id))


# ── streaming ────────────────────────────────────────────────────────────────
# The status line used to show one fixed sentence for the whole wait. These are
# the graph's ACTUAL node transitions, so what the user reads is what is
# happening — not a scripted progress animation.
STEP_LABEL = {
    "agent": "Reading the question and choosing tools",
    "tools": "Running tools over the dataset",
    "evidence_check": "Checking the draft against the tool output",
    "rewrite": "Rewriting to satisfy the evidence rules",
}


def ask_stream(question: str, session_id: str | None = None):
    """Yield (event, data) as the graph runs, then one final ('done', payload).

    Errors are yielded as an event too, never raised into the SSE body, so the
    dashboard always receives a terminal message.
    """
    try:
        state = {"messages": [HumanMessage(question)],
                 "tool_outputs": [], "violations": [], "rewrites": 0}
        last = None
        for update in _graph().stream(state, config=_config(session_id),
                                      stream_mode="updates"):
            for node, delta in update.items():
                yield "step", _describe(node, delta)
                last = delta
        final = _graph().get_state(_config(session_id)).values if session_id else None
        yield "done", _payload(final or _merge(state, last))
    except Exception as e:                       # a stream must still terminate
        yield "error", {"message": str(e)}


def _merge(base: dict, last: dict | None) -> dict:
    """Reconstruct enough final state for _payload when no checkpoint exists."""
    out = dict(base)
    if last:
        out.update({k: v for k, v in last.items() if k != "messages"})
        out["messages"] = list(last.get("messages") or base["messages"])
    return out


def _describe(node: str, delta: dict) -> dict:
    """Turn a node update into a sentence a planner would understand."""
    label = STEP_LABEL.get(node, node)
    detail = ""
    if node == "agent":
        msg = (delta.get("messages") or [None])[-1]
        calls = getattr(msg, "tool_calls", None) or []
        if calls:
            label = "Choosing tools"
            detail = ", ".join(c["name"] for c in calls)
        else:
            label = "Writing the answer"
    elif node == "tools":
        outs = delta.get("tool_outputs") or []
        if outs:
            o = outs[-1]
            n = len((o.get("result") or {}).get("rows") or [])
            label = f"Ran {o['tool']}"
            detail = f"{n} row{'' if n == 1 else 's'}"
    elif node == "evidence_check":
        v = delta.get("violations") or []
        label = "Evidence check"
        detail = "passed" if not v else f"{len(v)} issue{'' if len(v) == 1 else 's'}: {v[0][:70]}"
    elif node == "rewrite":
        label = f"Rewrite {delta.get('rewrites', 1)} of {MAX_REWRITES}"
    return {"node": node, "label": label, "detail": detail}
