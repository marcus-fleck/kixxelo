# TFVHH ELO Rangliste

Statische ELO-Rangliste für den Tischfußballverband Hamburg, automatisch generiert via GitHub Actions und veröffentlicht auf GitHub Pages.

## Setup (einmalig)

### 1. GitHub Pages aktivieren
- Repository Settings → Pages
- Source: **Deploy from a branch**
- Branch: `main`, Folder: `/ (root)`
- Speichern → nach ~1 Minute ist die Seite unter `https://<dein-user>.github.io/<repo-name>` erreichbar

### 2. Repo-Struktur
```
├── test.db          ← wird von dir gepusht
├── generate.py      ← generiert die HTML-Dateien
├── index.html       ← wird automatisch generiert
├── players/         ← wird automatisch generiert
│   ├── 255.html
│   └── ...
└── .github/
    └── workflows/
        └── generate.yml
```

## Workflow

```bash
# 1. Lokal: neue DB erzeugen (dein Qt-Binary)
./dein_binary --output test.db

# 2. Pushen
git add test.db
git commit -m "update rankings"
git push
```

→ GitHub Action startet automatisch, generiert `index.html` + alle Spielerseiten und pusht sie zurück ins Repo. GitHub Pages veröffentlicht sie innerhalb von Sekunden.

## Lokale Vorschau

```bash
python3 generate.py test.db .
# Dann index.html im Browser öffnen
```
