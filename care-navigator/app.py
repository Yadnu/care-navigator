"""Care Navigator Streamlit app with a trace viewer.

    streamlit run app.py
"""
from __future__ import annotations

from datetime import date, datetime, time

import streamlit as st

from navigator import config
from navigator.care_engine import LABELS
from navigator.data import load_plans, load_zips
from navigator.models import Outcome, Request
from navigator.pipeline import Navigator, NavigatorResult

TIME_PRESETS = {
    "Now": None,
    "Weekday 14:00 (Tue 3 Nov 2026)": datetime(2026, 11, 3, 14, 0),
    "Weekday 22:30 (Tue 3 Nov 2026)": datetime(2026, 11, 3, 22, 30),
    "Midnight 00:15 (Wed 4 Nov 2026)": datetime(2026, 11, 4, 0, 15),
    "Saturday 10:00 (7 Nov 2026)": datetime(2026, 11, 7, 10, 0),
    "Sunday 15:00 (8 Nov 2026)": datetime(2026, 11, 8, 15, 0),
    "Custom": None,
}


@st.cache_resource
def get_navigator() -> Navigator:
    config.load_env_file()
    return Navigator.from_env()


def md(text: str) -> str:
    """Escape dollar signs so Streamlit doesn't render prices as LaTeX."""
    return text.replace("$", "\\$")


def label(level) -> str:
    text = LABELS[level]
    return text[0].upper() + text[1:]


def show_options(title: str, options) -> None:
    if not options:
        return
    st.subheader(title)
    for o in options:
        p, m = o.match.practitioner, o.match
        where = "Online visit" if p.virtual else f"{m.distance_km:g} km away, {p.address}"
        who = f"**{p.facility_name}**" + ("" if p.name == p.facility_name else f" ({p.name})")
        st.markdown(md(f"{who}  \n{where} | {p.phone} | "
                       f"languages: {', '.join(p.languages)}  \nMatched: _{m.matched_text}_  \n"
                       f"{o.cost.summary()}"))


def show_result(result: NavigatorResult) -> None:
    for error in result.errors:
        st.warning(error)
    if result.outcome is None:
        return
    if result.outcome is Outcome.EMERGENCY:
        st.error(f"**{result.message}**")
        st.markdown(f"Emergency numbers: {', '.join(result.resources)}. This request stops here.")
    elif result.outcome is Outcome.FOLLOW_UP:
        st.info(result.question)
        st.text_input("Your answer (we only ask once)", key="followup_answer")
        st.button("Send answer", key="submit_followup")
    else:
        rec = result.recommendation
        st.success(f"Recommended level of care: {label(rec.decision.level)}.")
        st.markdown(md(rec.explanation))
        for note in rec.notes:
            st.warning(md(note))
        show_options("In-network options open now", rec.options)
        show_options("Online alternatives", rec.alternatives)
        if rec.nurse_line:
            st.markdown(f"Your plan's nurse line: **{rec.nurse_line}**")
        d = rec.decision
        st.caption(f"Decided by rule {d.rule_id} (care rules v{d.rules_version})"
                   f"{'; moved up one level because some details were unclear' if d.escalated else ''}.")
    if result.simplified:
        st.warning("Simplified answer: a live provider failed or timed out, so the offline version answered.")

    with st.expander(f"Trace viewer ({len(result.trace)} steps)"):
        if result.trace_path:
            st.caption(f"Saved to {result.trace_path}")
        for step in result.trace:
            tokens = f" | {step.tokens} tokens" if step.tokens else ""
            st.markdown(md(f"**{step.name}** | {step.used} | {step.latency_ms:.0f} ms{tokens}"))
            st.text(f"in:  {step.input[:500]}\nout: {step.output[:1000]}")


def request_time(choice: str) -> datetime:
    if choice == "Now":
        return datetime.now().replace(second=0, microsecond=0)
    if choice == "Custom":
        d = st.session_state.get("custom_date", date.today())
        t = st.session_state.get("custom_time", time(14, 0))
        return datetime.combine(d, t)
    return TIME_PRESETS[choice]


def main() -> None:
    st.set_page_config(page_title="Care Navigator", page_icon=":compass:")
    nav = get_navigator()
    st.title("Care Navigator")
    st.info(f"Mode: {nav.mode}")
    st.caption("Synthetic data only: every practitioner, plan and zip code is fictional. "
               "This is a prototype and not medical advice. In an emergency, call 911.")

    plans = {p["id"]: p["name"] for p in load_plans()}
    zips = {z["zip"]: z["neighborhood"] for z in load_zips()}

    st.text_area("Describe your symptoms in your own words", key="symptoms", max_chars=config.MAX_TEXT_CHARS)
    st.slider("How bad is it? (1 = barely noticeable, 10 = worst imaginable)", 1, 10, 4, key="severity")
    col1, col2 = st.columns(2)
    zip_choice = col1.selectbox("Zip code", [*zips, "Other"], key="zip",
                                format_func=lambda z: f"{z} ({zips[z]})" if z in zips else "Other (type it)")
    if zip_choice == "Other":
        col1.text_input("Zip code", key="zip_other")
    col2.selectbox("Insurance plan", list(plans), key="plan", format_func=lambda p: plans[p])
    col1.radio("Who is this for?", ["adult", "child"], key="age_group", horizontal=True)
    when_choice = col2.selectbox("Time of request", list(TIME_PRESETS), key="when")
    if when_choice == "Custom":
        col2.date_input("Date", key="custom_date")
        col2.time_input("Time", key="custom_time")

    if st.button("Find care", key="submit", type="primary"):
        st.session_state["last_request"] = dict(
            text=st.session_state.get("symptoms", ""),
            severity=st.session_state["severity"],
            zip=(st.session_state.get("zip_other") or "").strip() if zip_choice == "Other" else zip_choice,
            plan=st.session_state["plan"],
            request_time=request_time(when_choice),
            age_group=st.session_state["age_group"],
        )
        st.session_state["result"] = nav.run(Request(**st.session_state["last_request"]))
    elif st.session_state.get("submit_followup") and st.session_state.get("last_request"):
        answer = st.session_state.get("followup_answer", "")
        st.session_state["result"] = nav.run(Request(**st.session_state["last_request"], followup_answer=answer))

    if st.session_state.get("result"):
        show_result(st.session_state["result"])


main()
