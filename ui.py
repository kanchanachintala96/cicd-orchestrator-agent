import os
import subprocess
import sys
import time
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator.analyzer import ProjectAnalyzer
from orchestrator.cleanup import ResourceCleaner
from orchestrator.generator import PipelineGenerator
from orchestrator.github import GitHubConnector, parse_repo_input

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

/* Terminal log */
.terminal {
    background:#030712; color:#94a3b8;
    font-family:monospace; font-size:0.76rem;
    padding:10px 14px; border-radius:6px;
    border:1px solid #1e293b;
    max-height:180px; overflow-y:auto; white-space:pre-wrap;
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
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
for key, default in [("run_history", []), ("total_runs", 0), ("total_pass", 0)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Configuration")
    st.markdown("---")

    repo_path = st.text_input("Repository Path", value="./sample_app", placeholder="./my_project")

    GOALS = ["Run pipeline", "Run tests", "Lint only", "Custom..."]
    goal_choice = st.selectbox("Goal", GOALS, index=0)
    goal = st.text_input("Custom goal", placeholder="e.g. deploy to staging") if goal_choice == "Custom..." else goal_choice

    no_cleanup = st.toggle("Skip cleanup after run", value=False)

    st.markdown("---")
    run_btn = st.button("▶  Run Pipeline", type="primary", use_container_width=True)
    st.markdown("---")

    # Live session stats
    total = st.session_state.total_runs
    rate  = round(st.session_state.total_pass / total * 100) if total else 0
    st.markdown(f"""
    <div class="stat-card"><div class="num">{total}</div><div class="lbl">Total Runs</div></div>
    <div class="stat-card"><div class="num" style="color:#4ade80">{rate}%</div><div class="lbl">Pass Rate</div></div>
    """, unsafe_allow_html=True)

    st.caption("Supported: `Run pipeline` · `Run tests` · `Lint only`")

# ── Hero header ───────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <h1>🔧 CI/CD Orchestrator Agent</h1>
  <p>Local pipeline execution with automatic project detection and structured reporting</p>
  <span class="pill">Python</span>
  <span class="pill">Auto-detect</span>
  <span class="pill">Retry</span>
  <span class="pill">Rich Logs</span>
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

        # Auth badge
        whoami = connector.whoami()
        if whoami:
            st.markdown(f'<span class="gh-user-badge">✔ Authenticated as <b>{whoami}</b></span>',
                        unsafe_allow_html=True)
        else:
            st.caption("Using unauthenticated access (60 req/hr limit).")

        st.markdown("<br>", unsafe_allow_html=True)

        # Fetch repo info
        with st.spinner(f"Fetching {gh_owner}/{gh_repo_name}…"):
            try:
                info = connector.get_repo(gh_owner, gh_repo_name)
            except FileNotFoundError:
                st.error(f"Repository `{gh_owner}/{gh_repo_name}` not found on GitHub.")
                st.stop()
            except PermissionError as exc:
                st.error(str(exc))
                st.stop()
            except RuntimeError as exc:
                st.error(str(exc))
                st.stop()

        # Repo card
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

        # Branch selector + goal
        with st.spinner("Fetching branches…"):
            try:
                branches = connector.list_branches(gh_owner, gh_repo_name)
            except Exception:
                branches = [info.default_branch]

        gc1, gc2, gc3 = st.columns([2, 2, 1])
        with gc1:
            selected_branch = st.selectbox("Branch", branches,
                index=branches.index(info.default_branch) if info.default_branch in branches else 0,
                key="gh_branch")
        with gc2:
            GH_GOALS = ["Run pipeline", "Run tests", "Lint only", "Custom..."]
            gh_goal_choice = st.selectbox("Goal", GH_GOALS, key="gh_goal_choice")
            gh_goal = st.text_input("Custom goal", key="gh_custom_goal") if gh_goal_choice == "Custom..." else gh_goal_choice
        with gc3:
            st.markdown("<br>", unsafe_allow_html=True)
            gh_no_cleanup = st.toggle("Skip cleanup", key="gh_no_cleanup")

        clone_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 ".cloned_repos", f"{gh_owner}__{gh_repo_name}")

        clone_run_btn = st.button("🚀  Clone & Run Pipeline", type="primary", key="gh_run_btn")

        if clone_run_btn:
            st.markdown("---")

            # Clone
            with st.status(f"Cloning {info.full_name}@{selected_branch}…", expanded=True) as clone_status:
                result = connector.clone(info, clone_dir, selected_branch)
                if not result.success:
                    clone_status.update(label="Clone failed", state="error")
                    st.error(f"Clone error: {result.error}")
                    st.stop()
                clone_status.update(label=f"Cloned successfully — HEAD {result.commit_sha[:7]}", state="complete")

            if result.commit_sha:
                st.markdown(f'Commit: <span class="commit-badge">{result.commit_sha[:7]}</span>',
                            unsafe_allow_html=True)

            # Analyze & generate
            try:
                gh_config   = ProjectAnalyzer(clone_dir).analyze()
                gh_pipeline = PipelineGenerator(gh_config, goal=gh_goal).generate()
            except Exception as exc:
                st.error(f"Setup failed: {exc}")
                st.stop()

            if not gh_pipeline.steps:
                st.warning("No pipeline steps generated for this repo.")
                st.stop()

            st.markdown('<div class="sec-label">Execution</div>', unsafe_allow_html=True)

            gh_progress = st.progress(0, text="Starting…")
            gh_results, gh_logs, gh_aborted = [], {}, False
            gh_start = time.time()

            for idx, step in enumerate(gh_pipeline.steps, 1):
                gh_progress.progress(
                    int((idx - 1) / len(gh_pipeline.steps) * 100),
                    text=f"Running: {step.name}",
                )
                card    = st.empty()
                log_box = st.empty()
                log_lines, success = [], False

                card.markdown(
                    f'<div class="step-running"><span class="step-title">⚙ {step.name}</span>&nbsp;&nbsp;'
                    f'<span class="step-status-run">● running...</span></div>',
                    unsafe_allow_html=True,
                )

                try:
                    env  = {**os.environ, **step.env}
                    proc = subprocess.Popen(
                        step.command, cwd=step.cwd, env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, encoding="utf-8", errors="replace",
                    )
                    for line in iter(proc.stdout.readline, ""):
                        s = line.rstrip()
                        if s:
                            log_lines.append(s)
                            log_box.markdown(
                                f'<div class="terminal">{chr(10).join(log_lines[-20:])}</div>',
                                unsafe_allow_html=True,
                            )
                    proc.wait()
                    success = proc.returncode == 0
                except Exception as exc:
                    log_lines.append(f"ERROR: {exc}")

                gh_logs[step.name] = "\n".join(log_lines)
                log_box.markdown(
                    f'<div class="terminal">{chr(10).join(log_lines[-20:])}</div>',
                    unsafe_allow_html=True,
                )
                if success:
                    card.markdown(
                        f'<div class="step-pass"><span class="step-title">✔ {step.name}</span>&nbsp;&nbsp;'
                        f'<span class="step-status-pass">● passed</span></div>',
                        unsafe_allow_html=True,
                    )
                else:
                    card.markdown(
                        f'<div class="step-fail"><span class="step-title">✘ {step.name}</span>&nbsp;&nbsp;'
                        f'<span class="step-status-fail">● failed</span></div>',
                        unsafe_allow_html=True,
                    )

                gh_results.append({"Step": step.name, "Status": "PASS" if success else "FAIL"})

                if not success and step.critical:
                    st.error("Critical step failed — pipeline aborted.")
                    gh_aborted = True
                    break

            gh_elapsed = round(time.time() - gh_start, 2)
            gh_progress.progress(100, text="Done.")

            gh_passed = sum(1 for r in gh_results if r["Status"] == "PASS")
            gh_failed = len(gh_results) - gh_passed

            # Post commit status to GitHub
            state = "success" if gh_failed == 0 else "failure"
            desc  = f"{gh_passed}/{len(gh_results)} steps passed in {gh_elapsed}s"
            posted = connector.post_commit_status(
                gh_owner, gh_repo_name, result.commit_sha, state, desc
            )

            # Summary
            st.markdown("---")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Steps",    len(gh_results))
            m2.metric("Passed",   gh_passed)
            m3.metric("Failed",   gh_failed)
            m4.metric("Duration", f"{gh_elapsed}s")

            if gh_failed == 0:
                st.markdown('<div class="banner-pass">✔ All steps passed</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="banner-fail">✘ {gh_failed} step(s) failed</div>', unsafe_allow_html=True)

            if posted:
                st.success(f"Commit status posted to GitHub: **{state}**")

            full_log = "\n\n".join(f"=== {k} ===\n{v}" for k, v in gh_logs.items())
            st.download_button("⬇ Download Log", data=full_log,
                               file_name=f"{gh_repo_name}_{selected_branch}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                               mime="text/plain")

            if not gh_no_cleanup:
                with st.spinner("Cleaning up cloned repo…"):
                    try:
                        ResourceCleaner(clone_dir).clean()
                    except Exception:
                        pass

            # Add to shared history
            st.session_state.total_runs += 1
            if gh_failed == 0:
                st.session_state.total_pass += 1
            st.session_state.run_history.append({
                "Run": st.session_state.total_runs,
                "Repo": info.full_name,
                "Goal": gh_goal,
                "Passed": gh_passed,
                "Failed": gh_failed,
                "Time(s)": gh_elapsed,
                "Result": "PASS" if gh_failed == 0 else "FAIL",
            })

# ════════════════════════════════════════════════════════════════════════════
# LOCAL TAB
# ════════════════════════════════════════════════════════════════════════════
with tab_local:
    # ── Project analysis ─────────────────────────────────────────────────────
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
                ("Python",         config.python_executable, c5),
            ]
            for label, value, col in cards:
                col.markdown(
                    f'<div class="info-card"><div class="val">{value}</div><div class="lbl">{label}</div></div>',
                    unsafe_allow_html=True,
                )

            st.markdown("<br>", unsafe_allow_html=True)

            if goal and goal.strip():
                try:
                    pipeline_preview = PipelineGenerator(config, goal=goal).generate()
                    with st.expander(f"Pipeline Preview — {len(pipeline_preview.steps)} step(s)", expanded=True):
                        items_html = ""
                        for i, step in enumerate(pipeline_preview.steps, 1):
                            badge = '<span class="badge-c">CRITICAL</span>' if step.critical else '<span class="badge-o">OPTIONAL</span>'
                            cmd   = " ".join(step.command)
                            items_html += f'<div class="tl-item"><div class="tl-dot"></div><div class="tl-name">{i}. {step.name} {badge}</div><div class="tl-cmd">{cmd}</div></div>'
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

        total_steps  = len(pipeline.steps)
        progress_bar = st.progress(0, text="Starting pipeline...")
        results, run_logs, aborted = [], {}, False
        start_time = time.time()

        for idx, step in enumerate(pipeline.steps, 1):
            progress_bar.progress(int((idx - 1) / total_steps * 100), text=f"Running: {step.name}")
            card, log_box = st.empty(), st.empty()
            log_lines, success = [], False

            card.markdown(
                f'<div class="step-running"><span class="step-title">⚙ {step.name}</span>&nbsp;&nbsp;'
                f'<span class="step-status-run">● running...</span></div>',
                unsafe_allow_html=True,
            )

            try:
                env  = {**os.environ, **step.env}
                proc = subprocess.Popen(
                    step.command, cwd=step.cwd, env=env,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                )
                for line in iter(proc.stdout.readline, ""):
                    s = line.rstrip()
                    if s:
                        log_lines.append(s)
                        log_box.markdown(
                            f'<div class="terminal">{chr(10).join(log_lines[-20:])}</div>',
                            unsafe_allow_html=True,
                        )
                proc.wait()
                success = proc.returncode == 0
            except FileNotFoundError as exc:
                log_lines.append(f"ERROR: command not found — {exc}")
            except Exception as exc:
                log_lines.append(f"ERROR: {exc}")

            run_logs[step.name] = "\n".join(log_lines)
            log_box.markdown(
                f'<div class="terminal">{chr(10).join(log_lines[-20:])}</div>',
                unsafe_allow_html=True,
            )

            if success:
                card.markdown(
                    f'<div class="step-pass"><span class="step-title">✔ {step.name}</span>&nbsp;&nbsp;'
                    f'<span class="step-status-pass">● passed</span></div>',
                    unsafe_allow_html=True,
                )
            else:
                card.markdown(
                    f'<div class="step-fail"><span class="step-title">✘ {step.name}</span>&nbsp;&nbsp;'
                    f'<span class="step-status-fail">● failed</span></div>',
                    unsafe_allow_html=True,
                )

            results.append({
                "Step":     step.name,
                "Status":   "PASS" if success else "FAIL",
                "Critical": "Yes"  if step.critical else "No",
                "Retries":  step.max_retries,
            })

            if not success and step.critical:
                st.error("Critical step failed — pipeline aborted.")
                aborted = True
                break

        elapsed = round(time.time() - start_time, 2)
        progress_bar.progress(100, text="Pipeline complete.")

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="sec-label">Summary</div>', unsafe_allow_html=True)

        passed = sum(1 for r in results if r["Status"] == "PASS")
        failed = len(results) - passed

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Steps", total_steps)
        m2.metric("Passed",      passed)
        m3.metric("Failed",      failed)
        m4.metric("Duration",    f"{elapsed}s")

        left, right = st.columns([3, 2])
        with left:
            df = pd.DataFrame(results)
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

        if failed == 0:
            st.markdown('<div class="banner-pass">✔ All steps passed — pipeline successful</div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="banner-fail">✘ {failed} step(s) failed{"  — pipeline aborted" if aborted else ""}</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        full_log = "\n\n".join(f"=== {k} ===\n{v}" for k, v in run_logs.items())
        st.download_button("⬇ Download Full Log", data=full_log,
                           file_name=f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
                           mime="text/plain")

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
        st.session_state.run_history.append({
            "Run":    st.session_state.total_runs,
            "Repo":   os.path.basename(abs_path),
            "Goal":   goal,
            "Passed": passed,
            "Failed": failed,
            "Time(s)": elapsed,
            "Result": "PASS" if failed == 0 else "FAIL",
        })

# ── Run History (shared across tabs) ─────────────────────────────────────────
if st.session_state.run_history:
    st.markdown("---")
    st.markdown('<div class="sec-label">Run History</div>', unsafe_allow_html=True)

    hist_df = pd.DataFrame(st.session_state.run_history)
    col_chart, col_table = st.columns([2, 3])

    with col_chart:
        bar_data = hist_df.melt(id_vars="Run", value_vars=["Passed","Failed"],
                                var_name="Status", value_name="Count")
        bar = (
            alt.Chart(bar_data)
            .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
            .encode(
                x=alt.X("Run:O", title="Run #", axis=alt.Axis(labelColor="#94a3b8", titleColor="#94a3b8")),
                y=alt.Y("Count:Q", title="Steps", axis=alt.Axis(labelColor="#94a3b8", titleColor="#94a3b8")),
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
        st.dataframe(hist_df.style.map(_row_color, subset=["Result"]),
                     use_container_width=True, hide_index=True)
