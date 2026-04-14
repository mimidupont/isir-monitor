"""
ISIR Insolvency Case Monitor — multi-case version
===================================================
Reads cases from cases.json and monitors all of them in one daily run.
To add or remove a case, just edit cases.json — no need to touch this file.
"""

import requests
from bs4 import BeautifulSoup
import json
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ─── CONFIGURATION ────────────────────────────────────────────────────────────

EMAIL_SENDER    = os.environ["EMAIL_SENDER"]
EMAIL_PASSWORD  = os.environ["EMAIL_PASSWORD"]
EMAIL_RECIPIENT = os.environ["EMAIL_RECIPIENT"]

CASES_FILE    = "cases.json"
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

# ─── SCRAPING ─────────────────────────────────────────────────────────────────

def case_url(case_id):
    return f"https://isir.justice.cz/isir/ueu/evidence_upadcu_detail.do?id={case_id}"


def fetch_tab(session, case_id, tab_param):
    url = (
        "https://isir.justice.cz/isir/ueu/evidence_upadcu_detail.do"
        f"?id={case_id}&odkaz={tab_param}"
    )
    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"    [!] Could not fetch tab {tab_param}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = []
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells and any(c for c in cells):
                rows.append(cells)
    return rows


def scrape_case(session, case_id):
    data = {}
    try:
        session.get(case_url(case_id), headers=HEADERS, timeout=30)
    except requests.RequestException as e:
        print(f"  [!] Could not reach case page: {e}")
    for param, name in TABS:
        print(f"    Fetching {name} ...")
        data[param] = fetch_tab(session, case_id, param)
    return data

# ─── SNAPSHOT ─────────────────────────────────────────────────────────────────

def load_snapshot():
    if not os.path.exists(SNAPSHOT_FILE):
        return {}
    with open(SNAPSHOT_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_snapshot(data):
    with open(SNAPSHOT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ─── COMPARISON ───────────────────────────────────────────────────────────────

def find_new_rows(old_case_data, new_case_data):
    changes = {}
    for param, name in TABS:
        old_set = set(json.dumps(r, ensure_ascii=False) for r in old_case_data.get(param, []))
        added   = [r for r in new_case_data.get(param, [])
                   if json.dumps(r, ensure_ascii=False) not in old_set]
        if added:
            changes[param] = (name, added)
    return changes

# ─── EMAIL ────────────────────────────────────────────────────────────────────

def send_email(all_changes):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    subject = f"[ISIR] Zmeny v {len(all_changes)} insolvencnim/ch rizeni/ch - {now}"

    lines = [f"Cas kontroly: {now}", ""]
    for case_label, case_id, changes in all_changes:
        lines.append("=" * 60)
        lines.append(case_label)
        lines.append(case_url(case_id))
        lines.append("")
        for param, (tab_name, rows) in changes.items():
            lines.append(f"  -- {tab_name} --")
            for row in rows:
                lines.append("    * " + " | ".join(str(c) for c in row))
            lines.append("")

    cases_html = ""
    for case_label, case_id, changes in all_changes:
        url = case_url(case_id)
        tables_html = ""
        for param, (tab_name, rows) in changes.items():
            tables_html += f"<h3 style='color:#185FA5;margin:16px 0 4px'>{tab_name}</h3>"
            tables_html += "<table style='border-collapse:collapse;width:100%;font-size:13px;margin-bottom:12px'>"
            for row in rows:
                tables_html += "<tr>" + "".join(
                    f"<td style='border:1px solid #ddd;padding:6px 10px'>{c}</td>" for c in row
                ) + "</tr>"
            tables_html += "</table>"

        cases_html += f"""
        <div style="margin-bottom:32px;padding:16px;border:0.5px solid #ddd;border-radius:8px">
          <h2 style="margin:0 0 4px;font-size:16px;font-weight:500">{case_label}</h2>
          <p style="margin:0 0 12px;font-size:12px;color:#888">
            <a href="{url}">{url}</a>
          </p>
          {tables_html}
        </div>"""

    body_html = f"""<html><body style="font-family:sans-serif;max-width:700px;margin:0 auto;color:#2C2C2A">
  <div style="background:#E6F1FB;border-left:4px solid #378ADD;padding:12px 16px;border-radius:4px;margin-bottom:24px">
    <strong>Nove zaznamy v insolvencnich rizenich</strong><br>
    <span style="font-size:13px;color:#185FA5">{now}</span>
  </div>
  {cases_html}
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

# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"ISIR Monitor - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    with open(CASES_FILE, "r", encoding="utf-8") as f:
        cases = json.load(f)
    print(f"\nMonitoring {len(cases)} case(s).")

    snapshot  = load_snapshot()
    first_run = not snapshot
    if first_run:
        print("  No snapshot found — saving baseline, no alerts sent.")

    all_changes = []

    with requests.Session() as session:
        for case in cases:
            case_id    = case["id"]
            case_label = case["label"]
            print(f"\n>> {case_label}")

            new_data = scrape_case(session, case_id)

            if first_run:
                snapshot[case_id] = new_data
                continue

            old_data = snapshot.get(case_id, {})
            if not old_data:
                # Case newly added to cases.json
                print("  New case — saving baseline, no alert for this one.")
                snapshot[case_id] = new_data
                continue

            changes = find_new_rows(old_data, new_data)
            if not changes:
                print("  No changes.")
            else:
                total = sum(len(r) for _, r in changes.values())
                print(f"  {total} new row(s) found!")
                all_changes.append((case_label, case_id, changes))

            snapshot[case_id] = new_data

    print(f"\n[Summary] {len(all_changes)} case(s) with changes.")
    if all_changes:
        print("Sending email alert...")
        send_email(all_changes)

    print("Saving snapshot...")
    save_snapshot(snapshot)
    print("Done.\n")


if __name__ == "__main__":
    main()
