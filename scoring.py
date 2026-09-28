import csv
import requests
import dotenv
import os

# ── Constants ────────────────────────────────────────────────────────────────
dotenv.load_dotenv()

TBA_API_KEY     = os.getenv("TBA_API_KEY", "")
EVENT_CODE      = "2026njrr"

INPUT_FILE      = f"./drafts/{EVENT_CODE}.csv"
OUTPUT_FILE     = f"./scores/{EVENT_CODE}_output.csv"

PTS_QUAL_WIN    = 3
PTS_QUAL_TIE    = 1
PTS_PLAYOFF_WIN = 5

# SLFF table: alliance rank (1-8) → {Captain, 1st Pick, 2nd Pick}
# Backup teams are NOT in this table — they receive no alliance selection bonus.
SLFF = {
    1: {"Captain": 16, "1st Pick": 16, "2nd Pick": 1},
    2: {"Captain": 15, "1st Pick": 15, "2nd Pick": 2},
    3: {"Captain": 14, "1st Pick": 14, "2nd Pick": 3},
    4: {"Captain": 13, "1st Pick": 13, "2nd Pick": 4},
    5: {"Captain": 12, "1st Pick": 12, "2nd Pick": 5},
    6: {"Captain": 11, "1st Pick": 11, "2nd Pick": 6},
    7: {"Captain": 10, "1st Pick": 10, "2nd Pick": 7},
    8: {"Captain":  9, "1st Pick":  9, "2nd Pick": 8},
}

# ── TBA helpers ──────────────────────────────────────────────────────────────

TBA_BASE = "https://www.thebluealliance.com/api/v3"
HEADERS  = {"X-TBA-Auth-Key": TBA_API_KEY}

def tba_get(path):
    r = requests.get(f"{TBA_BASE}{path}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

# ── Input parsing ────────────────────────────────────────────────────────────

PARTICIPANT_COL = "Participant"
PICK_COL_PREFIX = "Pick #"

def parse_input(path):
    """
    Return a list of dicts: [{"name": str, "picks": [int, ...]}, ...]
    Ignores any column whose header doesn't match the known structure.
    Ignores non-contiguous row blocks outside the participant table.
    """
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))

    # Find the header row containing "Participant"
    header_row_idx = None
    participant_col_idx = None
    for i, row in enumerate(rows):
        for j, cell in enumerate(row):
            if cell.strip() == PARTICIPANT_COL:
                header_row_idx = i
                participant_col_idx = j
                break
        if header_row_idx is not None:
            break

    if header_row_idx is None:
        raise ValueError("Could not find 'Participant' header in input CSV")

    header = rows[header_row_idx]

    # Identify pick columns by header name
    pick_cols = []  # list of (col_index, pick_number)
    for j, cell in enumerate(header):
        cell = cell.strip()
        if cell.startswith(PICK_COL_PREFIX):
            try:
                num = int(cell[len(PICK_COL_PREFIX):])
                pick_cols.append((j, num))
            except ValueError:
                pass
    pick_cols.sort(key=lambda x: x[1])

    # Read contiguous participant rows; stop at the first blank Participant cell
    participants = []
    started = False
    for row in rows[header_row_idx + 1:]:
        if len(row) <= participant_col_idx: # type: ignore
            if started:
                break
            continue
        name = row[participant_col_idx].strip() # type: ignore
        if not name:
            if started:
                break
            continue
        started = True
        picks = []
        for col_idx, _ in pick_cols:
            if col_idx < len(row) and row[col_idx].strip():
                try:
                    picks.append(int(row[col_idx].strip()))
                except ValueError:
                    pass
        participants.append({"name": name, "picks": picks})

    return participants

# ── TBA data fetching ────────────────────────────────────────────────────────

PLAYOFF_LEVELS = {"ef", "qf", "sf", "f"}

def fetch_matches(event_code):
    """Fetch all matches once and return the raw list."""
    return tba_get(f"/event/{event_code}/matches")

def calc_qual_stats(matches):
    """
    Return {team_number: {"wins": int, "ties": int}} from qual matches.

    Rules:
    - Surrogate teams (surrogateTeamKeys) get NO points for that match,
      even if their alliance won.
    - DQ'd teams (dqTeamKeys) get NO points for that match.
      Their alliance teammates are unaffected and score normally.
    - Ties award PTS_QUAL_TIE to all eligible teams on both alliances.
    - Playoff ties cannot occur and are skipped (winning_alliance == "").
    """
    stats = {}

    for m in matches:
        if m.get("comp_level") != "qm":
            continue

        alliances        = m.get("alliances", {})
        winning_alliance = m.get("winning_alliance") or ""  # "" = tie, None safety

        for color in ("red", "blue"):
            alliance         = alliances.get(color, {})
            team_keys        = alliance.get("team_keys", [])
            surrogate_keys   = set(alliance.get("surrogate_team_keys", []))
            dq_keys          = set(alliance.get("dq_team_keys", []))

            if winning_alliance == "":
                result = "tie"
            elif winning_alliance == color:
                result = "win"
            else:
                result = "loss"

            for tk in team_keys:
                # Surrogates and DQ'd teams earn nothing for this match
                if tk in surrogate_keys or tk in dq_keys:
                    continue

                team_num = int(tk.replace("frc", ""))
                if team_num not in stats:
                    stats[team_num] = {"wins": 0, "ties": 0}

                if result == "win":
                    stats[team_num]["wins"] += 1
                elif result == "tie":
                    stats[team_num]["ties"] += 1

    return stats

def calc_playoff_wins(matches):
    """
    Return {team_number: int} counting playoff match wins.

    Rules:
    - Only teams on the winning alliance score.
    - DQ'd teams on the winning alliance get no points for that match.
      Their alliance teammates score normally.
    - Surrogate teams on the winning alliance get no points for that match.
    - Playoff ties are impossible; a blank winning_alliance means unplayed — skip.
    - Backup teams appear in team_keys just like normal members once called in,
      so they score naturally here. They receive no SLFF bonus (handled separately).
    """
    wins = {}

    for m in matches:
        if m.get("comp_level") not in PLAYOFF_LEVELS:
            continue

        winning_alliance = m.get("winning_alliance") or ""
        if not winning_alliance:
            continue  # unplayed or no result yet

        alliances      = m.get("alliances", {})
        alliance       = alliances.get(winning_alliance, {})
        team_keys      = alliance.get("team_keys", [])
        surrogate_keys = set(alliance.get("surrogate_team_keys", []))
        dq_keys        = set(alliance.get("dq_team_keys", []))

        for tk in team_keys:
            if tk in surrogate_keys or tk in dq_keys:
                continue
            team_num = int(tk.replace("frc", ""))
            wins[team_num] = wins.get(team_num, 0) + 1

    return wins

def fetch_alliance_bonuses(event_code):
    """
    Return {team_number: int} SLFF bonus for alliance-selected teams only.

    TBA returns alliances ordered by rank (index 0 = alliance 1).
    Each alliance dict has:
      "picks":  [captain_key, 1st_pick_key, 2nd_pick_key]
      "backup": {"out": "frcXXX", "in": "frcYYY"} or null

    Backup teams ("in") are explicitly excluded — they were not part of
    alliance selection and receive no SLFF bonus.
    """
    alliances = tba_get(f"/event/{event_code}/alliances")
    bonuses = {}

    for rank_idx, alliance in enumerate(alliances):
        alliance_rank = rank_idx + 1  # 1-based
        if alliance_rank not in SLFF:
            continue

        picks     = alliance.get("picks", [])
        positions = ["Captain", "1st Pick", "2nd Pick"]

        # Identify backup team key so we can skip it if it somehow appears in picks
        backup    = alliance.get("backup") or {}
        backup_in = backup.get("in", "")

        for pos_idx, tk in enumerate(picks[:3]):
            if tk == backup_in:
                # Safety guard: backup replaced a pick slot, skip SLFF for them
                continue
            team_num = int(tk.replace("frc", ""))
            position = positions[pos_idx]
            bonuses[team_num] = SLFF[alliance_rank][position]

    return bonuses

# ── Scoring ──────────────────────────────────────────────────────────────────

def build_team_points(event_code):
    """Return {team_number: int} total points for every team at the event."""
    matches        = fetch_matches(event_code)   # single API call
    qual_stats     = calc_qual_stats(matches)
    playoff_wins   = calc_playoff_wins(matches)
    alliance_bonus = fetch_alliance_bonuses(event_code)

    all_teams = set(qual_stats) | set(playoff_wins) | set(alliance_bonus)
    team_points = {}
    for team in all_teams:
        qs   = qual_stats.get(team, {"wins": 0, "ties": 0})
        pts  = qs["wins"] * PTS_QUAL_WIN
        pts += qs["ties"] * PTS_QUAL_TIE
        pts += playoff_wins.get(team, 0) * PTS_PLAYOFF_WIN
        pts += alliance_bonus.get(team, 0)
        team_points[team] = pts

    return team_points

def score_participants(participants, team_points):
    """Attach points_per_pick and total to each participant dict, sorted descending."""
    for p in participants:
        ppp = [team_points.get(pick, 0) for pick in p["picks"]]
        p["points_per_pick"] = ppp
        p["total"] = sum(ppp)
    participants.sort(key=lambda x: x["total"], reverse=True)
    return participants

# ── Output ───────────────────────────────────────────────────────────────────

def write_output(path, participants):
    """
    Write CSV matching the output format exactly, including empty spacing columns.

    Layout (0-indexed columns):
      0:        ""  (leading empty)
      1:        Participant
      2..N:     Pick #1, Pick #2, ... Pick #K
      N+1:      ""  (separator)
      N+2..M:   Points per Pick (one column per pick; only first column has header)
      M+1:      ""
      M+2:      ""
      M+3:      Total
    """
    if not participants:
        return

    num_picks     = max(len(p["picks"]) for p in participants)
    pick_headers  = [f"Pick #{i + 1}" for i in range(num_picks)]
    point_headers = ["Points per Pick"] + [""] * (num_picks - 1)

    header = ["", "Participant"] + pick_headers + [""] + point_headers + ["", "", "Total"]

    rows = [header]
    for p in participants:
        picks_padded  = p["picks"]           + [""] * (num_picks - len(p["picks"]))
        points_padded = p["points_per_pick"] + [""] * (num_picks - len(p["points_per_pick"]))
        row = (
            ["", p["name"]]
            + [str(x) for x in picks_padded]
            + [""]
            + [str(x) for x in points_padded]
            + ["", "", str(p["total"])]
        )
        rows.append(row)

    max_width = max(len(r) for r in rows)
    rows = [r + [""] * (max_width - len(r)) for r in rows]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([""] * max_width)  # blank leading row (matches input style)
        writer.writerows(rows)

# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Parsing input CSV...")
    participants = parse_input(INPUT_FILE)
    print(f"  Found {len(participants)} participants.")

    print("Fetching TBA data...")
    team_points = build_team_points(EVENT_CODE)
    print(f"  Scored {len(team_points)} teams.")

    print("Scoring participants...")
    participants = score_participants(participants, team_points)

    print("Writing output CSV...")
    write_output(OUTPUT_FILE, participants)
    print(f"  Done → {OUTPUT_FILE}")

if __name__ == "__main__":
    main()