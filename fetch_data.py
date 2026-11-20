"""Récupère l'historique (football-data.co.uk) + matchs récents et à venir (football-data.org) -> data.json"""
import os, io, csv, json, re, time, unicodedata, difflib, datetime as dt
import requests

KEY = os.environ.get("FOOTBALL_DATA_KEY", "")
LEAGUES = {"FL1": "F1", "PL": "E0", "PD": "SP1", "BL1": "D1", "SA": "I1", "CL": "CL"}  # code API -> code CSV
CO_UK = ["F1", "E0", "SP1", "D1", "I1"]
NB_SEASONS = 5
DAYS_AHEAD = 14

STOP = {"fc","afc","cf","ac","as","sc","ssc","rc","ogc","olympique","stade","club","de","the","1901","1899","1909","calcio","fk","sk","if","ud","cd","sd","ca"}
ALIAS = {
 "paris saint germain":"Paris SG","paris":"Paris FC","lyonnais":"Lyon","rennais":"Rennes","losc lille":"Lille",
 "brestois 29":"Brest","strasbourg alsace":"Strasbourg",
 "manchester united":"Man United","manchester city":"Man City","wolverhampton wanderers":"Wolves",
 "tottenham hotspur":"Tottenham","newcastle united":"Newcastle","nottingham forest":"Nott'm Forest",
 "west ham united":"West Ham","brighton and hove albion":"Brighton","leeds united":"Leeds",
 "atletico madrid":"Ath Madrid","athletic":"Ath Bilbao","real sociedad":"Sociedad","real betis balompie":"Betis",
 "rayo vallecano":"Vallecano","celta vigo":"Celta","deportivo alaves":"Alaves",
 "bayern munchen":"Bayern Munich","borussia dortmund":"Dortmund","borussia monchengladbach":"M'gladbach",
 "bayer 04 leverkusen":"Leverkusen","eintracht frankfurt":"Ein Frankfurt","1 fsv mainz 05":"Mainz",
 "tsg hoffenheim":"Hoffenheim","vfb stuttgart":"Stuttgart","vfl wolfsburg":"Wolfsburg",
 "internazionale milano":"Inter","milan":"Milan",
}

def norm(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"[^a-z0-9 ]", " ", s.replace("&", " and "))
    return " ".join(w for w in s.split() if w not in STOP)

def season_codes():
    t = dt.date.today(); y = t.year if t.month >= 8 else t.year - 1
    return [f"{(y-i)%100:02d}{(y-i+1)%100:02d}" for i in range(NB_SEASONS)]

def parse_date(s):
    for f in ("%d/%m/%Y", "%d/%m/%y"):
        try: return dt.datetime.strptime(s.strip(), f).date().isoformat()
        except Exception: pass
    return None

past, seen, names = [], set(), {}

def add(d, div, h, a, hg, ag):
    past.append([d, div, h, a, hg, ag]); seen.add((d, h, a))

# 1) Historique : CSV football-data.co.uk
for s in season_codes():
    for c in CO_UK:
        try:
            r = requests.get(f"https://www.football-data.co.uk/mmz4281/{s}/{c}.csv", timeout=30)
            if r.status_code != 200: continue
            for row in csv.DictReader(io.StringIO(r.content.decode("utf-8-sig", errors="replace"))):
                d = parse_date(row.get("Date") or "")
                h, a = (row.get("HomeTeam") or "").strip(), (row.get("AwayTeam") or "").strip()
                try: hg, ag = int(row["FTHG"]), int(row["FTAG"])
                except Exception: continue
                if d and h and a:
                    add(d, c, h, a, hg, ag); names[norm(h)] = h; names[norm(a)] = a
            print("ok", s, c)
        except Exception as e:
            print("erreur", s, c, e)

def canon(name):
    n = norm(name)
    if n in ALIAS: return ALIAS[n]
    if n in names: return names[n]
    m = difflib.get_close_matches(n, list(names), n=1, cutoff=0.75)
    return names[m[0]] if m else re.sub(r"\b(FC|AFC|CF)\b", "", name).strip()

def exists(d, h, a):
    base = dt.date.fromisoformat(d)
    return any((str(base + dt.timedelta(days=k)), h, a) in seen for k in (-1, 0, 1))

# 2) Récent + à venir : football-data.org (saison en cours, offre gratuite)
fixtures, now = [], dt.datetime.now(dt.timezone.utc)
if not KEY:
    print("Pas de clé FOOTBALL_DATA_KEY : historique seulement, pas de matchs à venir.")
else:
    for code, div in LEAGUES.items():
        try:
            r = requests.get(f"https://api.football-data.org/v4/competitions/{code}/matches",
                             headers={"X-Auth-Token": KEY}, timeout=30)
            r.raise_for_status()
            for m in r.json().get("matches", []):
                h, a = canon(m["homeTeam"]["name"] or ""), canon(m["awayTeam"]["name"] or "")
                d = m["utcDate"][:10]
                if m["status"] == "FINISHED":
                    ft = m["score"]["fullTime"]
                    if ft["home"] is not None and ft["away"] is not None and not exists(d, h, a):
                        add(d, div, h, a, ft["home"], ft["away"])
                elif m["status"] in ("SCHEDULED", "TIMED"):
                    t = dt.datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                    if now <= t <= now + dt.timedelta(days=DAYS_AHEAD):
                        fixtures.append({"t": m["utcDate"], "div": div, "h": h, "a": a})
            print("ok API", code)
        except Exception as e:
            print("erreur API", code, e)
        time.sleep(7)  # limite gratuite : 10 requêtes/minute

past.sort(key=lambda x: x[0]); fixtures.sort(key=lambda x: x["t"])
json.dump({"updated": now.isoformat(timespec="minutes"), "past": past, "fixtures": fixtures},
          open("data.json", "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
print(len(past), "matchs,", len(fixtures), "à venir")
