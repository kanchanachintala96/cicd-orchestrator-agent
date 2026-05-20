import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.analyzer import ProjectAnalyzer
from orchestrator.cleanup import ResourceCleaner
from orchestrator.generator import PipelineGenerator, Pipeline
from orchestrator.github import GitHubConnector, parse_repo_input

# ── Paths ─────────────────────────────────────────────────────────────────────
HISTORY_FILE = Path.home() / ".cicd_orchestrator" / "history.json"

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CI/CD Orchestrator",
    page_icon="🔧",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Hero banner */
.hero {
    background: linear-gradient(135deg, #0f0c29, #302b63, #24243e);
    padding: 2rem 2.5rem;
    border-radius: 14px;
    margin-bottom: 1.5rem;
    border: 1px solid rgba(124,58,237,0.35);
}
.hero h1 { color:#f1f5f9; font-size:1.9rem; margin:0; font-weight:700; letter-spacing:-0.5px; }
.hero p  { color:#94a3b8; margin:0.4rem 0 0.8rem 0; font-size:0.9rem; }
.hero .pill {
    display:inline-block;
    background:rgba(124,58,237,0.18);
    color:#a78bfa;
    border:1px solid rgba(124,58,237,0.4);
    padding:2px 12px; border-radius:20px; font-size:0.72rem; margin-right:6px;
}

/* Stat cards in sidebar */
.stat-card {
    background: linear-gradient(135deg,#1e293b,#0f172a);
    border:1px solid rgba(255,255,255,0.07);
    border-radius:10px; padding:10px 14px; margin-bottom:8px; text-align:center;
}
.stat-card .num { color:#e2e8f0; font-size:1.5rem; font-weight:700; }
.stat-card .lbl { color:#64748b; font-size:0.7rem; text-transform:uppercase; letter-spacing:.05em; }

/* Analysis cards */
.info-card {
    background:linear-gradient(135deg,#1e1e2e,#252545);
    border:1px solid rgba(255,255,255,0.07);
    border-radius:10px; padding:14px 16px; text-align:center;
}
.info-card .val { color:#e2e8f0; font-size:1.3rem; font-weight:700; margin-bottom:4px; }
.info-card .lbl { color:#64748b; font-size:0.7rem; text-transform:uppercase; letter-spacing:.06em; }

/* Pipeline timeline */
.timeline { border-left:2px solid #334155; margin-left:14px; padding-left:0; list-style:none; }
.tl-item  { position:relative; padding:8px 0 8px 28px; }
.tl-dot   {
    position:absolute; left:-7px; top:12px;
    width:12px; height:12px; border-radius:50%;
    background:#7c3aed; border:2px solid #0f172a;
}
.tl-name  { color:#e2e8f0; font-weight:600; font-size:0.88rem; }
.tl-cmd   { color:#475569; font-family:monospace; font-size:0.74rem; margin-top:2px; }
.badge-c  { background:rgba(239,68,68,.15); color:#f87171; border:1px solid rgba(239,68,68,.3); padding:1px 8px; border-radius:12px; font-size:0.68rem; margin-left:6px; }
.badge-o  { background:rgba(251,191,36,.15); color:#fbbf24; border:1px solid rgba(251,191,36,.3); padding:1px 8px; border-radius:12px; font-size:0.68rem; margin-left:6px; }

/* Execution step cards */
.step-running { background:#0f172a; border-left:4px solid #3b82f6; border-radius:8px; padding:12px 16px; margin-bottom:8px; }
.step-pass    { background:rgba(34,197,94,.06); border-left:4px solid #22c55e; border-radius:8px; padding:12px 16px; margin-bottom:8px; }
.step-fail    { background:rgba(239,68,68,.06);  border-left:4px solid #ef4444; border-radius:8px; padding:12px 16px; margin-bottom:8px; }
.step-title   { color:#e2e8f0; font-weight:700; font-size:0.9rem; }
.step-status-run  { color:#60a5fa; font-size:0.78rem; }
.step-status-pass { color:#4ade80; font-size:0.78rem; }
.step-status-fail { color:#f87171; font-size:0.78rem; }
.step-time    { color:#64748b; font-size:0.74rem; float:right; }

/* Terminal log */
.terminal {
    background:#030712; color:#94a3b8;
    font-family:monospace; font-size:0.76rem;
    padding:10px 14px; border-radius:6px;
    border:1px solid #1e293b;
    max-height:260px; overflow-y:auto; white-space:pre-wrap;
}

/* Section label */
.sec-label {
    color:#64748b; font-size:0.68rem; text-transform:uppercase;
    letter-spacing:.1em; margin-bottom:6px;
    border-bottom:1px solid #1e293b; padding-bottom:4px;
}

/* Overall status banner */
.banner-pass { background:linear-gradient(90deg,rgba(34,197,94,.15),transparent); border-left:4px solid #22c55e; border-radius:8px; padding:14px 20px; color:#4ade80; font-weight:700; font-size:1rem; }
.banner-fail { background:linear-gradient(90deg,rgba(239,68,68,.15),transparent); border-left:4px solid #ef4444; border-radius:8px; padding:14px 20px; color:#f87171; font-weight:700; font-size:1rem; }

/* GitHub repo card */
.repo-card {
    background:linear-gradient(135deg,#0d1117,#161b22);
    border:1px solid #30363d; border-radius:12px; padding:20px 24px; margin-bottom:12px;
}
.repo-card .repo-title { color:#e6edf3; font-size:1.1rem; font-weight:700; }
.repo-card .repo-desc  { color:#8b949e; font-size:0.82rem; margin:6px 0 10px 0; }
.repo-card .repo-meta  { display:flex; gap:18px; flex-wrap:wrap; }
.repo-meta-item { color:#8b949e; font-size:0.78rem; }
.repo-meta-item span { color:#e6edf3; font-weight:600; }
.lang-dot { display:inline-block; width:10px; height:10px; border-radius:50%; background:#f1e05a; margin-right:4px; }
.commit-badge { background:#21262d; border:1px solid #30363d; border-radius:6px; padding:3px 10px; font-family:monospace; font-size:0.75rem; color:#8b949e; }
.gh-user-badge { background:rgba(88,166,255,.12); border:1px solid rgba(88,166,255,.3); color:#58a6ff; padding:3px 12px; border-radius:20px; font-size:0.78rem; }

/* AI analysis */
.ai-card {
    background:linear-gradient(135deg,#0d0d1a,#1a0d2e);
    border:1px solid rgba(167,139,250,0.3);
    border-radius:10px; padding:16px 20px; margin-top:8px;
}
</style>
""", unsafe_allow_html=True)


# ── Persistent history helpers ────────────────────────────────────────────────
def _load_history() -> list:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_history(history: list):
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.write_text(json.dumps(history, indent=2), encoding="utf-8")


# ── AI analysis helper ────────────────────────────────────────────────────────
def _get_anthropic_client():
    try:
        import anthropic
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if key:
            return anthropic.Anthropic(api_key=key)
    except ImportError:
        pass
    return None


def _ai_stream(client, step_name: str, log_text: str):
    prompt = (
        f"A CI/CD pipeline step **\"{step_name}\"** failed. "
        f"Analyze the following log output and provide:\n"
        f"1. Root cause (1-2 sentences)\n"
        f"2. Specific fix with a code/command example\n"
        f"3. How to prevent this in future\n\n"
        f"Log output (last 100 lines):\n```\n{log_text[-4000:]}\n```"
    )
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── Gantt chart helper ────────────────────────────────────────────────────────
def _render_gantt(results: list):
    if not results:
        return
    gantt_data = []
    for r in results:
        gantt_data.append({
            "Step": r["Step"],
            "Start": r.get("Start", 0),
            "End": r.get("Start", 0) + r.get("Duration", 0),
            "Status": r["Status"],
        })
    df = pd.DataFrame(gantt_data)
    chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusTopRight=3, cornerRadiusBottomRight=3)
        .encode(
            x=alt.X("Start:Q", title="Time (seconds)", axis=alt.Axis(labelColor="#94a3b8", titleColor="#94a3b8")),
            x2="End:Q",
            y=alt.Y("Step:N", sort=None, axis=alt.Axis(labelColor="#e2e8f0", labelFontSize=12)),
            color=alt.condition(
                alt.datum.Status == "PASS",
                alt.value("#22c55e"),
                alt.value("#ef4444"),
            ),
            tooltip=["Step", alt.Tooltip("Start:Q", format=".2f"), alt.Tooltip("End:Q", format=".2f"), "Status"],
        )
        .properties(height=max(60, len(results) * 40 + 40), background="transparent",
                    title=alt.TitleParams("Step Duration (Gantt)", color="#94a3b8"))
        .configure_view(strokeWidth=0)
        .configure_axis(gridColor="#1e293b")
    )
    st.altair_chart(chart, use_container_width=True)


# ── Shared execution loop ─────────────────────────────────────────────────────
def run_pipeline_ui(pipeline: Pipeline, run_key: str) -> dict:
    """Execute pipeline with live UI feedback. Returns summary dict."""
    total_steps = len(pipeline.steps)
    progress_bar = st.progress(0, text="Starting pipeline...")
    results, run_logs, aborted = [], {}, False
    pipeline_start = time.time()

    for idx, step in enumerate(pipeline.steps, 1):
        progress_bar.progress(int((idx - 1) / total_steps * 100), text=f"Running: {step.name}")
        card = st.empty()
        log_box = st.empty()
        log_lines, success = [], False

        card.markdown(
            f'<div class="step-running">'
            f'<span class="step-title">⚙ {step.name}</span>&nbsp;&nbsp;'
            f'<span class="step-status-run">● running...</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        step_start = time.time() - pipeline_start
        t0 = time.time()

        try:
            env  = {**os.environ, **step.env}
            proc = subprocess.Popen(
                step.command, cwd=step.cwd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
            )
            try:
                for line in iter(proc.stdout.readline, ""):
                    s = line.rstrip()
                    if s:
                        log_lines.append(s)
                        log_box.markdown(
                            f'<div class="terminal">{chr(10).join(log_lines[-60:])}</div>',
                            unsafe_allow_html=True,
                        )
                proc.wait(timeout=step.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                log_lines.append(f"ERROR: Step timed out after {step.timeout} seconds.")
            success = proc.returncode == 0
        except FileNotFoundError as exc:
            log_lines.append(f"ERROR: command not found — {exc}")
        except Exception as exc:
            log_lines.append(f"ERROR: {exc}")

        duration = round(time.time() - t0, 2)
        run_logs[step.name] = "\n".join(log_lines)
        log_box.markdown(
            f'<div class="terminal">{chr(10).join(log_lines[-60:])}</div>',
            unsafe_allow_html=True,
        )

        time_badge = f'<span class="step-time">⏱ {duration}s</span>'
        if success:
            card.markdown(
                f'<div class="step-pass">'
                f'<span class="step-title">✔ {step.name}</span>&nbsp;&nbsp;'
                f'<span class="step-status-pass">● passed</span>{time_badge}'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            card.markdown(
                f'<div class="step-fail">'
                f'<span class="step-title">✘ {step.name}</span>&nbsp;&nbsp;'
                f'<span class="step-status-fail">● failed</span>{time_badge}'
                f'</div>',
                unsafe_allow_html=True,
            )

        results.append({
            "Step":     step.name,
            "Status":   "PASS" if success else "FAIL",
            "Critical": "Yes" if step.critical else "No",
            "Duration": duration,
            "Start":    round(step_start, 2),
        })

        if not success and step.critical:
            st.error("Critical step failed — pipeline aborted.")
            aborted = True
            break

    elapsed = round(time.time() - pipeline_start, 2)
    progress_bar.progress(100, text="Pipeline complete.")

    return {
        "results": results,
        "logs":    run_logs,
        "elapsed": elapsed,
        "aborted": aborted,
    }


def render_run_summary(run_data: dict, run_key: str):
    """Render summary metrics, charts, AI analysis, and download button."""
    results = run_data["results"]
    run_logs = run_data["logs"]
    elapsed  = run_data["elapsed"]
    aborted  = run_data["aborted"]

    passed = sum(1 for r in results if r["Status"] == "PASS")
    failed = len(results) - passed

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="sec-label">Summary</div>', unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Steps", len(results))
    m2.metric("Passed",      passed)
    m3.metric("Failed",      failed)
    m4.metric("Duration",    f"{elapsed}s")

    left, right = st.columns([3, 2])
    with left:
        df = pd.DataFrame([{k: v for k, v in r.items() if k != "Start"} for r in results])
        def _color(val):
            if val == "PASS": return "background-color:#14532d;color:#4ade80"
            if val == "FAIL": return "background-color:#450a0a;color:#f87171"
            return ""
        st.dataframe(df.style.map(_color, subset=["Status"]),
                     use_container_width=True, hide_index=True)
    with right:
        if results:
            donut_df = pd.DataFrame([
                {"Result": "Passed", "Count": passed},
                {"Result": "Failed", "Count": failed},
            ])
            chart = (
                alt.Chart(donut_df)
                .mark_arc(innerRadius=55, outerRadius=90)
                .encode(
                    theta=alt.Theta("Count:Q"),
                    color=alt.Color("Result:N",
                        scale=alt.Scale(domain=["Passed","Failed"], range=["#22c55e","#ef4444"]),
                        legend=alt.Legend(orient="bottom", labelColor="#94a3b8", titleColor="#94a3b8")),
                    tooltip=["Result","Count"],
                )
                .properties(width=220, height=200, background="transparent")
                .configure_view(strokeWidth=0)
            )
            st.altair_chart(chart, use_container_width=True)

    # Gantt chart
    if len(results) > 1:
        st.markdown('<div class="sec-label">Step Timeline</div>', unsafe_allow_html=True)
        _render_gantt(results)

    # Overall banner
    if failed == 0:
        st.markdown('<div class="banner-pass">✔ All steps passed — pipeline successful</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="banner-fail">✘ {failed} step(s) failed'
            f'{"  — pipeline aborted" if aborted else ""}</div>',
            unsafe_allow_html=True,
        )

    # AI Failure Analysis
    ai_client = _get_anthropic_client()
    failed_steps = [r["Step"] for r in results if r["Status"] == "FAIL"]
    if failed_steps:
        if ai_client:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="sec-label">🤖 AI Failure Analysis</div>', unsafe_allow_html=True)
            ai_cache_key = f"ai_analyses_{run_key}"
            if ai_cache_key not in st.session_state:
                st.session_state[ai_cache_key] = {}

            for step_name in failed_steps:
                log_text = run_logs.get(step_name, "No log captured.")
                btn_key  = f"ai_btn_{run_key}_{step_name}"
                cache_key = f"{run_key}_{step_name}"

                with st.expander(f"Analyze failure: **{step_name}**", expanded=False):
                    if cache_key in st.session_state[ai_cache_key]:
                        st.markdown(st.session_state[ai_cache_key][cache_key])
                    elif st.button("🤖 Analyze with Claude", key=btn_key):
                        with st.spinner("Analyzing with Claude..."):
                            result = st.write_stream(_ai_stream(ai_client, step_name, log_text))
                            st.session_state[ai_cache_key][cache_key] = result
        else:
            st.caption(
                "💡 Set `ANTHROPIC_API_KEY` environment variable to enable AI failure analysis."
            )

    # Log download
    st.markdown("<br>", unsafe_allow_html=True)
    full_log = "\n\n".join(f"=== {k} ===\n{v}" for k, v in run_logs.items())
    st.download_button(
        "⬇ Download Full Log", data=full_log,
        file_name=f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        mime="text/plain",
    )

    return passed, failed


# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [("total_runs", 0), ("total_pass", 0)]:
    if key not in st.session_state:
        st.session_state[key] = default

if "run_history" not in st.session_state:
    st.session_state.run_history = _load_history()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.markdown("---")

    repo_path = st.text_input("Repository Path", value="./sample_app", placeholder="./my_project")

    GOALS = ["Run pipeline", "Run tests", "Lint only", "Deploy", "Custom..."]
    goal_choice = st.selectbox("Goal", GOALS, index=0)
    goal = st.text_input("Custom goal", placeholder="e.g. deploy to staging") if goal_choice == "Custom..." else goal_choice

    no_cleanup = st.toggle("Skip cleanup after run", value=False)

    st.markdown("---")
    run_btn = st.button("▶  Run Pipeline", type="primary", use_container_width=True)
    st.markdown("---")

    total  = len(st.session_state.run_history)
    passed_total = sum(1 for r in st.session_state.run_history if r.get("Result") == "PASS")
    rate   = round(passed_total / total * 100) if total else 0
    st.markdown(f"""
    <div class="stat-card"><div class="num">{total}</div><div class="lbl">Total Runs</div></div>
    <div class="stat-card"><div class="num" style="color:#4ade80">{rate}%</div><div class="lbl">Pass Rate</div></div>
    """, unsafe_allow_html=True)

    # Pass-rate sparkline (last 10 runs)
    if len(st.session_state.run_history) >= 2:
        recent = st.session_state.run_history[-10:]
        spark_df = pd.DataFrame([
            {"i": i, "pass": 1 if r.get("Result") == "PASS" else 0}
            for i, r in enumerate(recent)
        ])
        sparkline = (
            alt.Chart(spark_df)
            .mark_area(line={"color": "#7c3aed"}, color=alt.Gradient(
                gradient="linear",
                stops=[alt.GradientStop(color="rgba(124,58,237,0.4)", offset=0),
                       alt.GradientStop(color="rgba(124,58,237,0)", offset=1)],
                x1=1, x2=1, y1=1, y2=0,
            ))
            .encode(
                x=alt.X("i:O", axis=None),
                y=alt.Y("pass:Q", axis=None, scale=alt.Scale(domain=[0, 1])),
            )
            .properties(height=50, background="transparent")
            .configure_view(strokeWidth=0)
        )
        st.markdown('<div style="color:#64748b;font-size:0.7rem;text-transform:uppercase;letter-spacing:.08em;margin-bottom:4px">Recent Pass Rate</div>', unsafe_allow_html=True)
        st.altair_chart(sparkline, use_container_width=True)

    st.caption("Supported: `Run pipeline` · `Run tests` · `Lint only`")

# ── Hero header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🔧 CI/CD Orchestrator Agent</h1>
  <p>Local pipeline execution with automatic project detection, structured reporting, and AI-powered failure analysis</p>
  <span class="pill">Python</span>
  <span class="pill">Node.js</span>
  <span class="pill">Auto-detect</span>
  <span class="pill">Retry</span>
  <span class="pill">Rich Logs</span>
  <span class="pill">AI Analysis</span>
</div>
""", unsafe_allow_html=True)

# ── Tabs ─────────────────────────────────────────────────────────────────────
tab_local, tab_github = st.tabs(["💻  Local", "🐙  GitHub"])

# ════════════════════════════════════════════════════════════════════════════
# GITHUB TAB
# ════════════════════════════════════════════════════════════════════════════
with tab_github:
    gh_col, _ = st.columns([3, 1])
    with gh_col:
        st.markdown('<div class="sec-label">GitHub Connection</div>', unsafe_allow_html=True)
        gh_token = st.text_input(
            "Personal Access Token (optional — needed for private repos & commit status)",
            type="password", key="gh_token",
            placeholder="ghp_xxxxxxxxxxxxxxxxxxxx",
        )
        gh_repo_input = st.text_input(
            "Repository",
            placeholder="owner/repo  or  https://github.com/owner/repo",
            key="gh_repo_input",
        )

    if gh_repo_input:
        try:
            gh_owner, gh_repo_name = parse_repo_input(gh_repo_input)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()

        connector = GitHubConnector(token=gh_token or None)

        whoami = connector.whoami()
        if whoami:
            st.markdown(f'<span class="gh-user-badge">✔ Authenticated as <b>{whoami}</b></span>',
                        unsafe_allow_html=True)
        else:
            st.caption("Using unauthenticated access (60 req/hr limit).")

        st.markdown("<br>", unsafe_allow_html=True)

        with st.spinner(f"Fetching {gh_owner}/{gh_repo_name}…"):
            try:
                info = connector.get_repo(gh_owner, gh_repo_name)
            except FileNotFoundError:
                st.error(f"Repository `{gh_owner}/{gh_repo_name}` not found on GitHub.")
                st.stop()
            except (PermissionError, RuntimeError) as exc:
                st.error(str(exc))
                st.stop()

        lock = "🔒 Private" if info.private else "🌐 Public"
        st.markdown(f"""
        <div class="repo-card">
          <div class="repo-title">📦 {info.full_name} &nbsp;<small style="color:#8b949e;font-weight:400">{lock}</small></div>
          <div class="repo-desc">{info.description or "No description provided."}</div>
          <div class="repo-meta">
            <div class="repo-meta-item"><span class="lang-dot"></span>{info.language}</div>
            <div class="repo-meta-item">⭐ <span>{info.stars:,}</span> stars</div>
            <div class="repo-meta-item">🍴 <span>{info.forks:,}</span> forks</div>
            <div class="repo-meta-item">🌿 default: <span>{info.default_branch}</span></div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.spinner("Fetching branches…"):
            try:
                branches = connector.list_branches(gh_owner, gh_repo_name)
            except Exception:
                branches = [info.default_branch]

        gc1, gc2, gc3, gc4 = st.columns([2, 2, 2, 1])
        with gc1:
            selected_branch = st.selectbox(
                "Branch", branches,
                index=branches.index(info.default_branch) if info.default_branch in branches else 0,
                key="gh_branch",
            )
        with gc2:
            GH_GOALS = ["Run pipeline", "Run tests", "Lint only", "Deploy", "Custom..."]
            gh_goal_choice = st.selectbox("Goal", GH_GOALS, key="gh_goal_choice")
            gh_goal = (st.text_input("Custom goal", key="gh_custom_goal")
                       if gh_goal_choice == "Custom..." else gh_goal_choice)
        with gc3:
            gh_subdir = st.text_input(
                "Subdirectory (optional)",
                placeholder="e.g. sample_app",
                key="gh_subdir",
                help="Analyze a subfolder of the repo instead of the root",
            )
        with gc4:
            st.markdown("<br>", unsafe_allow_html=True)
            gh_no_cleanup = st.toggle("Skip cleanup", key="gh_no_cleanup")

        clone_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            ".cloned_repos", f"{gh_owner}__{gh_repo_name}",
        )
        analyze_dir = os.path.join(clone_dir, gh_subdir.strip()) if gh_subdir.strip() else clone_dir

        clone_run_btn = st.button("🚀  Clone & Run Pipeline", type="primary", key="gh_run_btn")

        if clone_run_btn:
            st.markdown("---")

            with st.status(f"Cloning {info.full_name}@{selected_branch}…", expanded=True) as clone_status:
                result = connector.clone(info, clone_dir, selected_branch)
                if not result.success:
                    clone_status.update(label="Clone failed", state="error")
                    st.error(f"Clone error: {result.error}")
                    st.stop()
                clone_status.update(
                    label=f"Cloned successfully — HEAD {result.commit_sha[:7]}", state="complete"
                )

            if result.commit_sha:
                st.markdown(
                    f'Commit: <span class="commit-badge">{result.commit_sha[:7]}</span>',
                    unsafe_allow_html=True,
                )

            try:
                gh_config   = ProjectAnalyzer(analyze_dir).analyze()
                gh_pipeline = PipelineGenerator(gh_config, goal=gh_goal).generate()
            except Exception as exc:
                st.error(f"Setup failed: {exc}")
                st.stop()

            if not gh_pipeline.steps:
                st.warning("No pipeline steps generated for this repo.")
                st.stop()

            st.markdown('<div class="sec-label">Execution</div>', unsafe_allow_html=True)

            gh_run_key = f"gh_{st.session_state.total_runs + 1}"
            gh_run_data = run_pipeline_ui(gh_pipeline, gh_run_key)
            gh_results  = gh_run_data["results"]
            gh_elapsed  = gh_run_data["elapsed"]

            gh_passed, gh_failed = render_run_summary(gh_run_data, gh_run_key)

            # Post commit status to GitHub
            state  = "success" if gh_failed == 0 else "failure"
            desc   = f"{gh_passed}/{len(gh_results)} steps passed in {gh_elapsed}s"
            posted = connector.post_commit_status(
                gh_owner, gh_repo_name, result.commit_sha, state, desc
            )
            if posted:
                st.success(f"Commit status posted to GitHub: **{state}**")

            if not gh_no_cleanup:
                with st.spinner("Cleaning up cloned repo…"):
                    try:
                        ResourceCleaner(clone_dir).clean()
                    except Exception:
                        pass

            st.session_state.total_runs += 1
            if gh_failed == 0:
                st.session_state.total_pass += 1
            record = {
                "timestamp": datetime.now().isoformat(),
                "Run":    st.session_state.total_runs,
                "Repo":   info.full_name,
                "Goal":   gh_goal,
                "Passed": gh_passed,
                "Failed": gh_failed,
                "Time(s)": gh_elapsed,
                "Result": "PASS" if gh_failed == 0 else "FAIL",
            }
            st.session_state.run_history.append(record)
            _save_history(st.session_state.run_history)

# ════════════════════════════════════════════════════════════════════════════
# LOCAL TAB
# ════════════════════════════════════════════════════════════════════════════
with tab_local:
    abs_path = os.path.abspath(repo_path) if repo_path else ""

    if abs_path and os.path.isdir(abs_path):
        try:
            config = ProjectAnalyzer(abs_path).analyze()

            st.markdown('<div class="sec-label">Project Analysis</div>', unsafe_allow_html=True)
            c1, c2, c3, c4, c5 = st.columns(5)
            cards = [
                ("Type",           config.project_type.capitalize(), c1),
                ("Test Framework", config.test_framework.capitalize(), c2),
                ("Has Tests",      "Yes" if config.has_tests      else "No", c3),
                ("Lint Config",    "Yes" if config.has_lint_config else "No", c4),
                ("Runtime",        config.node_package_manager or config.python_executable, c5),
            ]
            for label, value, col in cards:
                col.markdown(
                    f'<div class="info-card"><div class="val">{value}</div>'
                    f'<div class="lbl">{label}</div></div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)

            if goal and goal.strip():
                try:
                    pipeline_preview = PipelineGenerator(config, goal=goal).generate()
                    with st.expander(f"Pipeline Preview — {len(pipeline_preview.steps)} step(s)", expanded=True):
                        items_html = ""
                        for i, step in enumerate(pipeline_preview.steps, 1):
                            badge = ('<span class="badge-c">CRITICAL</span>'
                                     if step.critical else '<span class="badge-o">OPTIONAL</span>')
                            cmd = " ".join(step.command)
                            items_html += (
                                f'<div class="tl-item"><div class="tl-dot"></div>'
                                f'<div class="tl-name">{i}. {step.name} {badge}</div>'
                                f'<div class="tl-cmd">{cmd}</div></div>'
                            )
                        st.markdown(f'<ul class="timeline">{items_html}</ul>', unsafe_allow_html=True)
                except ValueError as exc:
                    st.warning(str(exc))

        except Exception as exc:
            st.error(f"Analysis error: {exc}")
    elif abs_path:
        st.warning(f"Path not found: `{abs_path}`")

    # ── Run ───────────────────────────────────────────────────────────────────
    if run_btn:
        if not abs_path or not os.path.isdir(abs_path):
            st.error("Invalid repository path.")
            st.stop()
        if not goal or not goal.strip():
            st.error("Please enter a goal.")
            st.stop()

        st.markdown("---")
        st.markdown('<div class="sec-label">Execution</div>', unsafe_allow_html=True)

        try:
            config   = ProjectAnalyzer(abs_path).analyze()
            pipeline = PipelineGenerator(config, goal=goal).generate()
        except Exception as exc:
            st.error(f"Setup failed: {exc}")
            st.stop()

        if not pipeline.steps:
            st.warning("No pipeline steps generated.")
            st.stop()

        run_key  = f"local_{st.session_state.total_runs + 1}"
        run_data = run_pipeline_ui(pipeline, run_key)
        passed, failed = render_run_summary(run_data, run_key)

        if not no_cleanup:
            with st.spinner("Cleaning up..."):
                try:
                    ResourceCleaner(abs_path).clean()
                except Exception as exc:
                    st.warning(f"Cleanup warning: {exc}")
            st.info("Cleanup complete.")

        st.session_state.total_runs += 1
        if failed == 0:
            st.session_state.total_pass += 1
        record = {
            "timestamp": datetime.now().isoformat(),
            "Run":    st.session_state.total_runs,
            "Repo":   os.path.basename(abs_path),
            "Goal":   goal,
            "Passed": passed,
            "Failed": failed,
            "Time(s)": run_data["elapsed"],
            "Result": "PASS" if failed == 0 else "FAIL",
        }
        st.session_state.run_history.append(record)
        _save_history(st.session_state.run_history)

# ── Run History ───────────────────────────────────────────────────────────────
if st.session_state.run_history:
    st.markdown("---")
    hist_col, clear_col = st.columns([6, 1])
    with hist_col:
        st.markdown('<div class="sec-label">Run History</div>', unsafe_allow_html=True)
    with clear_col:
        if st.button("🗑 Clear", key="clear_history"):
            st.session_state.run_history = []
            _save_history([])
            st.rerun()

    hist_df = pd.DataFrame(st.session_state.run_history)
    display_cols = [c for c in ["Run", "Repo", "Goal", "Passed", "Failed", "Time(s)", "Result"]
                    if c in hist_df.columns]
    col_chart, col_table = st.columns([2, 3])

    with col_chart:
        bar_data = hist_df.melt(id_vars="Run", value_vars=["Passed","Failed"],
                                var_name="Status", value_name="Count")
        bar = (
            alt.Chart(bar_data)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("Run:O", title="Run #",
                        axis=alt.Axis(labelColor="#94a3b8", titleColor="#94a3b8")),
                y=alt.Y("Count:Q", title="Steps",
                        axis=alt.Axis(labelColor="#94a3b8", titleColor="#94a3b8")),
                color=alt.Color("Status:N",
                    scale=alt.Scale(domain=["Passed","Failed"], range=["#22c55e","#ef4444"]),
                    legend=alt.Legend(orient="bottom", labelColor="#94a3b8")),
                tooltip=["Run","Status","Count"],
            )
            .properties(height=200, background="transparent",
                        title=alt.TitleParams("Steps per Run", color="#94a3b8"))
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(bar, use_container_width=True)

    with col_table:
        def _row_color(val):
            if val == "PASS": return "background-color:#14532d;color:#4ade80"
            if val == "FAIL": return "background-color:#450a0a;color:#f87171"
            return ""
        st.dataframe(
            hist_df[display_cols].style.map(_row_color, subset=["Result"]),
            use_container_width=True, hide_index=True,
        )
