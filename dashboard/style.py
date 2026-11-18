import streamlit as st


def apply_dashboard_style() -> None:
    st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
            --canvas: #0b1220;
            --panel: #111b2d;
            --panel-soft: #162238;
            --line: #24334b;
            --muted: #91a1b8;
            --text: #e8eef8;
            --blue: #63a8ff;
            --green: #41c994;
            --red: #ff6577;
            --orange: #ffad5c;
            --yellow: #f3cb62;
            --purple: #b69aff;
        }
        .stApp { background: var(--canvas); color: var(--text); }
        [data-testid="stSidebar"] {
            background: #0e1828;
            border-right: 1px solid var(--line);
        }
        [data-testid="stSidebar"] h2 { letter-spacing: -.03em; }
        .eyebrow {
            color: var(--blue); font-size: .73rem; font-weight: 700;
            letter-spacing: .14em; margin: .2rem 0 .35rem;
        }
        .page-title {
            font-size: 1.9rem; font-weight: 700; letter-spacing: -.04em;
            margin: 0 0 .7rem; color: var(--text);
        }
        .system-status {
            display: inline-flex; align-items: center; gap: .5rem;
            border: 1px solid #245641; background: #11291f;
            color: #8be0ba; border-radius: 999px;
            padding: .38rem .72rem; font-size: .72rem; font-weight: 700;
            letter-spacing: .04em; float: right;
        }
        .status-dot {
            height: .48rem; width: .48rem; border-radius: 50%;
            display: inline-block; background: var(--green);
            box-shadow: 0 0 10px #41c99477;
        }
        div[data-testid="stMetric"] {
            background: linear-gradient(145deg, #142036, #101a2b);
            border: 1px solid var(--line); border-radius: 14px;
            padding: 1rem 1.05rem; min-height: 112px;
        }
        div[data-testid="stMetricLabel"] p {
            color: var(--muted); font-size: .78rem;
        }
        div[data-testid="stMetricValue"] {
            color: var(--text); font-weight: 700;
        }
        div[data-testid="stMetricDelta"] { font-size: .75rem; }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--line); border-radius: 12px;
        }
        div[data-testid="stPlotlyChart"] {
            background: #101a2a; border: 1px solid var(--line);
            border-radius: 12px; padding: .3rem;
        }
        div[data-testid="stExpander"] {
            border: 1px solid var(--line); border-radius: 10px;
        }
        div[data-testid="stAlert"] { border-radius: 10px; }
        .security-card {
            background: #111b2d; border: 1px solid var(--line);
            border-radius: 12px; padding: 1rem 1.1rem; margin-bottom: .7rem;
        }
        .security-card-title {
            font-weight: 650; color: var(--text); margin-bottom: .25rem;
        }
        .security-card-meta { color: var(--muted); font-size: .82rem; }
        .severity-critical { color: var(--red); }
        .severity-high { color: var(--orange); }
        .severity-medium { color: var(--yellow); }
        .severity-info { color: var(--purple); }
        .small-note { color: var(--muted); font-size: .82rem; }
        button[kind="secondary"] { border-color: var(--line); }
        @media (max-width: 700px) {
            .page-title { font-size: 1.55rem; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
