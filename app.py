import json
import io
import tempfile
from pathlib import Path

import streamlit as st
import pandas as pd

from db import (
    init_db, get_all_batches, get_batch_results, get_manual_review_emails,
    record_feedback, get_all_config, set_config
)
from pipeline.graph import EmailPipeline
from config import settings

# Page setup

st.set_page_config(
    page_title="BFSI Email Analyser",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

# Styles

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }

    .stApp { background-color: #0f1117; }

    /* Metric cards */
    [data-testid="metric-container"] {
        background: linear-gradient(135deg, #1e2130 0%, #252840 100%);
        border: 1px solid #2d3250;
        border-radius: 12px;
        padding: 16px 20px;
    }
    [data-testid="metric-container"] label { color: #8b92b3 !important; font-size: 0.8rem !important; }
    [data-testid="metric-container"] [data-testid="metric-value"] { color: #ffffff !important; font-size: 1.6rem !important; font-weight: 700 !important; }

    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: #1a1d2e;
        border-radius: 10px;
        gap: 4px;
        padding: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        color: #8b92b3;
        font-weight: 500;
        padding: 8px 20px;
    }
    .stTabs [aria-selected="true"] {
        background: #4f6ef7 !important;
        color: white !important;
    }

    /* Risk badges */
    .badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.5px;
    }
    .badge-critical { background: #ff4d4d22; color: #ff4d4d; border: 1px solid #ff4d4d44; }
    .badge-high     { background: #ff8c0022; color: #ff8c00; border: 1px solid #ff8c0044; }
    .badge-medium   { background: #ffd70022; color: #ffd700; border: 1px solid #ffd70044; }
    .badge-low      { background: #00e67622; color: #00e676; border: 1px solid #00e67644; }

    /* Email cards */
    .email-card {
        background: #1a1d2e;
        border: 1px solid #2d3250;
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 10px;
        transition: border-color 0.2s;
    }
    .email-card:hover { border-color: #4f6ef7; }

    /* Evidence block */
    .evidence-block {
        background: #12141f;
        border-left: 3px solid #4f6ef7;
        border-radius: 0 8px 8px 0;
        padding: 10px 14px;
        margin: 6px 0;
        font-size: 0.85rem;
    }

    /* Sidebar */
    [data-testid="stSidebar"] { background-color: #13151f; border-right: 1px solid #2d3250; }

    /* Buttons */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.2s;
    }
    .stButton > button:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(79,110,247,0.3); }

    /* Section headers */
    .section-header {
        font-size: 0.7rem;
        font-weight: 600;
        letter-spacing: 1.5px;
        color: #4f6ef7;
        text-transform: uppercase;
        margin-bottom: 12px;
    }

    /* Score bar */
    .score-bar-wrap { background: #252840; border-radius: 20px; height: 8px; width: 100%; }
    .score-bar-fill { height: 8px; border-radius: 20px; }
</style>
""", unsafe_allow_html=True)

# Helpers

LEVEL_COLORS = {
    "critical": "#ff4d4d",
    "high": "#ff8c00",
    "medium": "#ffd700",
    "low": "#00e676",
}


def badge(level: str) -> str:
    return f'<span class="badge badge-{level}">{level.upper()}</span>'


def score_bar(score: float, level: str) -> str:
    color = LEVEL_COLORS.get(level, "#4f6ef7")
    return f"""
    <div class="score-bar-wrap">
        <div class="score-bar-fill" style="width:{score}%; background:{color};"></div>
    </div>
    """


def sidebar():
    with st.sidebar:
        st.markdown("## 🔍 Email Analyser")
        st.markdown("BFSI Compliance Intelligence")
        st.markdown("---")

        batches = get_all_batches()
        if batches:
            st.markdown('<div class="section-header">Batch History</div>', unsafe_allow_html=True)
            options = {f"{b['filename']} ({b['created_at'][:10]})": b["id"] for b in batches}
            selected_label = st.selectbox("Select batch", list(options.keys()), label_visibility="collapsed")
            st.session_state["selected_batch"] = options[selected_label]
        else:
            st.info("No batches yet. Upload a file to start.")
            st.session_state.setdefault("selected_batch", None)

        st.markdown("---")
        st.caption("v2.0 · SQLite + LangGraph")


# Tab 1 — Upload & Analyze

def tab_upload():
    st.markdown("### Upload & Analyze")
    st.markdown("Upload an `.xlsx` or `.csv` file with columns: `email_id`, `from`, `to`, `subject`, `body`")

    uploaded = st.file_uploader("Choose file", type=["xlsx", "xls", "csv"])

    if uploaded:
        st.success(f"✓ File ready: **{uploaded.name}** ({uploaded.size / 1024:.1f} KB)")

        col1, col2 = st.columns([1, 4])
        with col1:
            run = st.button("▶ Run Analysis", type="primary", use_container_width=True)

        if run:
            suffix = Path(uploaded.name).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            pipeline = EmailPipeline()

            with st.status("Running analysis pipeline...", expanded=True) as status:
                st.write("📂 Loading emails...")
                try:
                    output = pipeline.run(tmp_path)
                    status.update(label="Analysis complete!", state="complete")
                except Exception as e:
                    status.update(label="Analysis failed", state="error")
                    st.error(str(e))
                    return

            st.session_state["selected_batch"] = output.batch_id

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Emails", output.summary.get("total", 0))
            c2.metric("🔴 Critical", output.summary.get("critical", 0))
            c3.metric("⚠️ Manual Review", output.summary.get("manual", 0))
            c4.metric("✅ Normal", output.summary.get("low", 0))

            st.info("Switch to the **Dashboard** or **Ranked Emails** tab to explore results.")


# Tab 2 — Dashboard

def tab_dashboard():
    st.markdown("### Dashboard")

    batches = get_all_batches()
    if not batches:
        st.info("No data yet. Upload a file to start.")
        return

    # Aggregate stats across all batches
    total = sum(b["total"] for b in batches)
    critical = sum(b["critical"] for b in batches)
    high = sum(b["high"] for b in batches)
    medium = sum(b["medium"] for b in batches)
    low = sum(b["low"] for b in batches)
    manual = sum(b["manual"] for b in batches)

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Total Emails", total)
    c2.metric("Critical", critical)
    c3.metric("High", high)
    c4.metric("Medium", medium)
    c5.metric("Normal", low)
    c6.metric("Manual Review", manual)

    st.markdown("---")

    # Risk distribution chart
    st.markdown("#### Risk Distribution")
    chart_data = pd.DataFrame({
        "Level": ["Critical", "High", "Medium", "Normal"],
        "Count": [critical, high, medium, low],
    })
    st.bar_chart(chart_data.set_index("Level"), color="#4f6ef7")

    st.markdown("---")

    # Batch history table
    st.markdown("#### Batch History")
    df = pd.DataFrame(batches)
    df = df.rename(columns={
        "id": "Batch ID", "filename": "File", "total": "Total",
        "critical": "Critical", "high": "High", "medium": "Medium",
        "low": "Normal", "manual": "Manual", "created_at": "Run At"
    })
    df["Run At"] = df["Run At"].str[:19].str.replace("T", " ")
    st.dataframe(df[["Batch ID", "File", "Total", "Critical", "High", "Medium", "Normal", "Manual", "Run At"]],
                 use_container_width=True, hide_index=True)


# Tab 3 — Ranked Emails

def tab_ranked():
    st.markdown("### Ranked Emails")

    batch_id = st.session_state.get("selected_batch")
    if not batch_id:
        st.info("Select a batch from the sidebar.")
        return

    results = get_batch_results(batch_id)
    if not results:
        st.info("No results for this batch.")
        return

    # Filters
    col_f1, col_f2 = st.columns([1, 3])
    with col_f1:
        level_filter = st.multiselect(
            "Filter by level",
            ["critical", "high", "medium", "low"],
            default=["critical", "high", "medium", "low"],
        )

    filtered = [r for r in results if r["criticality_level"] in level_filter]
    st.caption(f"Showing {len(filtered)} of {len(results)} emails")

    for row in filtered:
        level = row["criticality_level"]
        score = row["risk_score"]
        classifications = json.loads(row["classifications"] or "[]")
        tags = json.loads(row["tags"] or "[]")
        evidence = json.loads(row["evidence_lines"] or "[]")

        with st.expander(
            f"#{row['rank']}  {row['subject'] or '(no subject)'}  —  "
            f"{row['from_addr']}  →  Score: {score:.1f}",
            expanded=False
        ):
            col_left, col_right = st.columns([2, 1])

            with col_left:
                st.markdown(
                    f"{badge(level)} &nbsp; "
                    + " ".join(f"`{c}`" for c in classifications),
                    unsafe_allow_html=True,
                )
                st.markdown(score_bar(score, level), unsafe_allow_html=True)
                st.caption(f"Score: {score:.2f} / 100")

                if tags:
                    st.markdown("**Tags:** " + " ".join(f"`{t}`" for t in tags))

                st.markdown("**Reasoning:**")
                st.markdown(f"> {row['reasoning']}")

                if evidence:
                    st.markdown("**Evidence Lines:**")
                    for ev in evidence:
                        ev_level = ev.get("risk_level", "low")
                        color = LEVEL_COLORS.get(ev_level, "#4f6ef7")
                        st.markdown(
                            f'<div class="evidence-block" style="border-left-color:{color}">'
                            f'<b>Line {ev.get("line_number", "?")} [{ev_level.upper()}]</b> — {ev.get("reason","")}'
                            f'<br><i>"{ev.get("text","")}"</i>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

            with col_right:
                st.markdown(f"**From:** {row['from_addr']}")
                st.markdown(f"**To:** {row['to_addr']}")
                st.markdown(f"**Confidence:** {row['confidence']:.0%}")
                st.markdown(f"**Manual Review:** {'Yes ⚠️' if row['manual_review_required'] else 'No'}")
                if row.get("manual_review_reason"):
                    st.caption(row["manual_review_reason"])

                st.markdown("**Email Body:**")
                st.text_area("", value=row["body"] or "", height=150, disabled=True, label_visibility="collapsed", key=f"body_{row['email_id']}")


# Tab 4 — Manual Review

def tab_manual_review():
    st.markdown("### Manual Review")
    st.markdown("Mark emails as **True Positive** (real risk) or **False Positive** (not risky). This adjusts the sender's risk weight for future runs.")

    batch_id = st.session_state.get("selected_batch")
    if not batch_id:
        st.info("Select a batch from the sidebar.")
        return

    emails = get_manual_review_emails(batch_id)
    if not emails:
        st.success("No emails flagged for manual review in this batch.")
        return

    st.caption(f"{len(emails)} email(s) awaiting review")

    for row in emails:
        level = row["criticality_level"]
        score = row["risk_score"]
        classifications = json.loads(row["classifications"] or "[]")

        with st.container():
            st.markdown(f'<div class="email-card">', unsafe_allow_html=True)

            h_col, b_col = st.columns([3, 1])
            with h_col:
                st.markdown(
                    f"{badge(level)} &nbsp; **{row['subject'] or '(no subject)'}**",
                    unsafe_allow_html=True,
                )
                st.caption(f"From: {row['from_addr']} · Score: {score:.1f} · Classes: {', '.join(classifications)}")
                st.markdown(f"> {row['reasoning']}")
                if row.get("manual_review_reason"):
                    st.info(f"Review reason: {row['manual_review_reason']}")

            with b_col:
                note = st.text_input(
                    "Note (optional)",
                    key=f"note_{row['email_id']}",
                    placeholder="Add note...",
                    label_visibility="collapsed"
                )

                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("✅ TP", key=f"tp_{row['email_id']}", use_container_width=True, type="primary"):
                        record_feedback(row["email_id"], batch_id, "tp", note)
                        st.success("Marked as True Positive — sender weight increased.")
                        st.rerun()
                with btn_col2:
                    if st.button("❌ FP", key=f"fp_{row['email_id']}", use_container_width=True):
                        record_feedback(row["email_id"], batch_id, "fp", note)
                        st.warning("Marked as False Positive — sender weight reduced.")
                        st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)


# Tab 5 — Config

def tab_config():
    st.markdown("### Configuration")
    st.markdown("Changes take effect on the next analysis run.")

    st.markdown("#### Scoring Matrix Weights")
    st.caption("Set the risk weight (0.0-1.0) for each email classification.")

    matrix_path = Path("scoring_matrix.json")
    if matrix_path.exists():
        with open(matrix_path) as f:
            weights = json.load(f)
    else:
        weights = {}

    updated_weights = {}
    cols = st.columns(3)
    for i, (key, val) in enumerate(sorted(weights.items())):
        with cols[i % 3]:
            updated_weights[key] = st.slider(
                key,
                min_value=0.0,
                max_value=1.0,
                value=float(val),
                step=0.05,
                key=f"weight_{key}",
            )

    st.markdown("---")
    with st.expander("Add Classification"):
        new_name = st.text_input("Classification name")
        new_weight = st.slider("Weight", 0.0, 1.0, 0.5, 0.05)
        if st.button("Add") and new_name:
            updated_weights[new_name.strip().lower()] = new_weight

    if st.button("💾 Save Weights", type="primary"):
        with open(matrix_path, "w") as f:
            json.dump(updated_weights, f, indent=2)
        settings.SCORING_WEIGHTS = updated_weights
        st.success("Weights saved.")

    st.markdown("---")
    st.markdown("#### Criticality Thresholds")
    st.caption("Minimum score required to reach each risk level.")

    thresholds = settings.CRITICALITY_THRESHOLDS.copy()
    t_col1, t_col2, t_col3, t_col4 = st.columns(4)

    with t_col1:
        thresholds["critical"] = st.number_input("Critical ≥", value=float(thresholds.get("critical", 75)), min_value=0.0, max_value=100.0, step=1.0)
    with t_col2:
        thresholds["high"] = st.number_input("High ≥", value=float(thresholds.get("high", 50)), min_value=0.0, max_value=100.0, step=1.0)
    with t_col3:
        thresholds["medium"] = st.number_input("Medium ≥", value=float(thresholds.get("medium", 25)), min_value=0.0, max_value=100.0, step=1.0)
    with t_col4:
        thresholds["low"] = st.number_input("Low ≥", value=float(thresholds.get("low", 0)), min_value=0.0, max_value=100.0, step=1.0)

    if st.button("Save Thresholds"):
        settings.CRITICALITY_THRESHOLDS = thresholds
        set_config("criticality_thresholds", thresholds)
        st.success("Thresholds saved.")

    st.markdown("---")
    st.markdown("#### Model Settings")

    conf_threshold = st.slider(
        "Confidence threshold (below this → manual review)",
        0.0, 1.0, float(settings.CONFIDENCE_THRESHOLD), 0.05
    )
    batch_size = st.number_input(
        "Batch size (emails per LLM call)",
        min_value=1, max_value=20, value=int(settings.MAX_BATCH_SIZE)
    )

    if st.button("Save Model Settings"):
        settings.CONFIDENCE_THRESHOLD = conf_threshold
        settings.MAX_BATCH_SIZE = batch_size
        set_config("confidence_threshold", conf_threshold)
        set_config("max_batch_size", batch_size)
        st.success("Settings saved.")


# Main layout

def main():
    sidebar()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📤 Upload & Analyze",
        "📊 Dashboard",
        "📋 Ranked Emails",
        "🔎 Manual Review",
        "⚙️ Config",
    ])

    with tab1:
        tab_upload()
    with tab2:
        tab_dashboard()
    with tab3:
        tab_ranked()
    with tab4:
        tab_manual_review()
    with tab5:
        tab_config()


if __name__ == "__main__":
    main()
