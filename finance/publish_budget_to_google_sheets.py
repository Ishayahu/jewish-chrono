"""Publish operational budget only. Requires google-api-python-client and google-auth.
Run after the dashboard publisher; reuse its frozen goal from GitHub.
Pass --credentials PATH to a service-account JSON outside the repo,
or set GOOGLE_APPLICATION_CREDENTIALS.
Share the spreadsheet with that service account as editor.
"""
import argparse
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import google.auth
from google.oauth2 import service_account
from googleapiclient.discovery import build
from publish_from_calc import Workbook, cycles_from_book, remote_previous, github_token, existing_password

SHEET_ID = "1nQNEresKTI0b5LzVhmZQhT0AFLmqWhKNlz369CIoCPU"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--book", type=Path, default=Path.home()/"OneDrive"/"Documents"/"Бюджет_2.ods")
    p.add_argument('--credentials', type=Path, help='Path to service-account JSON')
    p.add_argument('--non-interactive', action='store_true', help='Do not prompt for GitHub credentials or dashboard password')
    a = p.parse_args()
    today = datetime.now(ZoneInfo("Europe/Moscow")).date().isoformat()
    cycle = cycles_from_book(Workbook(a.book), datetime.fromisoformat(today).date())[0]
    _, report = remote_previous(github_token(non_interactive=a.non_interactive), existing_password("FINANCE_OWNER_PASSWORD", "Dashboard password", non_interactive=a.non_interactive))
    goal = report.get("dailyGoal", {})
    if goal.get("date") != today or not isinstance(goal.get("target"), (int,float)):
        raise RuntimeError("Publish today's dashboard first; no current frozen goal")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if a.credentials:
        credentials = service_account.Credentials.from_service_account_file(str(a.credentials.expanduser()), scopes=scopes)
    else:
        credentials, _ = google.auth.default(scopes=scopes)
    api = build("sheets", "v4", credentials=credentials).spreadsheets()
    current = api.values().get(spreadsheetId=SHEET_ID, range="'Показатели'!B2").execute().get("values", [])
    if current and current[0][0] == today:
        print("Already published today; preserving operations")
        return
    budgets = cycle["budgets"]
    if not budgets or len(budgets)>999:
        raise RuntimeError("Invalid category count")
    def cell(v):
        return {"userEnteredValue": {"numberValue":v} if isinstance(v,(int,float)) else {"stringValue":v}}
    def write(sheet, row, col, data, endrow, endcol):
        return {"updateCells":{"range":{"sheetId":sheet,"startRowIndex":row,"endRowIndex":endrow,"startColumnIndex":col,"endColumnIndex":endcol},"rows":[{"values":[cell(v) for v in line]} for line in data],"fields":"userEnteredValue"}}
    requests = [
        write(190000001,1,1,[[today],[goal["target"]]],3,2),
        write(190000002,1,0,[[b["name"],b["limit"],b["remaining"]] for b in budgets],1000,3),
        write(190000003,1,0,[],1000,8),
    ]
    api.batchUpdate(spreadsheetId=SHEET_ID,body={"requests":requests}).execute()
    print("Daily operational snapshot published:", today)

if __name__ == "__main__":
    main()
