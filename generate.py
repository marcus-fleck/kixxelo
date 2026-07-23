#!/usr/bin/env python3
"""
Generiert statische HTML-Seiten für die KIXX ELO-Rangliste.
Erzeugt: index.html und players/{id}.html für jeden Spieler mit ELO-Historie.
"""

import sqlite3
import json
import os
import sys
from datetime import datetime

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else "test.db"
OUT_DIR = sys.argv[2] if len(sys.argv) > 2 else "."

PLAYER_DIR = os.path.join(OUT_DIR, "players")
os.makedirs(PLAYER_DIR, exist_ok=True)

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

generated_at = datetime.now().strftime("%d.%m.%Y %H:%M")

# ── Gemeinsames CSS ─────────────────────────────────────────────────────────

SHARED_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  /* ── Helles Theme zum Einbetten in den Kixx-Contentbereich ──
     Passt nur diese Werte an, wenn ein Ton nicht sitzt.
     --bg / --text am besten aus den DevTools von #content_area übernehmen. */
  --bg:      #ededed;   /* Seitenhintergrund = grauer Kixx-Contentbereich */
  --surface: #ffffff;   /* Karten & Tabellen (heben sich vom Grau ab) */
  --thead:   #f0f0ee;   /* Tabellenkopf */
  --border:  #dcdcda;
  --accent:  #e8460a;   /* Kixx-Orange */
  --accent2: #b84a00;   /* dunkleres Orange, kontrastsicher auf Hell */
  --text:    #1c1c1c;
  --muted:   #5f5f5f;
  --up:      #2e7d46;
  --down:    #b0341f;
  --font-display: 'Bebas Neue', sans-serif;
  --font-body:    'DM Sans', sans-serif;
}

html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 15px;
  line-height: 1.6;
}

/* Wrap: passt in den ~870px breiten Kixx-Contentbereich -> kein Scrollen am PC */
.wrap { max-width: 860px; margin: 0 auto; padding: 0 16px; }

/* Header */
header { border-bottom: 1px solid var(--border); padding: 22px 0 16px; margin-bottom: 28px; }
header .inner { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
header h1 { font-family: var(--font-display); font-size: 2.4rem; letter-spacing: 2px; color: var(--accent); line-height: 1; }
header .sub { color: var(--muted); font-size: 0.85rem; }
.timestamp { margin-left: auto; font-size: 0.78rem; color: var(--muted); }

/* Tabs */
.tabs { display: flex; gap: 4px; margin-bottom: 22px; }
.tab {
  padding: 8px 20px; border-radius: 6px 6px 0 0;
  border: 1px solid var(--border); border-bottom: none;
  background: transparent; color: var(--muted); cursor: pointer;
  font-family: var(--font-body); font-size: 0.88rem; font-weight: 500;
  letter-spacing: 0.5px; transition: all .18s;
}
.tab:hover { color: var(--text); background: var(--surface); }
.tab.active { background: var(--surface); color: var(--accent); border-color: var(--border); }
.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* Ranglisten-Tabelle (index): passt immer -> kein Scrollen, Namen kürzen notfalls */
.panel-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0 8px 8px 8px;
  overflow: hidden;
}
.panel-wrap table { width: 100%; }

/* Detailtabelle (Spielerseite): breite Spalten dürfen umbrechen,
   damit alles ohne horizontales Scrollen in ~830px passt. */
.table-responsive { width: 100%; max-width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
.table-responsive table { width: 100%; }
.table-responsive th, .table-responsive td { padding: 8px 8px; font-size: 0.8rem; vertical-align: top; }
.m-date  { color: var(--muted); white-space: nowrap; }
.m-comp  { color: var(--muted); font-size: 0.74rem; }   /* darf umbrechen */
.m-type  { color: var(--muted); white-space: nowrap; }
.m-partner {}                                            /* darf umbrechen */
.m-opp   { line-height: 1.35; }                          /* nutzt <br> */
.m-res   { text-align: right; font-weight: 700; white-space: nowrap; }
.table-responsive .change { white-space: nowrap; }
.table-responsive td.elo { font-size: 1rem; letter-spacing: 0; }

table { border-collapse: collapse; }
thead th {
  padding: 12px 14px; text-align: left; font-size: 0.72rem;
  letter-spacing: 1.2px; text-transform: uppercase; color: var(--muted);
  background: var(--thead); border-bottom: 1px solid var(--border); white-space: nowrap;
}
thead th.num { text-align: right; }
tbody tr { border-bottom: 1px solid var(--border); transition: background .12s; cursor: pointer; }
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: rgba(232,70,10,0.06); }
td { padding: 11px 14px; }
td.num { text-align: right; }
td.rank { font-family: var(--font-display); font-size: 1.15rem; color: var(--muted); width: 48px; }
td.rank.gold   { color: #c9950c; }
td.rank.silver { color: #7f8a99; }
td.rank.bronze { color: #b06a35; }
td.name { font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
td.name a { color: var(--text); text-decoration: none; }
td.name a:hover { color: var(--accent); }
td.elo { text-align: right; font-family: var(--font-display); font-size: 1.25rem; letter-spacing: 1px; color: var(--accent); }
td.change { text-align: right; font-size: 0.82rem; font-weight: 600; width: 56px; }
td.change.pos { color: var(--up); }
td.change.neg { color: var(--down); }
td.change.neu { color: var(--muted); }
td.matches { text-align: right; color: var(--muted); font-size: 0.85rem; }

/* Search */
.search-wrap { margin-bottom: 16px; }
.search-wrap input {
  width: 100%; max-width: 340px; padding: 9px 14px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text); font-family: var(--font-body); font-size: 0.9rem;
  outline: none; transition: border-color .18s;
}
.search-wrap input:focus { border-color: var(--accent); }

/* Back link */
.back { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); text-decoration: none; font-size: 0.85rem; margin-bottom: 22px; transition: color .15s; }
.back:hover { color: var(--accent); }

/* Player page */
.player-header { margin-bottom: 28px; }
.player-header h2 { font-family: var(--font-display); font-size: 2.6rem; letter-spacing: 2px; color: var(--text); line-height: 1; }
.player-header .badges { display: flex; gap: 12px; margin-top: 12px; flex-wrap: wrap; }
.badge { padding: 5px 14px; border-radius: 20px; font-size: 0.82rem; font-weight: 600; letter-spacing: 0.5px; }
.badge-combined { background: rgba(232,70,10,0.10); color: var(--accent);  border: 1px solid rgba(232,70,10,0.35); }
.badge-single   { background: rgba(184,74,0,0.09);  color: var(--accent2); border: 1px solid rgba(184,74,0,0.30); }
.badge-double   { background: rgba(46,125,70,0.09); color: var(--up);      border: 1px solid rgba(46,125,70,0.30); }

.chart-card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 22px; margin-bottom: 20px; }
.chart-card h3 { font-family: var(--font-display); letter-spacing: 1.5px; font-size: 1.1rem; color: var(--muted); margin-bottom: 16px; }
.chart-wrap { position: relative; height: 220px; }
canvas { width: 100% !important; height: 100% !important; }

.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 12px; margin-bottom: 26px; }
.stat-card { background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.stat-card .label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; color: var(--muted); margin-bottom: 4px; }
.stat-card .value { font-family: var(--font-display); font-size: 1.8rem; letter-spacing: 1px; }

footer { margin-top: 50px; padding: 22px 0; border-top: 1px solid var(--border); text-align: center; font-size: 0.78rem; color: var(--muted); }

/* ── Mobile (Hochformat) ─────────────────────────────────────────────── */
@media (max-width: 640px) {
  .wrap { padding: 0 10px; }
  header { padding: 16px 0 12px; margin-bottom: 18px; }
  header .inner { flex-direction: column; align-items: flex-start; gap: 4px; }
  header h1 { font-size: 1.8rem; letter-spacing: 1px; }
  .timestamp { margin-left: 0; }
  .tabs { gap: 2px; }
  .tab { padding: 7px 12px; font-size: 0.8rem; }
  .search-wrap input { max-width: none; }

  /* Index: 4 Spalten passen ohne horizontales Scrollen, Name kürzt mit … */
  thead th { padding: 8px 5px; font-size: 0.62rem; letter-spacing: 0.6px; }
  td { padding: 8px 5px; }
  td.rank { font-size: 0.95rem; width: 26px; padding-left: 8px; }
  td.name { max-width: 0; width: 100%; }
  td.elo { font-size: 1rem; letter-spacing: 0; }
  td.matches { font-size: 0.72rem; padding-right: 8px; }

  /* Detailtabelle: 8 Spalten -> auf dem Handy horizontal scrollen */
  .table-responsive table { min-width: 560px; }
  .table-responsive th, .table-responsive td { padding: 7px 6px; font-size: 0.72rem; }

  .player-header h2 { font-size: 2rem; }
  .stats-grid { grid-template-columns: repeat(2, 1fr); gap: 8px; }
  .stat-card { padding: 12px; }
  .stat-card .value { font-size: 1.4rem; }
  .chart-card { padding: 14px; }
  .chart-wrap { height: 180px; }
}
@media (max-width: 380px) {
  header h1 { font-size: 1.55rem; }
  thead th { font-size: 0.58rem; }
}
"""

# ── Daten laden ─────────────────────────────────────────────────────────────

def get_rankings():
    cats = {}
    for col in ('combined', 'single', 'double'):
        cur.execute(f"""
            SELECT p.id, p.firstName, p.lastName,
                   e.{col} AS elo
            FROM elo_current e
            JOIN players p ON p.id = e.player_id
            WHERE e.{col} != 1000
            ORDER BY e.{col} DESC
        """)
        cats[col] = [dict(r) for r in cur.fetchall()]
    return cats

def get_match_counts():
    """Gesamtzahl der Spiele je Spieler."""
    cur.execute("""
        SELECT player_id, COUNT(*) as cnt
        FROM played_matches GROUP BY player_id
    """)
    return {r[0]: r[1] for r in cur.fetchall()}

def get_match_counts_by_type():
    """Spiele je Spieler, getrennt nach Einzel (type=1) und Doppel (type=2)."""
    cur.execute("""
        SELECT pm.player_id, m.type, COUNT(*) AS cnt
        FROM played_matches pm
        JOIN matches m ON m.id = pm.match_id
        GROUP BY pm.player_id, m.type
    """)
    single, double = {}, {}
    for r in cur.fetchall():
        pid, mtype, cnt = r[0], r[1], r[2]
        if mtype == 1:
            single[pid] = single.get(pid, 0) + cnt
        elif mtype == 2:
            double[pid] = double.get(pid, 0) + cnt
    return single, double

def get_recent_matches(player_id, limit=30, match_type=None):
    type_filter = "AND m.type = ?" if match_type else ""
    params = [player_id]
    if match_type:
        params.append(match_type)
    params.append(limit)
    cur.execute(f"""
        SELECT
            m.id, m.type, m.score1, m.score2,
            m.p1, m.p2, m.p11, m.p22,
            c.name as comp_name, c.year, c.month, c.day,
            es.change as elo_change,
            es.rating as elo_after
        FROM played_matches pm
        JOIN matches m ON m.id = pm.match_id
        JOIN competitions c ON c.id = m.competition_id
        JOIN elo_separate es ON es.played_match_id = pm.id
        WHERE pm.player_id = ? {type_filter}
        ORDER BY c.unixTimestamp DESC, m.position DESC
        LIMIT ?
    """, params)
    rows = [dict(r) for r in cur.fetchall()]

    ids_needed = set()
    for r in rows:
        for col in ('p1', 'p2', 'p11', 'p22'):
            if r[col]:
                ids_needed.add(r[col])
    if ids_needed:
        placeholders = ','.join('?' * len(ids_needed))
        cur.execute(f"SELECT id, firstName, lastName FROM players WHERE id IN ({placeholders})",
                    list(ids_needed))
        pmap = {r['id']: f"{r['firstName']} {r['lastName']}" for r in cur.fetchall()}
    else:
        pmap = {}

    result = []
    for r in rows:
        pid = player_id
        on_side1 = (r['p1'] == pid or r['p11'] == pid)
        if r['score1'] == r['score2']:
            match_result = 'draw'
        elif on_side1:
            match_result = 'won' if r['score1'] > r['score2'] else 'lost'
        else:
            match_result = 'won' if r['score2'] > r['score1'] else 'lost'

        if r['type'] == 1:
            if on_side1:
                partners, opponents = [], [pmap.get(r['p2'], '?')]
            else:
                partners, opponents = [], [pmap.get(r['p1'], '?')]
        else:
            if on_side1:
                partner_id = r['p11'] if r['p1'] == pid else r['p1']
                partners = [pmap.get(partner_id, '?')]
                opponents = [pmap.get(r['p2'], '?'), pmap.get(r['p22'], '?')]
            else:
                partner_id = r['p22'] if r['p2'] == pid else r['p2']
                partners = [pmap.get(partner_id, '?')]
                opponents = [pmap.get(r['p1'], '?'), pmap.get(r['p11'], '?')]

        result.append({
            'date': f"{r['day']:02d}.{r['month']:02d}.{r['year']}",
            'comp': r['comp_name'],
            'type': 'Einzel' if r['type'] == 1 else 'Doppel',
            'partners': partners,
            'opponents': opponents,
            'result': match_result,
            'elo_change': r['elo_change'],
            'elo_after': r['elo_after'],
        })
    return result


def get_elo_history(player_id, match_type=None):
    type_filter = "AND m.type = ?" if match_type else ""
    params = [player_id]
    if match_type:
        params.append(match_type)
    cur.execute(f"""
        SELECT
            es.rating AS separate_rating,
            ec.rating AS combined_rating,
            c.year, c.month, c.day,
            c.name AS comp_name,
            m.type AS match_type
        FROM played_matches pm
        JOIN elo_separate es ON es.played_match_id = pm.id
        JOIN elo_combined ec ON ec.played_match_id = pm.id
        JOIN matches m ON m.id = pm.match_id
        JOIN competitions c ON c.id = m.competition_id
        WHERE pm.player_id = ? {type_filter}
        ORDER BY c.unixTimestamp, m.position
    """, params)
    return [dict(r) for r in cur.fetchall()]

rankings = get_rankings()
match_counts = get_match_counts()
single_counts, double_counts = get_match_counts_by_type()

# Pro Tab die passende Zählung: Gesamt / nur Einzel / nur Doppel
COUNTS_BY_COL = {
    'combined': match_counts,
    'single':   single_counts,
    'double':   double_counts,
}

# ── Index-Seite ──────────────────────────────────────────────────────────────

def render_table(rows, col):
    counts = COUNTS_BY_COL[col]
    html = []
    html.append('<table>')
    html.append('<thead><tr>'
                '<th>Platz</th>'
                '<th>Spieler</th>'
                '<th class="num">ELO</th>'
                '<th class="num">Spiele</th>'
                '</tr></thead><tbody>')
    for i, r in enumerate(rows, 1):
        rank_cls = {1: 'gold', 2: 'silver', 3: 'bronze'}.get(i, '')
        mc = counts.get(r['id'], 0)
        html.append(
            f'<tr onclick="location.href=\'players/{r["id"]}.html\'">'
            f'<td class="rank {rank_cls}">{i}</td>'
            f'<td class="name"><a href="players/{r["id"]}.html">{r["firstName"]} {r["lastName"]}</a></td>'
            f'<td class="elo">{r["elo"]}</td>'
            f'<td class="matches">{mc}</td>'
            f'</tr>'
        )
    html.append('</tbody></table>')
    return '\n'.join(html)

index_html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>KIXX ELO Rangliste</title>
<style>{SHARED_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="inner">
      <h1>ELO RANGLISTE</h1>
      <span class="sub">KIXX Hamburg</span>
      <span class="timestamp">Stand: {generated_at}</span>
    </div>
  </header>

  <div class="search-wrap">
    <input type="text" id="search" placeholder="Spieler suchen…" oninput="filterRows(this.value)">
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('combined',this)">Gesamt</button>
    <button class="tab" onclick="switchTab('single',this)">Einzel</button>
    <button class="tab" onclick="switchTab('double',this)">Doppel</button>
  </div>

  <div id="panel-combined" class="tab-panel active">
    <div class="panel-wrap">
      {render_table(rankings['combined'], 'combined')}
    </div>
  </div>
  <div id="panel-single" class="tab-panel">
    <div class="panel-wrap">
      {render_table(rankings['single'], 'single')}
    </div>
  </div>
  <div id="panel-double" class="tab-panel">
    <div class="panel-wrap">
      {render_table(rankings['double'], 'double')}
    </div>
  </div>

  <footer>KIXX ELO Rangliste · generiert {generated_at}</footer>
</div>

<script>
function switchTab(id, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.getElementById('panel-' + id).classList.add('active');
  btn.classList.add('active');
  filterRows(document.getElementById('search').value);
}}
function filterRows(q) {{
  q = q.toLowerCase();
  const active = document.querySelector('.tab-panel.active');
  active.querySelectorAll('tbody tr').forEach(tr => {{
    const name = tr.querySelector('.name').textContent.toLowerCase();
    tr.style.display = name.includes(q) ? '' : 'none';
  }});
}}
</script>
</body>
</html>
"""

with open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8") as f:
    f.write(index_html)
print("✓ index.html")

# ── Spieler-Seiten ───────────────────────────────────────────────────────────

cur.execute("SELECT * FROM elo_current")
elo_all = {r['player_id']: dict(r) for r in cur.fetchall()}

cur.execute("SELECT * FROM players")
all_players = {r['id']: dict(r) for r in cur.fetchall()}

generated_count = 0
for pid, elo_row in elo_all.items():
    if match_counts.get(pid, 0) == 0:
        continue

    player = all_players.get(pid)
    if not player:
        continue

    history = get_elo_history(pid)
    if not history:
        continue

    name = f"{player['firstName']} {player['lastName']}"
    mc = match_counts.get(pid, 0)
    mc_s = single_counts.get(pid, 0)
    mc_d = double_counts.get(pid, 0)

    combined_labels = []
    combined_data = []
    for h in history:
        combined_labels.append(f"{h['day']:02d}.{h['month']:02d}.{h['year']}")
        combined_data.append(h['combined_rating'])

    history_single = get_elo_history(pid, match_type=1)
    single_labels = []
    single_data = []
    for h in history_single:
        single_labels.append(f"{h['day']:02d}.{h['month']:02d}.{h['year']}")
        single_data.append(h['separate_rating'])

    history_double = get_elo_history(pid, match_type=2)
    double_labels = []
    double_data = []
    for h in history_double:
        double_labels.append(f"{h['day']:02d}.{h['month']:02d}.{h['year']}")
        double_data.append(h['separate_rating'])

    chart_combined_labels = json.dumps(combined_labels)
    chart_combined = json.dumps(combined_data)
    chart_single_labels = json.dumps(single_labels)
    chart_single = json.dumps(single_data)
    chart_double_labels = json.dumps(double_labels)
    chart_double = json.dumps(double_data)

    elo_c = elo_row.get('combined', 1000)
    elo_s = elo_row.get('single', 1000)
    elo_d = elo_row.get('double', 1000)

    def get_rank(col, val):
        return next((i+1 for i, r in enumerate(rankings[col]) if r['id'] == pid), '-')

    rank_c = get_rank('combined', elo_c)
    rank_s = get_rank('single', elo_s)
    rank_d = get_rank('double', elo_d)

    recent_all    = get_recent_matches(pid, limit=30)
    recent_single = get_recent_matches(pid, limit=30, match_type=1)
    recent_double = get_recent_matches(pid, limit=30, match_type=2)

    def build_match_rows(matches):
        parts = []
        for m in matches:
            change = m['elo_change']
            change_cls = 'pos' if change > 0 else ('neg' if change < 0 else 'neu')
            change_str = f"+{change}" if change > 0 else str(change)
            if m['result'] == 'won':
                result_str, result_color = '✓', 'var(--up)'
            elif m['result'] == 'draw':
                result_str, result_color = '=', 'var(--muted)'
            else:
                result_str, result_color = '✗', 'var(--down)'
            partner_str = ', '.join(m['partners']) if m['partners'] else '–'
            opponent_str = '<br>'.join(m['opponents'])
            comp_short = m['comp'].replace('Offenes Doppel', 'OD').replace('Offenes Einzel', 'OE')
            parts.append(
                f'<tr>'
                f'<td class="m-date">{m["date"]}</td>'
                f'<td class="m-comp">{comp_short}</td>'
                f'<td class="m-type">{m["type"]}</td>'
                f'<td class="m-partner">{partner_str}</td>'
                f'<td class="m-opp">{opponent_str}</td>'
                f'<td class="m-res num" style="color:{result_color}">{result_str}</td>'
                f'<td class="change {change_cls}">{change_str}</td>'
                f'<td class="elo">{m["elo_after"]}</td>'
                f'</tr>'
            )
        return '\n'.join(parts) if parts else '<tr><td colspan="8" style="color:var(--muted);text-align:center;padding:20px">Keine Spiele gefunden</td></tr>'

    matches_rows_all    = build_match_rows(recent_all)
    matches_rows_single = build_match_rows(recent_single)
    matches_rows_double = build_match_rows(recent_double)

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} – KIXX ELO</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
{SHARED_CSS}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="inner">
      <h1>ELO RANGLISTE</h1>
      <span class="sub">KIXX Hamburg</span>
      <span class="timestamp">Stand: {generated_at}</span>
    </div>
  </header>

  <a href="../index.html" class="back">← Zurück zur Rangliste</a>

  <div class="player-header">
    <h2>{name.upper()}</h2>
    <div class="badges">
      <span class="badge badge-combined">Gesamt #{rank_c}</span>
      <span class="badge badge-single">Einzel #{rank_s}</span>
      <span class="badge badge-double">Doppel #{rank_d}</span>
    </div>
  </div>

  <div class="stats-grid">
    <div class="stat-card">
      <div class="label">ELO Gesamt</div>
      <div class="value" style="color:var(--accent)">{elo_c}</div>
    </div>
    <div class="stat-card">
      <div class="label">ELO Einzel</div>
      <div class="value" style="color:var(--accent2)">{elo_s}</div>
    </div>
    <div class="stat-card">
      <div class="label">ELO Doppel</div>
      <div class="value" style="color:var(--up)">{elo_d}</div>
    </div>
    <div class="stat-card">
      <div class="label" id="statMatchesLabel">Spiele</div>
      <div class="value" id="statMatches" style="color:var(--text)">{mc}</div>
    </div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchPlayerTab('all',this)">Alle</button>
    <button class="tab" onclick="switchPlayerTab('single',this)">Einzel</button>
    <button class="tab" onclick="switchPlayerTab('double',this)">Doppel</button>
  </div>

  <div id="ptab-all" class="tab-panel active">
    <div class="chart-card">
      <h3>ELO ENTWICKLUNG – GESAMT (COMBINED)</h3>
      <div class="chart-wrap"><canvas id="chartCombined"></canvas></div>
    </div>
    <div class="chart-card" style="margin-top:8px">
      <h3>LETZTE SPIELE</h3>
      <div class="table-responsive">
      <table>
        <thead><tr><th>Datum</th><th>Turnier</th><th>Art</th><th>Partner</th><th>Gegner</th><th class="num">Erg.</th><th class="num">ELO Δ</th><th class="num">ELO</th></tr></thead>
        <tbody>{matches_rows_all}</tbody>
      </table></div>
    </div>
  </div>

  <div id="ptab-single" class="tab-panel">
    <div class="chart-card">
      <h3>ELO ENTWICKLUNG – EINZEL</h3>
      <div class="chart-wrap"><canvas id="chartSingle"></canvas></div>
    </div>
    <div class="chart-card" style="margin-top:8px">
      <h3>LETZTE EINZELSPIELE</h3>
      <div class="table-responsive">
      <table>
        <thead><tr><th>Datum</th><th>Turnier</th><th>Art</th><th>Partner</th><th>Gegner</th><th class="num">Erg.</th><th class="num">ELO Δ</th><th class="num">ELO</th></tr></thead>
        <tbody>{matches_rows_single}</tbody>
      </table></div>
    </div>
  </div>

  <div id="ptab-double" class="tab-panel">
    <div class="chart-card">
      <h3>ELO ENTWICKLUNG – DOPPEL</h3>
      <div class="chart-wrap"><canvas id="chartDouble"></canvas></div>
    </div>
    <div class="chart-card" style="margin-top:8px">
      <h3>LETZTE DOPPELSPIELE</h3>
      <div class="table-responsive">
      <table>
        <thead><tr><th>Datum</th><th>Turnier</th><th>Art</th><th>Partner</th><th>Gegner</th><th class="num">Erg.</th><th class="num">ELO Δ</th><th class="num">ELO</th></tr></thead>
        <tbody>{matches_rows_double}</tbody>
      </table></div>
    </div>
  </div>

  <footer>KIXX ELO Rangliste · generiert {generated_at}</footer>
</div>

<script>
const chartDefaults = {{
  responsive: true,
  maintainAspectRatio: false,
  interaction: {{ intersect: false, mode: 'index' }},
  plugins: {{
    legend: {{ labels: {{ color: '#555555', font: {{ family: 'DM Sans', size: 12 }} }} }},
    tooltip: {{
      backgroundColor: '#ffffff',
      borderColor: '#dddddd',
      borderWidth: 1,
      titleColor: '#1c1c1c',
      bodyColor: '#555555',
    }}
  }},
  scales: {{
    x: {{
      ticks: {{ color: '#8a8a8a', maxTicksLimit: 10, font: {{ size: 11 }} }},
      grid: {{ color: '#ececea' }},
    }},
    y: {{
      ticks: {{ color: '#8a8a8a', font: {{ size: 11 }} }},
      grid: {{ color: '#ececea' }},
    }}
  }}
}};

new Chart(document.getElementById('chartCombined'), {{
  type: 'line', data: {{ labels: {chart_combined_labels}, datasets: [{{
    label: 'Combined ELO', data: {chart_combined},
    borderColor: '#e8460a', backgroundColor: 'rgba(232,70,10,0.12)',
    borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, fill: true, tension: 0.3
  }}] }}, options: chartDefaults
}});

new Chart(document.getElementById('chartSingle'), {{
  type: 'line', data: {{ labels: {chart_single_labels}, datasets: [{{
    label: 'Einzel ELO', data: {chart_single},
    borderColor: '#e8460a', backgroundColor: 'rgba(232,70,10,0.12)',
    borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, fill: true, tension: 0.3
  }}] }}, options: chartDefaults
}});

new Chart(document.getElementById('chartDouble'), {{
  type: 'line', data: {{ labels: {chart_double_labels}, datasets: [{{
    label: 'Doppel ELO', data: {chart_double},
    borderColor: '#2e7d46', backgroundColor: 'rgba(46,125,70,0.12)',
    borderWidth: 2, pointRadius: 2, pointHoverRadius: 5, fill: true, tension: 0.3
  }}] }}, options: chartDefaults
}});

// Spiele-Zähler passend zum aktiven Tab
const matchCountsByTab = {{
  all:    {{ count: {mc},   label: 'Spiele' }},
  single: {{ count: {mc_s}, label: 'Spiele Einzel' }},
  double: {{ count: {mc_d}, label: 'Spiele Doppel' }}
}};

function switchPlayerTab(id, btn) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(b => b.classList.remove('active'));
  document.getElementById('ptab-' + id).classList.add('active');
  btn.classList.add('active');
  const c = matchCountsByTab[id];
  if (c) {{
    document.getElementById('statMatches').textContent = c.count;
    document.getElementById('statMatchesLabel').textContent = c.label;
  }}
}}
</script>
</body>
</html>
"""

    with open(os.path.join(PLAYER_DIR, f"{pid}.html"), "w", encoding="utf-8") as f:
        f.write(page)
    generated_count += 1

print(f"✓ {generated_count} Spielerseiten in players/")
print("Fertig!")
