#!/usr/bin/env python3
"""
Generiert statische HTML-Seiten für die TFVHH ELO-Rangliste.
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

# ── Gemeinsames CSS & JS ────────────────────────────────────────────────────

SHARED_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:       #0d0f14;
  --surface:  #161a23;
  --border:   #252a38;
  --accent:   #e8c847;
  --accent2:  #4a9eff;
  --text:     #e2e8f0;
  --muted:    #64748b;
  --up:       #34d399;
  --down:     #f87171;
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
  min-height: 100vh;
}

/* Grain overlay */
body::before {
  content: '';
  position: fixed; inset: 0;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)' opacity='0.04'/%3E%3C/svg%3E");
  pointer-events: none;
  z-index: 0;
  opacity: 0.6;
}

.wrap { position: relative; z-index: 1; max-width: 1000px; margin: 0 auto; padding: 0 20px; }

/* Header */
header {
  border-bottom: 1px solid var(--border);
  padding: 28px 0 20px;
  margin-bottom: 36px;
}
header .inner { display: flex; align-items: baseline; gap: 16px; flex-wrap: wrap; }
header h1 { font-family: var(--font-display); font-size: 2.8rem; letter-spacing: 2px; color: var(--accent); line-height: 1; }
header .sub { color: var(--muted); font-size: 0.85rem; }
.timestamp { margin-left: auto; font-size: 0.78rem; color: var(--muted); }

/* Tabs */
.tabs { display: flex; gap: 4px; margin-bottom: 28px; }
.tab {
  padding: 8px 20px;
  border-radius: 6px 6px 0 0;
  border: 1px solid var(--border);
  border-bottom: none;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-family: var(--font-body);
  font-size: 0.88rem;
  font-weight: 500;
  letter-spacing: 0.5px;
  transition: all .18s;
}
.tab:hover { color: var(--text); background: var(--surface); }
.tab.active { background: var(--surface); color: var(--accent); border-color: var(--border); }

.tab-panel { display: none; }
.tab-panel.active { display: block; }

/* Table */
.panel-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 0 8px 8px 8px;
  overflow: hidden;
}
table { width: 100%; border-collapse: collapse; }
thead th {
  padding: 12px 16px;
  text-align: left;
  font-size: 0.72rem;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  color: var(--muted);
  background: var(--bg);
  border-bottom: 1px solid var(--border);
}
thead th.num { text-align: right; }
tbody tr {
  border-bottom: 1px solid var(--border);
  transition: background .12s;
  cursor: pointer;
}
tbody tr:last-child { border-bottom: none; }
tbody tr:hover { background: rgba(232,200,71,0.04); }
td { padding: 11px 16px; }
td.rank {
  font-family: var(--font-display);
  font-size: 1.15rem;
  color: var(--muted);
  width: 52px;
}
td.rank.gold   { color: #f5c842; }
td.rank.silver { color: #adb5c7; }
td.rank.bronze { color: #cd7f45; }
td.name { font-weight: 500; }
td.name a { color: var(--text); text-decoration: none; }
td.name a:hover { color: var(--accent); }
td.elo {
  text-align: right;
  font-family: var(--font-display);
  font-size: 1.25rem;
  letter-spacing: 1px;
  color: var(--accent);
}
td.change { text-align: right; font-size: 0.82rem; font-weight: 600; width: 60px; }
td.change.pos { color: var(--up); }
td.change.neg { color: var(--down); }
td.change.neu { color: var(--muted); }
td.matches { text-align: right; color: var(--muted); font-size: 0.85rem; }

/* Search */
.search-wrap { margin-bottom: 16px; }
.search-wrap input {
  width: 100%;
  max-width: 340px;
  padding: 9px 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: var(--font-body);
  font-size: 0.9rem;
  outline: none;
  transition: border-color .18s;
}
.search-wrap input:focus { border-color: var(--accent); }

/* Back link */
.back { display: inline-flex; align-items: center; gap: 6px; color: var(--muted); text-decoration: none; font-size: 0.85rem; margin-bottom: 24px; transition: color .15s; }
.back:hover { color: var(--accent); }

/* Player page */
.player-header { margin-bottom: 32px; }
.player-header h2 { font-family: var(--font-display); font-size: 3rem; letter-spacing: 2px; color: var(--text); line-height: 1; }
.player-header .badges { display: flex; gap: 12px; margin-top: 14px; flex-wrap: wrap; }
.badge {
  padding: 5px 14px;
  border-radius: 20px;
  font-size: 0.82rem;
  font-weight: 600;
  letter-spacing: 0.5px;
}
.badge-combined { background: rgba(232,200,71,0.15); color: var(--accent); border: 1px solid rgba(232,200,71,0.3); }
.badge-single   { background: rgba(74,158,255,0.12); color: var(--accent2); border: 1px solid rgba(74,158,255,0.3); }
.badge-double   { background: rgba(52,211,153,0.12); color: var(--up); border: 1px solid rgba(52,211,153,0.3); }

.chart-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 24px;
  margin-bottom: 20px;
}
.chart-card h3 { font-family: var(--font-display); letter-spacing: 1.5px; font-size: 1.1rem; color: var(--muted); margin-bottom: 18px; }
.chart-wrap { position: relative; height: 220px; }
canvas { width: 100% !important; height: 100% !important; }

.stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; margin-bottom: 28px; }
.stat-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 16px;
}
.stat-card .label { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 1.2px; color: var(--muted); margin-bottom: 4px; }
.stat-card .value { font-family: var(--font-display); font-size: 1.8rem; letter-spacing: 1px; }

footer { margin-top: 60px; padding: 24px 0; border-top: 1px solid var(--border); text-align: center; font-size: 0.78rem; color: var(--muted); }
"""

# ── Daten laden ─────────────────────────────────────────────────────────────

def get_rankings():
    cats = {}
    for col in ('combined', 'single', 'double'):
        cur.execute(f"""
            SELECT p.id, p.firstName, p.lastName,
                   e.{col} AS elo,
                   e.combined, e.single, e.double
            FROM elo_current e
            JOIN players p ON p.id = e.player_id
            WHERE e.{col} != 1000
            ORDER BY e.{col} DESC
        """)
        cats[col] = [dict(r) for r in cur.fetchall()]
    return cats

def get_match_counts():
    cur.execute("""
        SELECT player_id, COUNT(*) as cnt
        FROM played_matches GROUP BY player_id
    """)
    return {r[0]: r[1] for r in cur.fetchall()}

def get_elo_history(player_id):
    """Gibt (separate, combined) ELO-Verläufe zurück."""
    cur.execute("""
        SELECT
            ec.rating AS combined_rating,
            es.rating AS separate_rating,
            c.year, c.month, c.day,
            c.name AS comp_name,
            m.type AS match_type
        FROM played_matches pm
        JOIN elo_combined ec ON ec.played_match_id = pm.id
        JOIN elo_separate es ON es.played_match_id = pm.id
        JOIN matches m ON m.id = pm.match_id
        JOIN competitions c ON c.id = m.competition_id
        WHERE pm.player_id = ?
        ORDER BY c.unixTimestamp, m.position
    """, (player_id,))
    return [dict(r) for r in cur.fetchall()]

rankings = get_rankings()
match_counts = get_match_counts()

# ── Index-Seite ──────────────────────────────────────────────────────────────

def render_table(rows, col):
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
        mc = match_counts.get(r['id'], 0)
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
<title>TFVHH ELO Rangliste</title>
<style>{SHARED_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="inner">
      <h1>ELO RANGLISTE</h1>
      <span class="sub">Tischfußballverband Hamburg</span>
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

  <footer>TFVHH ELO Rangliste · generiert {generated_at}</footer>
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
    # Nur Spieler mit wirklich gespielten Matches
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

    # Chart-Daten aufbereiten
    labels = []
    combined_data = []
    single_data = []
    double_data = []

    for h in history:
        d = f"{h['day']:02d}.{h['month']:02d}.{h['year']}"
        labels.append(d)
        combined_data.append(h['combined_rating'])
        if h['match_type'] == 1:
            single_data.append(h['separate_rating'])
            double_data.append(None)
        else:
            single_data.append(None)
            double_data.append(h['separate_rating'])

    chart_labels = json.dumps(labels)
    chart_combined = json.dumps(combined_data)
    chart_single = json.dumps(single_data)
    chart_double = json.dumps(double_data)

    # Statistiken
    elo_c = elo_row.get('combined', 1000)
    elo_s = elo_row.get('single', 1000)
    elo_d = elo_row.get('double', 1000)

    # Rang berechnen
    def get_rank(col, val):
        return next((i+1 for i, r in enumerate(rankings[col]) if r['id'] == pid), '-')

    rank_c = get_rank('combined', elo_c)
    rank_s = get_rank('single', elo_s)
    rank_d = get_rank('double', elo_d)

    page = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name} – TFVHH ELO</title>
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
      <span class="sub">Tischfußballverband Hamburg</span>
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
      <div class="label">Spiele</div>
      <div class="value" style="color:var(--text)">{mc}</div>
    </div>
  </div>

  <div class="chart-card">
    <h3>ELO ENTWICKLUNG – GESAMT (COMBINED)</h3>
    <div class="chart-wrap"><canvas id="chartCombined"></canvas></div>
  </div>
  <div class="chart-card">
    <h3>ELO ENTWICKLUNG – EINZEL &amp; DOPPEL</h3>
    <div class="chart-wrap"><canvas id="chartSeparate"></canvas></div>
  </div>

  <footer>TFVHH ELO Rangliste · generiert {generated_at}</footer>
</div>

<script>
const labels = {chart_labels};
const combinedData = {chart_combined};
const singleData = {chart_single};
const doubleData = {chart_double};

const chartDefaults = {{
  responsive: true,
  maintainAspectRatio: false,
  interaction: {{ intersect: false, mode: 'index' }},
  plugins: {{
    legend: {{ labels: {{ color: '#94a3b8', font: {{ family: 'DM Sans', size: 12 }} }} }},
    tooltip: {{
      backgroundColor: '#161a23',
      borderColor: '#252a38',
      borderWidth: 1,
      titleColor: '#e2e8f0',
      bodyColor: '#94a3b8',
    }}
  }},
  scales: {{
    x: {{
      ticks: {{ color: '#4a5568', maxTicksLimit: 10, font: {{ size: 11 }} }},
      grid: {{ color: '#1a1f2e' }},
    }},
    y: {{
      ticks: {{ color: '#4a5568', font: {{ size: 11 }} }},
      grid: {{ color: '#1a1f2e' }},
    }}
  }}
}};

new Chart(document.getElementById('chartCombined'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [{{
      label: 'Combined ELO',
      data: combinedData,
      borderColor: '#e8c847',
      backgroundColor: 'rgba(232,200,71,0.08)',
      borderWidth: 2,
      pointRadius: 2,
      pointHoverRadius: 5,
      fill: true,
      tension: 0.3,
      spanGaps: false,
    }}]
  }},
  options: chartDefaults
}});

new Chart(document.getElementById('chartSeparate'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{
        label: 'Einzel',
        data: singleData,
        borderColor: '#4a9eff',
        backgroundColor: 'rgba(74,158,255,0.06)',
        borderWidth: 2,
        pointRadius: 2,
        pointHoverRadius: 5,
        fill: false,
        tension: 0.3,
        spanGaps: false,
      }},
      {{
        label: 'Doppel',
        data: doubleData,
        borderColor: '#34d399',
        backgroundColor: 'rgba(52,211,153,0.06)',
        borderWidth: 2,
        pointRadius: 2,
        pointHoverRadius: 5,
        fill: false,
        tension: 0.3,
        spanGaps: false,
      }}
    ]
  }},
  options: chartDefaults
}});
</script>
</body>
</html>
"""

    with open(os.path.join(PLAYER_DIR, f"{pid}.html"), "w", encoding="utf-8") as f:
        f.write(page)
    generated_count += 1

print(f"✓ {generated_count} Spielerseiten in players/")
print("Fertig!")
