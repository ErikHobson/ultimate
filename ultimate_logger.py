
from __future__ import annotations
import json
from dataclasses import dataclass
from datetime import datetime
from typing import List, Dict, Optional, Literal, Tuple

TeamKey = Literal["A", "B"]

def now_iso() -> str:
    """Local wall time with timezone offset, second precision."""
    return datetime.now().astimezone().isoformat(timespec="seconds")

def other_team(team: TeamKey) -> TeamKey:
    return "B" if team == "A" else "A"

@dataclass
class PlayerRef:
    team: TeamKey
    name: str

class UltimateStatLogger:
    """
    Events:
    - P : Pull (click puller, then press P)
    - PASS : Auto on same-team consecutive clicks (From last holder → clicked player)
    - TURN : Auto on cross-team click (on thrower) OR manual Turn button after clicking thrower
    - D : Auto on cross-team click awarded to clicked defender (who takes possession)
    - O : Drop (click dropper, then press O) — no D; flips possession
    - S : Score (click scoring receiver, then press S) — increments point number
    - SUB : Substitution (press Sub → click OUT → click IN)

    CSV schema:
    ["Timestamp","Team","Event","Point","From","To","OnFieldTeamA","OnFieldTeamB"]
    """

    HEADER = ["Timestamp","Team","Event","Point","From","To","OnFieldTeamA","OnFieldTeamB"]

    def __init__(
        self,
        onfield_A: List[str],
        onfield_B: List[str],
        team_names: Optional[Dict[TeamKey, str]] = None,
    ) -> None:
        self.team_names = team_names or {"A": "A", "B": "B"}
        self.onfield: Dict[TeamKey, List[str]] = {
            "A": list(onfield_A),
            "B": list(onfield_B),
        }
        # Logging buffer
        self.events: List[Dict[str, str]] = []

        # Game/point state
        self.point_number: int = 1
        self.possession_team: Optional[TeamKey] = None
        self.last_holder: Optional[PlayerRef] = None
        self.last_throw: Optional[Tuple[PlayerRef, PlayerRef]] = None

        # UI helpers
        self.last_clicked: Optional[PlayerRef] = None
        self.await_new_holder_team: Optional[TeamKey] = None  # after O/manual TURN/P
        self.sub_mode: bool = False
        self.sub_out: Optional[PlayerRef] = None
        self.await_pull: bool = False  # after S

    # ---------------------------
    # Public API (UI actions)
    # ---------------------------
    def click_player(self, team: TeamKey, player: str) -> List[Dict[str, str]]:
        """Handle a player click per agreed rules."""
        p = PlayerRef(team=team, name=player)
        self.last_clicked = p
        created: List[Dict[str, str]] = []

        # Substitution flow
        if self.sub_mode:
            return self._handle_sub_click(p)

        # Awaiting new holder after O / manual TURN / P
        if self.await_new_holder_team is not None:
            if p.team != self.await_new_holder_team:
                return created  # ignore wrong team click
            self.possession_team = p.team
            self.last_holder = p
            self.last_throw = None
            self.await_new_holder_team = None
            return created

        # Post-score, awaiting a Pull
        if self.await_pull:
            return created

        # Start of point / first holder (if not after Pull)
        if self.possession_team is None and self.last_holder is None:
            self.possession_team = p.team
            self.last_holder = p
            self.last_throw = None
            return created

        # Ignore self-click
        if self.last_holder and p.team == self.possession_team and p.name == self.last_holder.name:
            return created

        # Same-team → PASS
        if self.last_holder and p.team == self.possession_team:
            row = self._make_row(
                team=self.possession_team,
                event="PASS",
                from_name=self.last_holder.name,
                to_name=p.name,
            )
            self.events.append(row)
            created.append(row)
            self.last_throw = (self.last_holder, p)
            self.last_holder = p
            return created

        # Cross-team → TURN (thrower) + D (clicked defender), flip possession
        if self.last_holder and p.team != self.possession_team:
            turn_row = self._make_row(
                team=self.possession_team,
                event="TURN",
                from_name=self.last_holder.name,
                to_name="",
            )
            self.events.append(turn_row)
            created.append(turn_row)

            d_row = self._make_row(
                team=p.team,
                event="D",
                from_name=p.name,
                to_name="",
            )
            self.events.append(d_row)
            created.append(d_row)

            self.possession_team = p.team
            self.last_holder = p
            self.last_throw = None
            return created

        # Fallback
        if self.last_holder is None:
            self.possession_team = p.team
            self.last_holder = p
            return created

    def press_score(self) -> Dict[str, str]:
        """Click scoring receiver, then press S. Increments point and resets to await P."""
        if self.possession_team is None:
            raise ValueError("Cannot score: no possession/team context.")
        if self.last_clicked is None:
            raise ValueError("Click the scoring receiver, then press S.")

        thrower: Optional[PlayerRef] = None
        receiver: Optional[PlayerRef] = None

        if self.last_throw:
            thrower, receiver = self.last_throw
        elif self.last_holder and self.last_clicked.team == self.possession_team:
            thrower = self.last_holder
            receiver = self.last_clicked
        else:
            raise ValueError("Cannot resolve thrower/receiver for S. Click a receiver on the possession team.")

        row = self._make_row(
            team=self.possession_team,
            event="S",
            from_name=thrower.name if thrower else "",
            to_name=receiver.name if receiver else "",
        )
        self.events.append(row)

        # End point
        self.point_number += 1
        self.possession_team = None
        self.last_holder = None
        self.last_throw = None
        self.await_new_holder_team = None
        self.await_pull = True
        return row

    def press_drop(self) -> Dict[str, str]:
        """Click dropping receiver, then press O. Revokes trailing PASS to that receiver (if any)."""
        if self.possession_team is None or self.last_clicked is None:
            raise ValueError("Click the dropping receiver (possession team) before pressing O.")
        dropper = self.last_clicked
        if dropper.team != self.possession_team:
            raise ValueError("Dropper must be on the team in possession.")

        # Revoke trailing PASS if it targeted this receiver
        if self.events and self.events[-1]["Event"] == "PASS":
            last = self.events[-1]
            if last["Team"] == self.possession_team and last["To"] == dropper.name:
                self.events.pop()
                thrower_name = last["From"]
                self.last_holder = PlayerRef(team=self.possession_team, name=thrower_name)
                self.last_throw = None

        row = self._make_row(
            team=self.possession_team,
            event="O",
            from_name=dropper.name,
            to_name="",
        )
        self.events.append(row)

        # Flip possession and require next click be opposite team
        self.await_new_holder_team = other_team(self.possession_team)
        self.possession_team = other_team(self.possession_team)
        self.last_holder = None
        self.last_throw = None
        return row

    def press_turn(self) -> Dict[str, str]:
        """Manual turf/throwaway to nobody: press after clicking thrower. No D is logged."""
        if self.possession_team is None or self.last_holder is None:
            raise ValueError("Click the thrower (current holder) before pressing Turn.")

        row = self._make_row(
            team=self.possession_team,
            event="TURN",
            from_name=self.last_holder.name,
            to_name="",
        )
        self.events.append(row)

        self.await_new_holder_team = other_team(self.possession_team)
        self.possession_team = other_team(self.possession_team)
        self.last_holder = None
        self.last_throw = None
        return row

    def press_pull(self) -> Dict[str, str]:
        """Click puller, then press P. Receiving team will be set on their first holder click."""
        if self.last_clicked is None:
            raise ValueError("Click the puller, then press P.")
        puller = self.last_clicked

        row = self._make_row(
            team=puller.team,
            event="P",
            from_name=puller.name,
            to_name="",
        )
        self.events.append(row)

        self.possession_team = None
        self.last_holder = None
        self.last_throw = None
        self.await_new_holder_team = other_team(puller.team)
        self.await_pull = False
        return row

    def start_sub(self) -> None:
        """Enter substitution mode (Sub → OUT → IN)."""
        self.sub_mode = True
        self.sub_out = None

    def undo_last(self, n: int = 1) -> None:
        """Remove last n events (does not rewind internal state)."""
        for _ in range(min(n, len(self.events))):
            self.events.pop()

    def save_csv(self, path: str) -> None:
        """Write events to CSV."""
        fieldnames = self.HEADER
        with open(path, "w", newline="", encoding="utf-8") as f:
            import csv as _csv
            writer = _csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.events:
                writer.writerow(row)

    # ---------------------------
    # Internal helpers
    # ---------------------------
    def _handle_sub_click(self, p: PlayerRef) -> List[Dict[str, str]]:
        created: List[Dict[str, str]] = []
        # OUT
        if self.sub_out is None:
            if p.name not in self.onfield[p.team]:
                raise ValueError(f"Player '{p.name}' is not currently on-field for team {p.team}.")
            self.sub_out = p
            return created
        # IN
        if p.team != self.sub_out.team:
            raise ValueError("Substitution must be within the same team.")
        if p.name in self.onfield[p.team]:
            raise ValueError(f"Player '{p.name}' is already on-field for team {p.team}.")
        team = p.team
        self._apply_sub(team, self.sub_out.name, p.name)
        row = self._make_row(
            team=team,
            event="SUB",
            from_name=self.sub_out.name,
            to_name=p.name,
        )
        self.events.append(row)
        created.append(row)
        self.sub_mode = False
        self.sub_out = None
        return created

    def _apply_sub(self, team: TeamKey, out_player: str, in_player: str) -> None:
        if out_player not in self.onfield[team]:
            raise ValueError(f"Cannot sub out '{out_player}': not on-field for team {team}.")
        idx = self.onfield[team].index(out_player)
        self.onfield[team][idx] = in_player
        if self.last_holder and self.last_holder.team == team and self.last_holder.name == out_player:
            self.last_holder = None

    def _make_row(self, team: TeamKey, event: str, from_name: str, to_name: str) -> Dict[str, str]:
        return {
            "Timestamp": now_iso(),
            "Team": team,
            "Event": event,
            "Point": str(self.point_number),
            "From": from_name or "",
            "To": to_name or "",
            "OnFieldTeamA": json.dumps(self.onfield["A"], ensure_ascii=False),
            "OnFieldTeamB": json.dumps(self.onfield["B"], ensure_ascii=False),
        }
