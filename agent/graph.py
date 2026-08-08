"""Tanya Dino: LangGraph state machine over the grounded tools.

    agent → tools → evidence_check → (rewrite, capped) → respond

The point of the graph is the evidence_check node: it is plain Python, it sees
the RAW tool rows rather than the model's prose, and the model cannot reach the
user without passing it. If the draft breaks an evidence rule, the answer is
sent back to be rewritten with the violations named, and after two attempts a
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
- Call the tool again for every question about a named settlement, district or facility,
  even when the answer appeared earlier in this conversation and even when the question is
  a repeat. The evidence check only sees tools called in THIS turn and deletes any figure
  you did not fetch in it, so answering from memory loses the number.
- If the user asserts a figure, do not agree with it or repeat it until a tool has returned
  it. Look it up and state what the data says, even if that contradicts them.
- Ranking is the Digital Inclusion Priority Index (DIPI), a transparent weighted blend:
  connectivity need 40%, population at stake 25%, institutions served 15%, equity 20%.
  It screens communities for FURTHER ASSESSMENT.
- Respect evidence tiers exactly. "insufficient" means say "evidence needed", never
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
    """Everything known about one settlement: its measured download, upload, latency and
    how many tests back them, the four pillar scores and their weights, and its terrain
    reading (elevation, height within its district, metres above or below the nearest
    town) which helps explain a slow link but never affects the score.
    Use this for "what speed does X get", "is X really N Mbps" and "why is X ranked there".
    A LOW connectivity pillar means low NEED, i.e. the place is already fast."""
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
    """Suggested connectivity option and the rules that fired, including any terrain
    caveat. Illustrative criteria."""
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
    """Compare districts: settlements, evidence gap, median speed, median elevation, how
    many sit below their nearest town, and how many schools and health points are inside
    each one. Use this for "which district has the most schools / hospitals / settlements /
    evidence gap", or "which district is the most mountainous". Sort by facilities, schools,
    health, settlements, evidence_gap, priority, elevation or terrain."""
    return T.district_summary(district, sort_by, top_k)


@tool
def list_facilities(district: str = "", kind: str = "", limit: int = 50,
                    sort_by: str = "name") -> dict:
    """The actual NAMES of schools and health points, each with the nearest settlement
    that has a speed measurement and what it reads. Use this to list or name facilities,
    and to answer which schools or clinics sit in the best or worst connected places.
    kind: school, health, hospital, clinic, doctors, or empty for all.
    sort_by: name, fastest, or slowest."""
    return T.list_facilities(district, kind, limit, sort_by)


@tool
def compare_areas(names: str, level: str = "district") -> dict:
    """Compare two to four DISTRICTS or DIVISIONS side by side on identical definitions:
    median speed and latency, the share of settlements below 360p for a class of 30, people
    in those areas, how much of each is measured, remoteness, terrain, schools and health
    points, and where each sits against the other 25 districts. Use this for "compare A and
    B", "A vs B", "which district should we prioritise", "is A worse than B".
    names: the areas, e.g. "Ranau, Kudat" or "Ranau vs Kota Kinabalu".
    level: district (default) or division.
    Every figure is a rate or a median, never a raw total, so a large district does not win
    by being large. The result carries its own written summary in `summary`."""
    return T.compare_areas(names, level)


@tool
def find_failing_schools(district: str = "", division: str = "", users: int = 30,
                         tier: str = "360p", top_k: int = 25) -> dict:
    """Settlements with a school within 3 km whose MEASURED link cannot carry a class of
    `users` at `tier`. Use this for "which schools are worst off", "where can a classroom
    not stream", "how many schools fall below 360p" and anything about schools and speed
    together. Tiers: 360p, 480p, 720p, 1080p, 4k. Settlements with no measurement are
    excluded rather than counted as failing."""
    return T.find_failing_schools(district, division, users, tier, top_k)


@tool
def rank_bundles(budget_rm: float = 50_000_000, scenario: str = "balanced",
                 cost_scenario: str = "base", top_k: int = 25) -> dict:
    """Which groups of fibre settlements a budget funds, and in what order. Use this for
    "what should we build first", "what does RM 50 million buy", "which corridor / bundle
    / area should we deploy to", and anything about ORDER of deployment rather than one
    settlement. A bundle is settlements close enough to screen as one shared build.
    scenario: need (most urgent first, cost ignored), balanced (urgency per ringgit, the
    default), or reach (most settlements and institutions per ringgit).
    cost_scenario: low, base or high, the same catalogue optimise_budget uses.
    Fibre only. Tower, satellite and community Wi-Fi are per-site builds with nothing to
    share, so they are not bundled."""
    return T.rank_bundles(budget_rm, scenario, cost_scenario, top_k)


@tool
def explain_bundle(name_or_id: str) -> dict:
    """Which deployment bundle one settlement belongs to, and what else would be built
    with it. Use this for "would X be built with anything else", "what is in X's bundle",
    "is X part of a shared build". Answers honestly when a settlement is in no bundle."""
    return T.explain_bundle(name_or_id)


TOOL_LIST = [rank_settlements, explain_priority, compare_settlements, simulate_experience,
             predict_coverage, recommend_intervention, optimise_budget, plan_survey,
             generate_validation_report, district_summary, list_facilities, compare_areas,
             find_failing_schools, rank_bundles, explain_bundle]


class TDState(TypedDict):
    messages: Annotated[list, add_messages]
    tool_outputs: list
    violations: list
    rewrites: int
    # The District Decision Comparison currently on the user's screen, if any.
    # Recomputed here in Python from the area NAMES the dashboard sends, the
    # dashboard never sends its numbers, so a client cannot feed the model a
    # figure and have the guardrail bless it as data.
    context: dict


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


def _window(msgs: list) -> list:
    """The last MAX_HISTORY messages, cut on a turn boundary.

    A blind [-MAX_HISTORY:] slice cuts wherever it lands. From the FOURTH
    question of a session onward it landed between an AIMessage carrying
    tool_calls and the ToolMessage answering it, so the window opened on a
    dangling function call and Gemini rejected the whole turn:

        400 INVALID_ARGUMENT, Please ensure that function call turn comes
        immediately after a user turn or after a function response turn.

    which surfaced to the user as "Copilot offline" on question four, every
    session, forever. Only a HumanMessage is a safe place to open a window: a
    tool call and its response are then always inside it together.
    """
    starts = [i for i, m in enumerate(msgs) if isinstance(m, HumanMessage)]
    if len(msgs) > MAX_HISTORY and starts:
        cut = len(msgs) - MAX_HISTORY
        # The oldest turn that still fits; failing that the current turn, even
        # if a long tool loop makes it overrun the budget. Correct beats short.
        msgs = msgs[next((i for i in starts if i >= cut), starts[-1]):]
    elif len(msgs) > MAX_HISTORY:
        msgs = msgs[-MAX_HISTORY:]
    # Belt and braces: never send a tool call whose response is not also in the
    # window. Nothing in the graph produces one today, rewrite_node calls the
    # model unbound, so it cannot emit a call that never runs, but this is the
    # shape Gemini rejects outright, and it is one line to make impossible.
    answered = {getattr(m, "tool_call_id", None) for m in msgs}
    return [m for m in msgs
            if all(c["id"] in answered for c in (getattr(m, "tool_calls", None) or []))]


# ── the comparison the user is looking at ────────────────────────────────────
# The dashboard's "Ask Tanya Dino about this" button sends the SELECTION, never
# the numbers. compare_areas() then recomputes them here, so what the model is
# handed is the same deterministic output that drew the table rather than
# anything a client asserted. The fixed-rule summary travels with it and is
# never edited: the model reasons ON it, it does not replace it.
CONTEXT_KEYS = ("areas", "level", "stats", "sabah", "indicators", "summary",
                "note", "unavailable", "flags")


def seed_comparison(level: str, areas) -> dict:
    """Recompute the on-screen comparison, trimmed to what a reader needs.

    `rows` is dropped because it mirrors `indicators`, and `ids` because at
    twenty-five districts it is 1,114 settlement ids that would both bloat the
    prompt and ring the entire map for a question about districts.
    """
    if not areas or len(areas) < 2:
        return {}
    out = T.compare_areas(list(areas), level or "district")
    if not out.get("indicators"):
        return {}
    return {k: out[k] for k in CONTEXT_KEYS if k in out}


def seed_bundles(budget_rm, scenario: str) -> dict:
    """Recompute the deployment portfolio the user is looking at.

    Same shape of contract as seed_comparison: the dashboard sends the SETTINGS,
    never the figures, and rank_bundles recomputes them here. `ids` is dropped
    because two hundred settlement ids would bloat the prompt for a question
    about bundles, and `rows` keeps only the funded ones.
    """
    try:
        budget = float(budget_rm)
    except (TypeError, ValueError):
        return {}
    out = T.rank_bundles(budget, scenario or "balanced")
    if not out.get("rows"):
        return {}
    keep = ("bundles_total", "bundles_funded", "settlements_funded", "schools_funded",
            "clinics_funded", "spent_rm", "budget_rm", "cost_all_rm", "scenario",
            "ranked_by", "flags", "label", "note")
    ctx = {k: out[k] for k in keep if k in out}
    ctx["rows"] = [r for r in out["rows"] if r.get("funded")]
    return ctx


def _context_message(ctx: dict) -> SystemMessage:
    if "bundles_total" in ctx:
        return SystemMessage(
            "The user is looking at the Deployment bundles panel. The JSON below is the "
            "EXACT set of figures on their screen, computed in Python by the same code "
            "that drew the panel:\n"
            + json.dumps(ctx, default=str)
            + "\n\nAnswer from THESE numbers. `rows` is only the FUNDED bundles; "
            "`bundles_total` counts all of them. Costs are illustrative benchmarks, and a "
            "bundle is settlements grouped by position as a screening proxy for a shared "
            "build, never an engineering design or a surveyed route: say so rather than "
            "implying the route exists. You may still call tools for anything this object "
            "does not contain, such as one named settlement.")
    names = ", ".join(ctx.get("areas") or [])
    return SystemMessage(
        f"The user is looking at the District Decision Comparison for {names}. The JSON "
        "below is the EXACT set of figures on their screen, computed in Python by the "
        "same code that drew the table:\n"
        + json.dumps(ctx, default=str)
        + "\n\nAnswer from THESE numbers. Do not recompute them, do not round them "
        "differently, and do not introduce a figure that is neither in this object nor "
        "in a tool result. `summary` is the fixed-rule text already printed on their "
        "sheet, never restate it and never contradict it; add the reasoning it cannot "
        "give, such as which of two areas to fund first and why, or what a field team "
        "should collect. `percentile_worse_than` is the rank against every area in "
        "Sabah, where a HIGHER number is worse. You may still call tools for anything "
        "this object does not contain, such as one named settlement.")


def agent_node(state: TDState):
    # The comparison rides in front of the window rather than inside the
    # history, so it survives MAX_HISTORY trimming: a follow-up on the eighth
    # question still sees the same figures the first one did.
    ctx = state.get("context") or {}
    head = [SystemMessage(SYSTEM)] + ([_context_message(ctx)] if ctx else [])
    return {"messages": [_llm(bound=True).invoke(head + _window(state["messages"]))]}


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
            # A list of strings joins rather than collapsing to its first item.
            # T._s(["Ranau", "Kudat"]) returns "Ranau", so a two-district
            # comparison quietly became a one-district one.
            v = (", ".join(str(x).strip() for x in v if str(x).strip())
                 if isinstance(v, (list, tuple)) and all(isinstance(x, str) for x in v)
                 else T._s(v))
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


def _text(msg) -> str:
    """A message's content as a plain string.

    Gemini does not always return content as a string. It can return a list of
    parts, and everything downstream assumed a string: the guardrail called
    .lower() on it and killed the turn with "'list' object has no attribute
    'lower'", and on the paths that did not crash the raw part list went to the
    user as the answer. Flatten it once, here, so neither can happen.
    """
    c = getattr(msg, "content", msg)
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        parts = []
        for part in c:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                t = part.get("text") or part.get("content")
                if isinstance(t, str):
                    parts.append(t)
        return " ".join(parts).strip()
    return "" if c is None else str(c)


# A number a planner would read as a measurement: anything with a decimal
# point, or an integer of four digits or more (populations, budgets). Small
# integers are deliberately skipped, "top 10", "a class of 30", "40% of DIPI"
# are structure, not data, and flagging them would be all false positives.
DATA_NUMBER = re.compile(r"\d[\d,]*\.\d+|\d[\d,]{3,}")
# ...and a bare four-digit number in this range is a year, not a population.
YEAR = re.compile(r"^(19|20)\d\d$")


def _data_numbers(text: str) -> set:
    return {n for n in (m.group(0).replace(",", "") for m in DATA_NUMBER.finditer(text))
            if not YEAR.match(n)}


def _tool_numbers(outputs: list) -> set:
    """Every number the tools returned, in the forms a model would write them."""
    allowed = set()
    for o in outputs:
        blob = json.dumps(o.get("result") or {}, default=str)
        for m in re.finditer(r"\d+(?:\.\d+)?", blob):
            allowed.add(m.group(0))
            try:
                f = abs(float(m.group(0)))
            except ValueError:
                continue
            # Every scale a model might write it at, so "RM 2.5 million" is
            # recognised as the 2500000 the tool returned rather than reported
            # as invented.
            for scale in (1, 1e3, 1e6, 1e9):
                for dp in (0, 1, 2):
                    s = f"{f / scale:.{dp}f}"
                    allowed.add(s)
                    allowed.add(s.rstrip("0").rstrip(".") or "0")
    return allowed


def _scan(draft: str, outputs: list) -> list:
    """The guardrail. Pure Python, reading raw tool rows, not the model's word for it.

    Detection keys off the machine-readable `flags` a tool returns. It used to
    key off the prose in `label` and `note`, which meant rewording a sentence in
    tools.py could silently disarm a rule. The prose checks are kept as a
    fallback so an un-flagged tool still trips the right wire.
    """
    v = []
    ids_insufficient = []
    has_low = has_modelled = has_illustrative = has_sharing = has_bundle = False
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
        # criteria", so rule-based advice was never required to say so.
        if flags & {"illustrative_cost", "illustrative_rules"} \
                or str(r.get("label", "")).lower().startswith("illustrative"):
            has_illustrative = True
        if "modelled" in flags or "modelled estimate" in str(r.get("note", "")).lower():
            has_modelled = True
        if "assumption_equal_sharing" in flags:
            has_sharing = True
        # Bundles are a proximity screen, not an engineering design, and the
        # difference is the whole claim. Without this an answer could say "build
        # the Tenom corridor" as though a route had been surveyed.
        if "bundle_proxy" in flags:
            has_bundle = True
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
    # "Python computes, the agent narrates", enforced rather than requested.
    # The system prompt already forbids inventing a number, and the model
    # ignored it: asked why a settlement was not picked, it restated a speed
    # the USER had asserted in the question as if it were data, and no tool had
    # ever returned that figure for that place. A prompt is not a control.
    invented = sorted(_data_numbers(draft) - _tool_numbers(outputs))
    if invented:
        v.append("These figures appear in the answer but in no tool result: "
                 + ", ".join(invented[:4])
                 + ". Every number must come from a tool. Remove them, or say the data does "
                   "not contain that figure. Never repeat a number the user supplied as if "
                   "the dataset confirmed it.")

    # The disclaimer is appended to EVERY answer and begins "Screening for
    # further assessment", so a keyword like "screen" is satisfied before the
    # model has written a word. Check the body with the disclaimer removed.
    _body = draft.lower().replace(T.DISCLAIMER.rstrip(".").lower(), " ")
    if has_bundle and not re.search(
            r"proxy|grouped|screened as|not a design|not an engineering|shared build", _body):
        v.append("A deployment bundle is quoted without saying what it is. Bundles are "
                 "settlements grouped by position as a SCREENING proxy for a shared build, "
                 "not an engineering design or a surveyed route. Say so.")

    if T.DISCLAIMER.rstrip(".").lower() not in draft.lower():
        v.append(f"The closing disclaimer is missing: {T.DISCLAIMER}")
    return v


def _all_outputs(state: TDState) -> list:
    """Tool results, plus the on-screen comparison if one is attached.

    The comparison is Python output exactly like a tool result, so its figures
    are data and the number guardrail must not report them as invented.
    """
    outs = list(state.get("tool_outputs") or [])
    ctx = state.get("context") or {}
    if ctx:
        outs = outs + [{"tool": "comparison_context", "result": ctx}]
    return outs


def evidence_check_node(state: TDState):
    draft = _text(state["messages"][-1])
    return {"violations": _scan(draft, _all_outputs(state))}


def rewrite_node(state: TDState):
    n = state.get("rewrites", 0) + 1
    if n > MAX_REWRITES:
        # Hard-templated safe answer. The model does not get a third attempt.
        # It carries EVERY caveat _scan can ask for, because this text is the
        # terminal state, if it tripped a rule of its own there would be
        # nothing left to rewrite it into.
        rows = [o for o in _all_outputs(state) if (o.get("result") or {}).get("rows")]
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
    # Same window as agent_node. This used to send the entire history, which
    # both grew without bound and could carry the same dangling call.
    ctx = state.get("context") or {}
    out = llm.invoke([SystemMessage(SYSTEM), *([_context_message(ctx)] if ctx else []),
                      *_window(state["messages"]), HumanMessage(fix)])
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
    answer = _text(state["messages"][-1])
    outs = state.get("tool_outputs") or []
    ctx = state.get("context") or {}
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
    elif ctx and not outs:
        # Reasoning over the on-screen comparison IS a grounded answer. Without
        # this it fell to "refusal" and the mascot looked baffled by a question
        # it had just answered from real figures.
        rtype = "answer"
    elif not outs:
        rtype = "refusal"          # answered from the rules without calling a tool
    elif ids:
        rtype = "location"         # something to point at on the map
    elif table:
        rtype = "answer"
    else:
        rtype = "no_evidence"

    used = [o["tool"] for o in outs]
    if ctx:
        # Shown in the chat's "what actually ran" list, so the grounding is
        # visible rather than implied.
        used = [f"comparison on screen ({len(ctx.get('areas') or [])} "
                f"{ctx.get('level', 'district')}s)"] + used
    out = {"answer": answer, "table": table,
           "map": {"action": "select" if len(ids) == 1 else "highlight", "ids": ids},
           "tools_used": used,
           "grounded_in_comparison": bool(ctx) and "areas" in ctx,
           "grounded_in_bundles": bool(ctx) and "bundles_total" in ctx,
           "response_type": rtype,
           "notes": notes,
           "rewrites": state.get("rewrites", 0)}
    if trace_url:
        out["trace_url"] = trace_url
    return out


def _initial(question: str, context) -> dict:
    """The turn's starting state. `context` is {level, areas} from the dashboard;
    the figures are recomputed here rather than accepted from the client."""
    ctx = {}
    if isinstance(context, dict):
        if context.get("areas"):
            ctx = seed_comparison(context.get("level", "district"), context.get("areas"))
        elif context.get("budget_rm"):
            ctx = seed_bundles(context.get("budget_rm"), context.get("scenario", ""))
    return {"messages": [HumanMessage(question)], "tool_outputs": [],
            "violations": [], "rewrites": 0, "context": ctx}


def ask(question: str, session_id: str | None = None, context=None) -> dict:
    """Run one turn. Returns the dashboard contract: answer, table, map.ids."""
    from langchain_core.tracers.context import collect_runs
    with collect_runs() as cb:
        state = _graph().invoke(_initial(question, context),
                                config=_config(session_id))
        run_id = cb.traced_runs[0].id if cb.traced_runs else None
    return _payload(state, _trace_url(run_id))


# ── streaming ────────────────────────────────────────────────────────────────
# The status line used to show one fixed sentence for the whole wait. These are
# the graph's ACTUAL node transitions, so what the user reads is what is
# happening, not a scripted progress animation.
STEP_LABEL = {
    "agent": "Reading the question and choosing tools",
    "tools": "Running tools over the dataset",
    "evidence_check": "Checking the draft against the tool output",
    "rewrite": "Rewriting to satisfy the evidence rules",
}


def ask_stream(question: str, session_id: str | None = None, context=None):
    """Yield (event, data) as the graph runs, then one final ('done', payload).

    Errors are yielded as an event too, never raised into the SSE body, so the
    dashboard always receives a terminal message.
    """
    try:
        state = _initial(question, context)
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
