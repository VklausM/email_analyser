import json, io, tempfile, streamlit as st, pandas as pd
from pathlib import Path
from db import init_db, clear_data, get_results, get_manual_review_emails, record_feedback, set_config, get_meta
from pipeline.graph import EmailPipeline
from config import settings

st.set_page_config(page_title="BFSI Email Analyser", page_icon="🔍", layout="wide")
init_db()

st.markdown("<style>@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');html, body, [class*='css'] { font-family: 'Inter', sans-serif; }.stApp { background-color: #0f1117; }[data-testid='metric-container'] { background: linear-gradient(135deg, #1e2130 0%, #252840 100%); border: 1px solid #2d3250; border-radius: 12px; padding: 16px 20px; }[data-testid='metric-container'] label { color: #8b92b3 !important; font-size: 0.8rem !important; }[data-testid='metric-container'] [data-testid='metric-value'] { color: #ffffff !important; font-size: 1.6rem !important; font-weight: 700 !important; }.stTabs [data-baseweb='tab-list'] { background: #1a1d2e; border-radius: 10px; gap: 4px; padding: 4px; }.stTabs [data-baseweb='tab'] { border-radius: 8px; color: #8b92b3; font-weight: 500; padding: 8px 20px; }.stTabs [aria-selected='true'] { background: #4f6ef7 !important; color: white !important; }.badge { display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; }.badge-critical { background: #ff4d4d22; color: #ff4d4d; border: 1px solid #ff4d4d44; }.badge-high { background: #ff8c0022; color: #ff8c00; border: 1px solid #ff8c0044; }.badge-medium { background: #ffd70022; color: #ffd700; border: 1px solid #ffd70044; }.badge-low { background: #00e67622; color: #00e676; border: 1px solid #00e67644; }.email-card { background: #1a1d2e; border: 1px solid #2d3250; border-radius: 12px; padding: 16px 20px; margin-bottom: 10px; }.email-card:hover { border-color: #4f6ef7; }.evidence-block { background: #12141f; border-left: 3px solid #4f6ef7; border-radius: 0 8px 8px 0; padding: 10px 14px; margin: 6px 0; font-size: 0.85rem; }[data-testid='stSidebar'] { background-color: #13151f; border-right: 1px solid #2d3250; }.stButton > button { border-radius: 8px; font-weight: 500; transition: all 0.2s; }.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(79,110,247,0.3); }.score-bar-wrap { background: #252840; border-radius: 20px; height: 8px; width: 100%; }.score-bar-fill { height: 8px; border-radius: 20px; }</style>", unsafe_allow_html=True)

COLORS = {"critical": "#ff4d4d", "high": "#ff8c00", "medium": "#ffd700", "low": "#00e676"}
def badge(l): return f'<span class="badge badge-{l}">{l.upper()}</span>'
def score_bar(s, l):
    c = COLORS.get(l, "#4f6ef7")
    return f'<div class="score-bar-wrap"><div class="score-bar-fill" style="width:{s}%; background:{c};"></div></div>'

def sidebar():
    with st.sidebar:
        st.markdown("## 🔍 Email Analyser\nBFSI Compliance")
        st.markdown("---")
        fn = get_meta("filename")
        if fn: st.success(f"Current: **{fn}**")
        st.markdown("---")

def tab_upload():
    st.markdown("### Upload & Analyze")
    up = st.file_uploader("Choose file", type=["xlsx", "xls", "csv"])
    if up and st.button("▶ Run Analysis", type="primary"):
        clear_data()
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(up.name).suffix) as tmp:
            tmp.write(up.read())
            path = tmp.name
        try:
            with st.status("Initializing analysis pipeline...", expanded=True) as s:
                from db import set_meta
                set_meta("filename", up.name)
                s.write("📂 Loading and preprocessing emails...")
                pipeline = EmailPipeline()
                s.write("🤖 Running LLM Analysis and Risk Scoring...")
                pipeline.run(path)
                s.update(label="Analysis complete!", state="complete")
            st.rerun()
        except Exception as e:
            st.error(f"Analysis failed: {str(e)}")
            import traceback
            st.code(traceback.format_exc())

def tab_dashboard():
    st.markdown("### Dashboard")
    res = get_results()
    if not res: return st.info("No data. Upload a file.")
    stats = {"total": len(res), "critical": sum(1 for r in res if r["criticality_level"]=="critical"), "high": sum(1 for r in res if r["criticality_level"]=="high"), "medium": sum(1 for r in res if r["criticality_level"]=="medium"), "low": sum(1 for r in res if r["criticality_level"]=="low"), "manual": sum(1 for r in res if r["manual_review_required"])}
    cols = st.columns(6)
    for i, (k, v) in enumerate(stats.items()): cols[i].metric(k.title(), v)
    st.markdown("---")
    st.bar_chart(pd.DataFrame({"Level": ["Critical", "High", "Medium", "Normal"], "Count": [stats["critical"], stats["high"], stats["medium"], stats["low"]]}).set_index("Level"))

def tab_ranked():
    st.markdown("### Ranked Emails")
    res = get_results()
    if not res: return st.info("Upload a file.")
    lvl = st.multiselect("Filter", ["critical", "high", "medium", "low"], default=["critical", "high", "medium", "low"])
    for r in [r for r in res if r["criticality_level"] in lvl]:
        cls, tags, ev = json.loads(r["classifications"] or "[]"), json.loads(r["tags"] or "[]"), json.loads(r["evidence_lines"] or "[]")
        with st.expander(f"#{r['rank']} {r['subject']} — {r['from_addr']} (Score: {r['risk_score']})"):
            c1, c2 = st.columns([2, 1])
            with c1:
                st.markdown(f"{badge(r['criticality_level'])} {' '.join([f'`{c}`' for c in cls])}", unsafe_allow_html=True)
                st.markdown(score_bar(r["risk_score"], r["criticality_level"]), unsafe_allow_html=True)
                if tags: st.markdown("**Tags:** " + " ".join([f"`{t}`" for t in tags]))
                st.markdown(f"**Reasoning:**\n> {r['reasoning']}")
                for e in ev:
                    col = COLORS.get(e.get("risk_level", "low"), "#4f6ef7")
                    st.markdown(f'<div class="evidence-block" style="border-left-color:{col}"><b>Line {e.get("line_number")}</b>: {e.get("reason")}<br><i>"{e.get("text")}"</i></div>', unsafe_allow_html=True)
            with c2:
                st.markdown(f"**From:** {r['from_addr']}\n**To:** {r['to_addr']}\n**Manual:** {'Yes' if r['manual_review_required'] else 'No'}")
                st.text_area("Body", value=r["body"] or "", height=150, disabled=True, label_visibility="collapsed", key=f"b_{r['email_id']}")

def tab_manual_review():
    st.markdown("### Manual Review")
    emails = get_manual_review_emails()
    if not emails: return st.success("No emails to review.")
    for r in emails:
        with st.container():
            st.markdown('<div class="email-card">', unsafe_allow_html=True)
            c1, c2 = st.columns([3, 1])
            with c1:
                st.markdown(f"{badge(r['criticality_level'])} **{r['subject']}**", unsafe_allow_html=True)
                st.caption(f"From: {r['from_addr']} | Score: {r['risk_score']}")
                st.markdown(f"> {r['reasoning']}")
            with c2:
                note = st.text_input("Note", key=f"n_{r['email_id']}", placeholder="Add note...", label_visibility="collapsed")
                b1, b2 = st.columns(2)
                if b1.button("✅ TP", key=f"tp_{r['email_id']}", use_container_width=True, type="primary"):
                    record_feedback(r["email_id"], "tp", note)
                    st.rerun()
                if b2.button("❌ FP", key=f"fp_{r['email_id']}", use_container_width=True):
                    record_feedback(r["email_id"], "fp", note)
                    st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

def tab_config():
    st.markdown("### Config")
    with open("scoring_matrix.json") as f: w = json.load(f)
    new_w = {}
    cols = st.columns(3)
    for i, (k, v) in enumerate(sorted(w.items())):
        with cols[i%3]: new_w[k] = st.slider(k, 0.0, 1.0, float(v), 0.05, key=f"w_{k}")
    if st.button("Save Weights"):
        with open("scoring_matrix.json", "w") as f: json.dump(new_w, f, indent=2)
        settings.SCORING_WEIGHTS = new_w
        st.success("Saved.")
    st.markdown("---")
    t = settings.CRITICALITY_THRESHOLDS.copy()
    c1, c2, c3, c4 = st.columns(4)
    t["critical"] = c1.number_input("Critical ≥", value=float(t["critical"]))
    t["high"] = c2.number_input("High ≥", value=float(t["high"]))
    t["medium"] = c3.number_input("Medium ≥", value=float(t["medium"]))
    t["low"] = c4.number_input("Low ≥", value=float(t["low"]))
    if st.button("Save Thresholds"):
        settings.CRITICALITY_THRESHOLDS = t
        set_config("criticality_thresholds", t)
        st.success("Saved.")

def main():
    sidebar()
    t1, t2, t3, t4, t5 = st.tabs(["📤 Upload", "📊 Dash", "📋 Ranked", "🔎 Review", "⚙️ Config"])
    with t1: tab_upload()
    with t2: tab_dashboard()
    with t3: tab_ranked()
    with t4: tab_manual_review()
    with t5: tab_config()

if __name__ == "__main__": main()
