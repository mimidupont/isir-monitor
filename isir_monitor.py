"""
ISIR Insolvency Case Monitor
Runs daily via GitHub Actions — no laptop or server needed.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

CASE_URL = "https://isir.justice.cz/isir/ueu/evidence_upadcu_detail.do?id=322989793181EED0E06333F21FAC4CE5"
BASE_ID  = "322989793181EED0E06333F21FAC4CE5"

# These are loaded from GitHub Secrets — you never put passwords in code
EMAIL_SENDER    = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD  = os.environ["EMAIL_PASSWORD"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]

SNAPSHOT_FILE = "isir_snapshot.json"

TABS = [
    ("A", "Oddil A - Rizeni do upadku"),
    ("B", "Oddil B - Rizeni po upadku"),
    ("C", "Oddil C - Incidencni spory"),
    ("D", "Oddil D - Ostatni"),
    ("P", "Oddil P - Prihlasky"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "cs,en;q=0.9",
    "Referer": "https://isir.justice.cz/",
}


def fetch_tab(session, tab_param):
    url = (
        "https://isir.justice.cz/isir/ueu/evidence_upadcu_detail.do"
        f"?id={BASE_ID}&odkaz={tab_param}"
    )
    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [!] Could not fetch tab {tab_param}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells and any(c for c in cells):
                rows.append(cells)
    return rows


def scrape_all_tabs():
    data = {}
    with requests.Session() as session:
        try:
            session.get(CASE_URL, headers=HEADERS, timeout=30)
        except requests.RequestException as e:
            print(f"[!] Could not reach main page: {e}")
        for param, name in TABS:
            print(f"  Fetching: {name} ...")
            data[param] = fetch_tab(session, param)
    return data


def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(data):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_new_rows(old_data, new_data):
    changes = {}
    for param, name in TABS:
        old_set = set(json.dumps(r, ensure_ascii=False) for r in old_data.get(param, []))
        added   = [r for r in new_data.get(param, [])
                   if json.dumps(r, ensure_ascii=False) not in old_set]
        if added:
            changes[param] = (name, added)
    return changes


def send_email(changes):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"[ISIR] Nove zaznamy v insolvencnim rizeni - {now}"

    lines = [
        "Byly nalezeny nove zaznamy v insolvencnim rejstriku.",
        f"Pripad: {CASE_URL}",
        f"Cas kontroly: {now}", "",
    ]
    for param, (tab_name, rows) in changes.items():
        lines.append(f"-- {tab_name} --")
        for row in rows:
            lines.append("  * " + " | ".join(str(c) for c in row))
        lines.append("")
    lines += ["-" * 60, CASE_URL]

    tables_html = ""
    for param, (tab_name, rows) in changes.items():
        tables_html += f"<h3 style='color:#185FA5;margin:16px 0 4px'>{tab_name}</h3>"
        tables_html += "<table style='border-collapse:collapse;width:100%;font-size:13px'>"
        for row in rows:
            tables_html += "<tr>" + "".join(
                f"<td style='border:1px solid #ddd;padding:6px 10px'>{c}</td>" for c in row
            ) + "</tr>"
        tables_html += "</table>"

    body_html = f"""<html><body style="font-family:sans-serif;max-width:700px;margin:0 auto;color:#2C2C2A">
  <div style="background:#E6F1FB;border-left:4px solid #378ADD;padding:12px 16px;border-radius:4px;margin-bottom:16px">
    <strong>Nove zaznamy v insolvencnim rizeni</strong><br>
    <span style="font-size:13px;color:#185FA5">{now}</span>
  </div>
  {tables_html}
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
  <p style="font-size:12px;color:#888">Primy odkaz: <a href="{CASE_URL}">{CASE_URL}</a></p>
</body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_SENDER
    msg["To"]      = EMAIL_RECIPIENT
    msg.attach(MIMEText("\n".join(lines), "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECIPIENT, msg.as_bytes())
    print(f"  [OK] Alert sent to {EMAIL_RECIPIENT}")


def main():
    print(f"\n{'='*60}")
    print(f"ISIR Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    print("\n[1] Scraping all tabs...")
    new_data = scrape_all_tabs()

    print("\n[2] Loading previous snapshot...")
    old_data = load_snapshot()

    if not old_data:
        print("  First run - saving baseline. No alert sent.")
        save_snapshot(new_data)
        print(f"  Saved {sum(len(v) for v in new_data.values())} rows total.")
        return

    print("\n[3] Comparing snapshots...")
    changes = find_new_rows(old_data, new_data)

    if not changes:
        print("  No changes found.")
    else:
        total = sum(len(r) for _, r in changes.values())
        print(f"  {total} new row(s) in {len(changes)} tab(s) - sending alert...")
        send_email(changes)

    print("\n[4] Saving updated snapshot...")
    save_snapshot(new_data)
    print("  Done.\n")


if __name__ == "__main__":
    main()
