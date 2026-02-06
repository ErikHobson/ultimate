
import json
from typing import List, Dict
import pandas as pd
import streamlit as st
from ultimate_logger import UltimateStatLogger, other_team

st.set_page_config(page_title="Ultimate Stat Logger", page_icon="🫏", layout="wide")

# ---------------------------
# Session State Initialization
# ---------------------------

def init_state():
    if "logger" not in st.session_state:
        # Simple defaults; you can paste/override in the sidebar
        A = []
        B = []
        st.session_state.logger = UltimateStatLogger(onfield_A=A, onfield_B=B)
    if "team_names" not in st.session_state:
        st.session_state.team_names = {"A": "Team Light", "B": "Team Dark"}
    if "roster_lists" not in st.session_state:
        # Start each roster as the current on-field 5; you can add more below
        st.session_state.roster_lists = {
            "A": list(st.session_state.logger.onfield["A"]),
            "B": list(st.session_state.logger.onfield["B"]),
        }
    if "rosters_text" not in st.session_state:
        st.session_state.rosters_text = {
            "A": "\n".join(st.session_state.roster_lists["A"]),
            "B": "\n".join(st.session_state.roster_lists["B"]),
        }

init_state()
logger = st.session_state.logger

# ---------------------------
# Small helpers
# ---------------------------

def _sync_rosters_text():
    st.session_state.rosters_text = {
        "A": "\n".join(st.session_state.roster_lists["A"]),
        "B": "\n".join(st.session_state.roster_lists["B"]),
    }

# ---------------------------
# Sidebar Controls
# ---------------------------

st.sidebar.header("⚙️ Setup")
st.sidebar.write("Manage team names, rosters, and on-field lineups.")

with st.sidebar.expander("Team Names", expanded=False):
    name_A = st.text_input("Team Light label", value=st.session_state.team_names["A"], key="nmA")
    name_B = st.text_input("Team Dark label", value=st.session_state.team_names["B"], key="nmB")
    st.session_state.team_names = {"A": name_A, "B": name_B}

with st.sidebar.expander("Roster Manager", expanded=True):
    st.caption("Add/remove/reorder players. Then set the on-field 5.")

    for team_key in ("A", "B"):
        st.subheader(f"{st.session_state.team_names[team_key]} roster")
        roster: List[str] = st.session_state.roster_lists[team_key]

        # Show current roster with up/down/remove
        i = 0
        while i < len(roster):
            p = roster[i]
            cols = st.columns([6,1,1,1])
            with cols[0]:
                st.text_input(
                    label=f"{team_key}_name_{i}",
                    value=p,
                    key=f"{team_key}_display_{i}",
                    label_visibility="collapsed",
                    disabled=True,
                )
            with cols[1]:
                if st.button("▲", key=f"{team_key}_up_{i}") and i > 0:
                    roster[i-1], roster[i] = roster[i], roster[i-1]
                    _sync_rosters_text()
                    st.rerun()
            with cols[2]:
                if st.button("▼", key=f"{team_key}_down_{i}") and i < len(roster)-1:
                    roster[i+1], roster[i] = roster[i], roster[i+1]
                    _sync_rosters_text()
                    st.rerun()
            with cols[3]:
                if st.button("🗑", key=f"{team_key}_del_{i}"):
                    removed = roster.pop(i)
                    # If removed player is currently on-field, leave a gap (handled when applying on-field)
                    _sync_rosters_text()
                    st.rerun()
            i += 1

        # Add new player
        add_cols = st.columns([3,1])
        with add_cols[0]:
            new_name = st.text_input(f"Add player to {st.session_state.team_names[team_key]}", key=f"add_{team_key}")
        with add_cols[1]:
            if st.button("Add", key=f"addbtn_{team_key}"):
                nm = (new_name or "").strip()
                if nm and nm not in roster:
                    roster.append(nm)
                    _sync_rosters_text()
                    st.rerun()

        # On-field selection
        st.markdown("**Set on-field**")
        oc1, oc2 = st.columns(2)
        with oc1:
            if st.button("Use first 5", key=f"first5_{team_key}"):
                if len(roster) < 5:
                    st.error("Need at least 5 players.")
                else:
                    logger.onfield[team_key] = roster[:5]
                    st.success("On-field set to first 5.")
        with oc2:
            # Custom 5 selection
            opts = roster
            default = [p for p in logger.onfield[team_key] if p in opts]
            chosen = st.multiselect(
                f"{st.session_state.team_names[team_key]}: pick exactly 5",
                options=opts,
                default=default,
                key=f"pick5_{team_key}"
            )
            if st.button("Apply 5", key=f"apply5_{team_key}"):
                if len(chosen) != 5:
                    st.error("Select exactly 5 players.")
                else:
                    logger.onfield[team_key] = list(chosen)
                    st.success("On-field updated.")

st.sidebar.divider()
# Always-on CSV download for current events
csv_data = pd.DataFrame(logger.events).to_csv(index=False).encode("utf-8")
st.sidebar.download_button(
    "Save game_log.csv",
    data=csv_data,
    file_name="game_log.csv",
    mime="text/csv",
    disabled=not logger.events
)

# ---------------------------
# Header / Status
# ---------------------------

c1, c2, c3, c4 = st.columns([2,2,2,2])
with c1:
    st.markdown(f"### 🫏 Point: **{logger.point_number}**")
with c2:
    poss = logger.possession_team if logger.possession_team else ("— awaiting pull —" if logger.await_pull else "—")
    if poss in ("A","B"):
        st.markdown(f"### Possession: **{st.session_state.team_names[poss]}**")
    else:
        st.markdown(f"### Possession: {poss}")
with c3:
    txt = "Sub Mode: **Select OUT**, then **IN**" if logger.sub_mode else "Sub Mode: off"
    st.markdown(f"### {txt}")
with c4:
    st.markdown("### Events logged: **{}**".format(len(logger.events)))

st.divider()

# ---------------------------
# Action Buttons Row
# ---------------------------

bcol1, bcol2, bcol3, bcol4, bcol5, bcol6, bcol5 = st.columns([1.2,1.2,1.2,1.2,1.2,1.2,1.2])
with bcol1:
    if st.button("Score", use_container_width=True):
        try:
            logger.press_score()
        except Exception as e:
            st.error(str(e))
with bcol2:
    if st.button("Drop", use_container_width=True):
        try:
            logger.press_drop()
        except Exception as e:
            st.error(str(e))
with bcol3:
    if st.button("Turn", use_container_width=True):
        try:
            logger.press_turn()
        except Exception as e:
            st.error(str(e))
with bcol4:
    if st.button("Pull", use_container_width=True):
        try:
            logger.press_pull()
        except Exception as e:
            st.error(str(e))
with bcol5:
    if st.button("Sub", use_container_width=True):
        logger.start_sub()
with bcol6:
    if st.button("Undo last", use_container_width=True):
        logger.undo_last(1)
with bcol5:
    if st.button("Reset session", use_container_width=True):
        st.session_state.clear()
        st.rerun()

st.divider()

# ---------------------------
# Player Grids
# ---------------------------

def render_team_grid(team_key: str):
    team_name = st.session_state.team_names[team_key]
    players = logger.onfield[team_key]
    st.markdown(f"#### {team_name} (click player)")

    # 3 columns for big touch targets
    cols = st.columns(3)
    for i, p in enumerate(players):
        with cols[i % 3]:
            if st.button(p, key=f"{team_key}_{p}", use_container_width=True):
                try:
                    created = logger.click_player(team_key, p)
                    for row in created:
                        st.toast(f"{row['Event']} — {row['Team']} {row['From']}{' → ' + row['To'] if row['To'] else ''}")
                except Exception as e:
                    st.error(str(e))

    # Bench for IN step during Sub mode (same team as OUT)
    if logger.sub_mode and logger.sub_out is not None and logger.sub_out.team == team_key:
        full_roster = st.session_state.roster_lists[team_key]
        bench = [p for p in full_roster if p not in logger.onfield[team_key]]
        if bench:
            st.caption("Bench (click to sub IN)")
            bench_cols = st.columns(3)
            for i, p in enumerate(bench):
                with bench_cols[i % 3]:
                    if st.button(p, key=f"{team_key}_bench_{p}", use_container_width=True):
                        try:
                            created = logger.click_player(team_key, p)  # Sub mode routes to IN
                            for row in created:
                                st.toast(f"{row['Event']} — {row['Team']} {row['From']}{' → ' + row['To'] if row['To'] else ''}")
                        except Exception as e:
                            st.error(str(e))

lcol, rcol = st.columns(2)
with lcol:
    render_team_grid("A")
with rcol:
    render_team_grid("B")

st.divider()

# ---------------------------
# Log Table
# ---------------------------

st.markdown("### Event Log")
if logger.events:
    df = pd.DataFrame(logger.events)
    st.dataframe(df, use_container_width=True, hide_index=True)
else:
    st.info("No events yet. Click players and use buttons above.")

# ---------------------------
# Helper Tips
# ---------------------------

with st.expander("How to use (quick recap)"):
    st.markdown(
        """
- **PASS**: click same-team consecutive players.
- **Cross-team click**: auto `TURN` (on thrower) + `D` (to clicked defender).
- **Drop**: click the dropper, then **Drop**. (Revokes the just-logged PASS to that receiver, if any.)
- **Turn**: click the thrower, then **Turn** (no D). Next click must be other team to set holder.
- **Score**: click the scoring receiver, then **Score**. Increments point; expect a **Pull** next.
- **Pull**: click the puller, then **Pull**. First receiving click sets holder (no PASS).
- **Sub**: press **Sub** → click **OUT** → click **IN**. Logged as `SUB` with on-field snapshots.
        """
    )
