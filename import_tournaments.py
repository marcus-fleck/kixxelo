#!/usr/bin/env python3
"""
Tournament.app -> SQLite Import + ELO Berechnung

Holt alle Sado/Mido/Samstagsdoppel/Mittwochsdoppel Turniere von der API,
schreibt Matches in die DB und berechnet ELO-Ratings (nur Doppel).

Verwendung:
  python3 import_tournaments.py --token-file token --db neue.db
  python3 import_tournaments.py --token-file token --db neue.db --dry-run
  python3 import_tournaments.py --token-file token --db neue.db --year 2025
"""

import argparse
import sqlite3
import requests
import sys
import re
from datetime import datetime

BASE_URL = "https://api.tournament.io/v1/public"
TOURNAMENT_FILTER = re.compile(r"sado|mido|samstagsdoppel|mittwochsdoppel|einzel", re.IGNORECASE)

K = 24
START_RATING = 1000.0

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = """
CREATE TABLE IF NOT EXISTS competitions (
    id integer NOT NULL,
    tfvbId integer NOT NULL,
    type integer,
    name text,
    year integer,
    month integer,
    day integer,
    unixTimestamp,
    tioId text UNIQUE,
    primary key (id)
);
CREATE TABLE IF NOT EXISTS players (
    id integer NOT NULL,
    firstName text NOT NULL,
    lastName text NOT NULL,
    primary key (id)
);
CREATE TABLE IF NOT EXISTS matches (
    id integer NOT NULL,
    competition_id integer NOT NULL,
    position integer,
    type integer,
    score1 integer,
    score2 integer,
    p1 integer NOT NULL,
    p2 integer NOT NULL,
    p11 integer NOT NULL,
    p22 integer NOT NULL,
    primary key (id),
    constraint fk_matches_competition foreign key (competition_id)
        references competitions (id) deferrable initially deferred
);
CREATE TABLE IF NOT EXISTS played_matches (
    id integer NOT NULL,
    player_id integer NOT NULL,
    match_id integer,
    primary key (id),
    constraint fk_played_matches_player foreign key (player_id)
        references players (id) deferrable initially deferred,
    constraint fk_played_matches_match foreign key (match_id)
        references matches (id) deferrable initially deferred
);
CREATE TABLE IF NOT EXISTS elo_separate (
    played_match_id integer NOT NULL,
    rating smallint NOT NULL,
    change smallint NOT NULL,
    primary key (played_match_id)
);
CREATE TABLE IF NOT EXISTS elo_combined (
    played_match_id integer NOT NULL,
    rating smallint NOT NULL,
    change smallint NOT NULL,
    primary key (played_match_id)
);
CREATE TABLE IF NOT EXISTS elo_current (
    player_id integer NOT NULL,
    single smallint NOT NULL,
    double smallint NOT NULL,
    combined smallint NOT NULL,
    primary key (player_id)
);
CREATE TABLE IF NOT EXISTS player_vs_player_stats (
    player_id integer NOT NULL,
    other_id integer NOT NULL,
    single_wins smallint NOT NULL,
    single_draws smallint NOT NULL,
    single_losses smallint NOT NULL,
    double_wins smallint NOT NULL,
    double_draws smallint NOT NULL,
    double_losses smallint NOT NULL,
    partner_wins smallint NOT NULL,
    partner_draws smallint NOT NULL,
    partner_losses smallint NOT NULL,
    combined_delta smallint NOT NULL,
    double_delta smallint NOT NULL,
    single_delta smallint NOT NULL,
    partner_combined_delta smallint NOT NULL,
    partner_double_delta smallint NOT NULL
);
"""

# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def api_get(path, token, params=None):
    r = requests.get(f"{BASE_URL}{path}", headers={"Authorization": token}, params=params)
    r.raise_for_status()
    return r.json()


def fetch_all_matching_tournaments(token, year):
    matching = []
    limit = 5
    offset = 0
    while True:
        data = api_get("/tournaments", token, params={"limit": limit, "offset": offset})
        if not data:
            break
        for t in data:
            if TOURNAMENT_FILTER.search(t.get("name", "")):
                date_str = t.get("date", "")
                if date_str and date_str.startswith(str(year)):
                    matching.append(t)
        if len(data) < limit:
            break
        offset += limit
    return matching


def fetch_discipline_matches(token, tournament_id, discipline_id):
    return api_get(f"/tournaments/{tournament_id}/disciplines/{discipline_id}/matches", token)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def init_db(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def get_or_create_player(cur, first_name, last_name):
    cur.execute("SELECT id FROM players WHERE firstName = ? AND lastName = ?", (first_name, last_name))
    row = cur.fetchone()
    if row:
        return row[0]
    cur.execute("INSERT INTO players (firstName, lastName) VALUES (?, ?)", (first_name, last_name))
    return cur.lastrowid


def competition_already_imported(cur, tio_id):
    cur.execute("SELECT id FROM competitions WHERE tioId = ?", (tio_id,))
    return cur.fetchone() is not None


def insert_competition(cur, tio_id, name, date_str):
    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    unix_ts = int(dt.timestamp())
    cur.execute(
        "INSERT INTO competitions (tfvbId, type, name, year, month, day, unixTimestamp, tioId) VALUES (0, 3, ?, ?, ?, ?, ?, ?)",
        (name, dt.year, dt.month, dt.day, unix_ts, tio_id)
    )
    return cur.lastrowid


# ---------------------------------------------------------------------------
# Match parsing
# ---------------------------------------------------------------------------

def extract_score(match):
    display = match.get("displayScore")
    if display and len(display) == 2:
        return display[0], display[1]
    encounters = match.get("encounters", [])
    if not encounters:
        return None, None
    try:
        sets = encounters[0]
        if isinstance(sets[0], list):
            wins1 = sum(1 for s in sets if s[0] > s[1])
            wins2 = sum(1 for s in sets if s[1] > s[0])
            return wins1, wins2
        else:
            return sets[0], sets[1]
    except Exception:
        return None, None


def extract_teams(match):
    entries = match.get("entries", [])
    if len(entries) < 2:
        return None, None

    def get_players(entry):
        """Gibt die Spieler-Einträge eines Teams zurück."""
        if entry is None:
            return []
        sub = entry.get("entries", [])
        return sub if sub else [entry]

    # Neue Struktur: [[{team1_obj}], [{team2_obj}]]
    # entries[0] ist eine Liste mit einem Team-Objekt
    if isinstance(entries[0], list):
        team1_list = entries[0]
        team2_list = entries[1]
        # Jede Liste enthält ein Team-Objekt mit entries = [player1, player2]
        team1 = get_players(team1_list[0]) if team1_list else []
        team2 = get_players(team2_list[0]) if team2_list else []
        return team1, team2

    # Alte Struktur: [{team1_obj}, {team2_obj}]
    return get_players(entries[0]), get_players(entries[1])


def parse_name(name_str):
    parts = name_str.strip().rsplit(" ", 1)
    return (parts[0], parts[1]) if len(parts) == 2 else (parts[0], "")


# ---------------------------------------------------------------------------
# ELO
# ---------------------------------------------------------------------------

def elo_expected(r1, r2):
    return 1.0 / (1.0 + 10 ** ((r2 - r1) / 400.0))


def elo_adjust_single(rating, k, result, other_rating):
    """Passt Single-ELO an. result = Ergebnis aus Sicht dieses Spielers."""
    pa = elo_expected(rating, other_rating)
    return rating + k * (result - pa)


def elo_adjust_double(rating, k, result, partner_rating, o1_rating, o2_rating):
    """Passt Double-ELO an."""
    r1 = 0.5 * (rating + partner_rating)
    r2 = 0.5 * (o1_rating + o2_rating)
    pa = elo_expected(r1, r2)
    return rating + k * (result - pa)


def recalculate_elo(conn):
    """
    Berechnet played_matches, elo_separate, elo_combined, elo_current
    und player_vs_player_stats komplett neu aus allen matches.
    Entspricht exakt der C++ recompute() Logik.
    """
    cur = conn.cursor()

    # Alles leeren
    cur.execute("DELETE FROM played_matches")
    cur.execute("DELETE FROM elo_separate")
    cur.execute("DELETE FROM elo_combined")
    cur.execute("DELETE FROM elo_current")
    cur.execute("DELETE FROM player_vs_player_stats")

    # Alle Matches chronologisch laden
    cur.execute("""
        SELECT m.id, m.competition_id, m.position, m.type,
               m.score1, m.score2, m.p1, m.p2, m.p11, m.p22,
               c.unixTimestamp, c.name
        FROM matches m
        JOIN competitions c ON c.id = m.competition_id
        ORDER BY c.unixTimestamp, m.competition_id, m.position
    """)
    all_matches = cur.fetchall()

    # Ratings: player_id -> float (start 1000)
    ratings_single   = {}
    ratings_double   = {}
    ratings_combined = {}

    def get_r(d, pid):
        return d.get(pid, START_RATING)

    # ELO Einträge: (pm_id, rating_before, change)
    elo_sep_rows  = []  # elo_separate
    elo_comb_rows = []  # elo_combined

    # played_matches
    pm_rows = []
    pm_counter = [0]

    def add_pm(player_id, match_id):
        pm_counter[0] += 1
        pm_rows.append((pm_counter[0], player_id, match_id))
        return pm_counter[0]

    # pvp stats: (player_id, other_id) -> dict
    pvp = {}

    def get_pvp(a, b):
        key = (a, b)
        if key not in pvp:
            pvp[key] = {
                'single_wins': 0, 'single_draws': 0, 'single_losses': 0,
                'double_wins': 0, 'double_draws': 0, 'double_losses': 0,
                'partner_wins': 0, 'partner_draws': 0, 'partner_losses': 0,
                'combined_delta': 0.0, 'double_delta': 0.0, 'single_delta': 0.0,
                'partner_combined_delta': 0.0, 'partner_double_delta': 0.0,
            }
        return pvp[key]

    def pvp_checkin(d, result):
        if result == 1.0:
            d['wins'] = d.get('wins', 0) + 1
        elif result == 0.5:
            d['draws'] = d.get('draws', 0) + 1
        else:
            d['losses'] = d.get('losses', 0) + 1

    for row in all_matches:
        mid, comp_id, pos, mtype, score1, score2, p1, p2, p11, p22, unix_ts, comp_name = row

        # result aus Sicht Team 2 (wie im C++ Code)
        if score1 > score2:
            result = 0.0
        elif score1 < score2:
            result = 1.0
        else:
            result = 0.5

        k = K

        if mtype == 1:  # Single
            pm1id = add_pm(p1, mid)
            pm2id = add_pm(p2, mid)

            # Separate (Single ELO)
            r1s = get_r(ratings_single, p1)
            r2s = get_r(ratings_single, p2)
            new_r1s = elo_adjust_single(r1s, k, 1.0 - result, r2s)
            new_r2s = elo_adjust_single(r2s, k, result, r1s)
            elo_sep_rows.append((pm1id, round(r1s), round(new_r1s - r1s)))
            elo_sep_rows.append((pm2id, round(r2s), round(new_r2s - r2s)))
            ratings_single[p1] = new_r1s
            ratings_single[p2] = new_r2s

            # Combined
            r1c = get_r(ratings_combined, p1)
            r2c = get_r(ratings_combined, p2)
            new_r1c = elo_adjust_single(r1c, k, 1.0 - result, r2c)
            new_r2c = elo_adjust_single(r2c, k, result, r1c)
            elo_comb_rows.append((pm1id, round(r1c), round(new_r1c - r1c)))
            elo_comb_rows.append((pm2id, round(r2c), round(new_r2c - r2c)))
            ratings_combined[p1] = new_r1c
            ratings_combined[p2] = new_r2c

            # PVP
            d12 = get_pvp(p1, p2)
            d21 = get_pvp(p2, p1)
            if result == 0.0:   # p1 won
                d12['single_wins']   += 1
                d21['single_losses'] += 1
            elif result == 1.0: # p2 won
                d12['single_losses'] += 1
                d21['single_wins']   += 1
            else:
                d12['single_draws'] += 1
                d21['single_draws'] += 1
            d12['single_delta'] += round(new_r1s - r1s)
            d21['single_delta'] += round(new_r2s - r2s)
            d12['combined_delta'] += round(new_r1c - r1c)
            d21['combined_delta'] += round(new_r2c - r2c)

        elif mtype == 2:  # Double
            pm1id  = add_pm(p1,  mid)
            pm11id = add_pm(p11, mid)
            pm2id  = add_pm(p2,  mid)
            pm22id = add_pm(p22, mid)

            # Separate (Double ELO)
            d1  = get_r(ratings_double, p1)
            d11 = get_r(ratings_double, p11)
            d2  = get_r(ratings_double, p2)
            d22 = get_r(ratings_double, p22)

            new_d1  = elo_adjust_double(d1,  k, 1.0-result, d11, d2, d22)
            new_d11 = elo_adjust_double(d11, k, 1.0-result, d1,  d2, d22)
            new_d2  = elo_adjust_double(d2,  k, result,     d22, d1, d11)
            new_d22 = elo_adjust_double(d22, k, result,     d2,  d1, d11)

            elo_sep_rows.append((pm1id,  round(d1),  round(new_d1  - d1)))
            elo_sep_rows.append((pm11id, round(d11), round(new_d11 - d11)))
            elo_sep_rows.append((pm2id,  round(d2),  round(new_d2  - d2)))
            elo_sep_rows.append((pm22id, round(d22), round(new_d22 - d22)))

            ratings_double[p1]  = new_d1
            ratings_double[p11] = new_d11
            ratings_double[p2]  = new_d2
            ratings_double[p22] = new_d22

            # Combined
            c1  = get_r(ratings_combined, p1)
            c11 = get_r(ratings_combined, p11)
            c2  = get_r(ratings_combined, p2)
            c22 = get_r(ratings_combined, p22)

            new_c1  = elo_adjust_double(c1,  k, 1.0-result, c11, c2, c22)
            new_c11 = elo_adjust_double(c11, k, 1.0-result, c1,  c2, c22)
            new_c2  = elo_adjust_double(c2,  k, result,     c22, c1, c11)
            new_c22 = elo_adjust_double(c22, k, result,     c2,  c1, c11)

            elo_comb_rows.append((pm1id,  round(c1),  round(new_c1  - c1)))
            elo_comb_rows.append((pm11id, round(c11), round(new_c11 - c11)))
            elo_comb_rows.append((pm2id,  round(c2),  round(new_c2  - c2)))
            elo_comb_rows.append((pm22id, round(c22), round(new_c22 - c22)))

            ratings_combined[p1]  = new_c1
            ratings_combined[p11] = new_c11
            ratings_combined[p2]  = new_c2
            ratings_combined[p22] = new_c22

            # PVP Double
            res1 = 1.0 - result  # aus Sicht Team 1
            res2 = result        # aus Sicht Team 2
            for attacker, chg_sep, chg_comb in [(p1, new_d1-d1, new_c1-c1), (p11, new_d11-d11, new_c11-c11)]:
                for defender in [p2, p22]:
                    d = get_pvp(attacker, defender)
                    if res1 == 1.0:   d['double_wins']   += 1
                    elif res1 == 0.5: d['double_draws']  += 1
                    else:             d['double_losses']  += 1
                    d['double_delta']   += round(chg_sep)
                    d['combined_delta'] += round(chg_comb)
            for attacker, chg_sep, chg_comb in [(p2, new_d2-d2, new_c2-c2), (p22, new_d22-d22, new_c22-c22)]:
                for defender in [p1, p11]:
                    d = get_pvp(attacker, defender)
                    if res2 == 1.0:   d['double_wins']   += 1
                    elif res2 == 0.5: d['double_draws']  += 1
                    else:             d['double_losses']  += 1
                    d['double_delta']   += round(chg_sep)
                    d['combined_delta'] += round(chg_comb)

            # PVP Partner
            for a, b, chg_sep, chg_comb, res in [
                (p1,  p11, new_d1-d1,   new_c1-c1,   res1),
                (p11, p1,  new_d11-d11, new_c11-c11, res1),
                (p2,  p22, new_d2-d2,   new_c2-c2,   res2),
                (p22, p2,  new_d22-d22, new_c22-c22, res2),
            ]:
                d = get_pvp(a, b)
                if res == 1.0:   d['partner_wins']   += 1
                elif res == 0.5: d['partner_draws']  += 1
                else:            d['partner_losses']  += 1
                d['partner_double_delta']   += round(chg_sep)
                d['partner_combined_delta'] += round(chg_comb)

    # Alle Spieler (auch ohne Matches) für elo_current
    cur.execute("SELECT id FROM players")
    all_player_ids = [r[0] for r in cur.fetchall()]

    # Schreiben
    cur.executemany("INSERT INTO played_matches (id, player_id, match_id) VALUES (?, ?, ?)", pm_rows)

    cur.executemany("INSERT INTO elo_separate (played_match_id, rating, change) VALUES (?, ?, ?)", elo_sep_rows)

    cur.executemany("INSERT INTO elo_combined (played_match_id, rating, change) VALUES (?, ?, ?)", elo_comb_rows)

    for pid in all_player_ids:
        cur.execute(
            "INSERT INTO elo_current (player_id, single, double, combined) VALUES (?, ?, ?, ?)",
            (pid,
             round(get_r(ratings_single, pid)),
             round(get_r(ratings_double, pid)),
             round(get_r(ratings_combined, pid)))
        )

    pvp_rows = []
    for (pid, oid), s in pvp.items():
        pvp_rows.append((
            pid, oid,
            s['single_wins'], s['single_draws'], s['single_losses'],
            s['double_wins'], s['double_draws'], s['double_losses'],
            s['partner_wins'], s['partner_draws'], s['partner_losses'],
            round(s['combined_delta']), round(s['double_delta']), round(s['single_delta']),
            round(s['partner_combined_delta']), round(s['partner_double_delta']),
        ))
    cur.executemany("INSERT INTO player_vs_player_stats VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", pvp_rows)

    conn.commit()
    print(f"  ELO berechnet: {len(pm_rows)} played_matches, {len(elo_sep_rows)} elo_separate, {len(pvp_rows)} pvp-Einträge")


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def import_tournament(conn, token, t, dry_run=False):
    cur = conn.cursor()
    tio_id = t["id"]
    name = t["name"]
    date_str = t.get("date", "")

    if competition_already_imported(cur, tio_id):
        print(f"  Bereits importiert, überspringe.")
        return 0

    tournament_detail = api_get(f"/tournaments/{tio_id}", token)
    all_matches = []
    for disc in tournament_detail.get("disciplines", []):
        # Immer die ID aus dem Detail-Endpunkt verwenden (nicht aus der Liste)
        disc_id = disc.get("id")
        if not disc_id:
            continue
        entry_type = disc.get("entryType", "")
        match_type = 1 if entry_type == "single" else 2  # 1=Einzel, 2=Doppel
        print(f"  Discipline: {disc_id} (entryType={entry_type}, type={match_type})")
        try:
            matches = fetch_discipline_matches(token, tio_id, disc_id)
            print(f"  -> {len(matches)} Matches von API")
            # match_type an jeden Match anhängen
            for m in matches:
                m['_match_type'] = match_type
            all_matches.extend(matches)
        except Exception as e:
            print(f"  Warnung: Discipline {disc_id} nicht ladbar: {e}")

    playable = [m for m in all_matches if m.get("state") == "played" and m.get("entries")]
    print(f"  {len(all_matches)} Matches gesamt, {len(playable)} gespielt")

    if not playable:
        print(f"  Keine gespielten Matches, überspringe.")
        return 0

    if dry_run:
        print(f"  [DRY RUN] Würde {len(playable)} Matches importieren.")
        return len(playable)

    comp_id = insert_competition(cur, tio_id, name, date_str)

    imported = 0
    skipped = 0
    for pos, m in enumerate(playable):
        team1, team2 = extract_teams(m)
        score1, score2 = extract_score(m)

        if not team1 or not team2 or score1 is None:
            skipped += 1
            continue

        def resolve(entry):
            if entry is None:
                return None
            fn, ln = parse_name(entry.get("name", ""))
            return get_or_create_player(cur, fn, ln)

        p1  = resolve(team1[0])
        p2  = resolve(team2[0])
        if match_type == 1:  # Single: p11/p22 = 0
            p11 = 0
            p22 = 0
        else:
            p11 = resolve(team1[1] if len(team1) > 1 else team1[0])
            p22 = resolve(team2[1] if len(team2) > 1 else team2[0])

        if None in (p1, p11, p2, p22):
            skipped += 1
            continue

        if match_type == 2 and (p1 == p11 or p2 == p22):
            skipped += 1
            print(f"  Warnung: Match {m.get('id')} hat doppelten Spieler, überspringe.")
            continue

        match_type = m.get('_match_type', 2)
        cur.execute(
            "INSERT INTO matches (competition_id, position, type, score1, score2, p1, p2, p11, p22) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (comp_id, pos, match_type, score1, score2, p1, p2, p11, p22)
        )
        match_id = cur.lastrowid

        for pid in {p1, p11, p2, p22}:
            if pid == 0:
                continue
            cur.execute(
                "INSERT INTO played_matches (player_id, match_id) VALUES (?, ?)",
                (pid, match_id)
            )

        imported += 1

    conn.commit()
    print(f"  ✓ {imported} Matches importiert, {skipped} übersprungen")
    return imported


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Tournament.app -> SQLite Importer + ELO")
    parser.add_argument("--db", required=True, help="Pfad zur SQLite-Datenbank")
    parser.add_argument("--token", help="API-Token direkt")
    parser.add_argument("--token-file", help="Datei mit API-Token")
    parser.add_argument("--year", type=int, default=2026, help="Turnierjahr (default: 2026)")
    parser.add_argument("--dry-run", action="store_true", help="Nichts schreiben, nur anzeigen")
    parser.add_argument("--skip-elo", action="store_true", help="ELO-Berechnung überspringen")
    args = parser.parse_args()

    if args.token:
        token = args.token.strip()
    elif args.token_file:
        with open(args.token_file) as f:
            token = f.read().strip()
    else:
        print("Fehler: --token oder --token-file angeben")
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    init_db(conn)

    print(f"Suche Turniere für {args.year}...")
    tournaments = fetch_all_matching_tournaments(token, year=args.year)
    # Chronologisch sortieren
    tournaments.sort(key=lambda t: t.get("date", ""))
    print(f"{len(tournaments)} passende Turniere gefunden:\n")
    for t in tournaments:
        print(f"  {t['date'][:10]}  {t['name']}  [{t['state']}]")
    print()

    total = 0
    for t in tournaments:
        if t.get("state") not in ("finished", "running"):
            print(f"Überspringe '{t['name']}' (state={t['state']})")
            continue
        print(f"Importiere: {t['name']} ({t['date'][:10]}) [{t['id']}]")
        total += import_tournament(conn, token, t, dry_run=args.dry_run)

    print(f"\nMatches importiert: {total}")

    if not args.dry_run and not args.skip_elo and total > 0:
        print("\nBerechne ELO...")
        recalculate_elo(conn)

    conn.close()
    print("Fertig.")


if __name__ == "__main__":
    main()

