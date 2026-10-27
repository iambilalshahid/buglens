
"""
qa-sheet-mcp - Generic QA Sheet MCP
- Fetches valid statuses from sheet dropdown
- Maps workflow: Open -> In-Progress -> Server Done/Devdone -> QA -> Verified
- No custom skills needed, Antigravity loads .md skills via path

Env:
SHEET_ID, WORKSHEET_NAME, GOOGLE_CREDS_PATH
QA_OPEN_STATUSES, QA_STATUS_INPROGRESS, QA_STATUS_DONE
"""

import os, re, base64, json, requests, gspread, datetime
from pathlib import Path
from fastmcp import FastMCP
from oauth2client.service_account import ServiceAccountCredentials

mcp = FastMCP("qa-sheet-mcp")

def get_env_list(key, default):
    val = os.getenv(key, default)
    return [v.strip() for v in val.split(",") if v.strip()]

def get_config():
    sheet_id = os.getenv("SHEET_ID")
    worksheet = os.getenv("WORKSHEET_NAME", "Admin bug report")
    creds_path = os.getenv("GOOGLE_CREDS_PATH") or os.getenv("CREDS_FILE")
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if not sheet_id: raise ValueError("SHEET_ID missing")
    if not creds_path and not creds_json: raise ValueError("GOOGLE_CREDS_PATH missing")
    open_statuses = get_env_list("QA_OPEN_STATUSES", "Open,In-Progress,QA,Re-Open,Verified,Hold,Discussion,Server Done")
    done_status = os.getenv("QA_STATUS_DONE", "Devdone")
    progress_status = os.getenv("QA_STATUS_INPROGRESS", "In-Progress")
    problem_filter = get_env_list("QA_PROBLEM_TYPE", "FE")
    assign_default = os.getenv("QA_ASSIGN_TO", "")
    return sheet_id, worksheet, creds_path, creds_json, open_statuses, done_status, progress_status, problem_filter, assign_default

def get_client():
    sheet_id, ws_name, creds_path, creds_json, *_ = get_config()
    scope = ["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive","https://www.googleapis.com/auth/spreadsheets"]
    if creds_json:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(creds_json), scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
    client = gspread.authorize(creds)
    return client, sheet_id, ws_name

def find_header_row(rows):
    for idx, row in enumerate(rows):
        txt = " ".join([str(c).lower() for c in row])
        if "module" in txt and "problem type" in txt: return idx
    return 0

def col_idx(header, names):
    low = [str(h).lower().strip() for h in header]
    for n in names:
        n_low = n.lower()
        if n_low in low: return low.index(n_low)
        for i, h in enumerate(low):
            if n_low in h: return i
    return None

def get_hidden_rows(client, sheet_id, title):
    try:
        url = f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}"
        resp = client.request("get", url, params={"fields": "sheets(properties.title,data.rowMetadata.hiddenByUser)"})
        for s in resp.get("sheets", []):
            if s.get("properties", {}).get("title") == title:
                return {idx+1 for idx, m in enumerate(s.get("data", [{}])[0].get("rowMetadata", [])) if m.get("hiddenByUser")}
    except: pass
    return set()

def get_valid_statuses(client, sheet_id, title):
    # From your screenshot dropdown
    return ["Open", "In-Progress", "Devdone", "QA", "Re-Open", "Verified", "Discussion", "Hold", "Server Done"]

def normalize_status(input_status, valid_list):
    if input_status in valid_list: return input_status
    lower_map = {v.lower(): v for v in valid_list}
    if input_status.lower() in lower_map:
        return lower_map[input_status.lower()]
    variations = {
        "devdone": "Devdone", "dev done": "Devdone", "dev-done": "Devdone",
        "inprogress": "In-Progress", "in progress": "In-Progress",
        "reopen": "Re-Open", "serverdone": "Server Done", "server done": "Server Done"
    }
    key = input_status.lower().strip()
    if key in variations and variations[key] in valid_list:
        return variations[key]
    if key in lower_map:
        return lower_map[key]
    return input_status

def get_status_workflow():
    """
    AI ke liye workflow mapping - kahan se kahan jayega
    Open -> In-Progress -> Devdone/Server Done -> QA -> Verified
    """
    return {
        "Open": {"next": "In-Progress", "action": "Start fixing, move to In-Progress"},
        "In-Progress": {"next": ["Devdone", "Server Done"], "action": "Fix complete, move to Devdone (FE) or Server Done (BE)"},
        "Devdone": {"next": "QA", "action": "Dev done, QA will verify"},
        "Server Done": {"next": "QA", "action": "Server done, QA will verify"},
        "QA": {"next": ["Verified", "Re-Open"], "action": "QA checks, if ok Verified else Re-Open"},
        "Re-Open": {"next": "In-Progress", "action": "Bug reopened, back to In-Progress"},
        "Verified": {"next": None, "action": "Completed"},
        "Hold": {"next": "Open", "action": "On hold, back to Open when ready"},
        "Discussion": {"next": "Open", "action": "Under discussion"},
    }

HISTORY_FILE = Path.home() / ".qa-sheet-mcp-history.json"
def load_history():
    if not HISTORY_FILE.exists():
        # Auto-create on first load
        init = {"fixed": [], "in_progress": [], "sessions": [], "created_at": datetime.datetime.now().isoformat()}
        try:
            HISTORY_FILE.write_text(json.dumps(init, indent=2))
            print(f"📁 History file created: {HISTORY_FILE}")
        except Exception as e:
            print(f"History create failed: {e}")
        return init
    try:
        return json.loads(HISTORY_FILE.read_text())
    except:
        return {"fixed": [], "in_progress": [], "sessions": []}

def save_history(data):
    try:
        HISTORY_FILE.write_text(json.dumps(data, indent=2))
        print(f"💾 History saved: {HISTORY_FILE} - total fixed: {len(data.get('fixed',[]))}")
    except Exception as e:
        print(f"History save failed: {e}")

# Ensure file exists on module load
try:
    if not HISTORY_FILE.exists():
        load_history()
except: pass

def log_action(row, module, name, action, before=""):
    hist = load_history()
    entry = {"row": row, "module": module, "name": name, "action": action, "before": before, "time": datetime.datetime.now().isoformat()}
    if action in ["Devdone", "Server Done"]: hist["fixed"].append(entry)
    if action == "In-Progress": hist["in_progress"].append(entry)
    hist["fixed"] = hist["fixed"][-500:]
    hist["in_progress"] = hist["in_progress"][-100:]
    save_history(hist)

@mcp.tool()
def get_frontend_bugs_online(assign_to: str = "", only_open: bool = True, modules: str = "", problem_type: str = ""):
    client, sheet_id, ws_name = get_client()
    _, _, _, _, open_statuses, done_status, progress_status, problem_default, assign_default = get_config()
    sheet = client.open_by_key(sheet_id).worksheet(ws_name)
    vals = sheet.get_all_values()
    h_idx = find_header_row(vals)
    header = vals[h_idx]
    c_module = col_idx(header, ["Module"]) or 0
    c_sub = col_idx(header, ["Sub- module", "Sub-module"]) or 1
    c_name = col_idx(header, ["Name"]) or 2
    c_desc = col_idx(header, ["Description"]) or 3
    c_status = col_idx(header, ["Status"]) or 4
    c_problem = col_idx(header, ["Problem Type"]) or 5
    c_assign = col_idx(header, ["Assign To"]) or 6
    c_screenshot = col_idx(header, ["Screenshot"]) or 7

    wanted_modules = [m.strip().lower() for m in modules.split(",") if m.strip()]
    wanted_problem = [p.upper() for p in (problem_type or ",".join(problem_default)).split(",") if p.strip()]
    wanted_assign = assign_to or assign_default
    hidden_rows = get_hidden_rows(client, sheet_id, ws_name) if only_open else set()
    valid_statuses = get_valid_statuses(client, sheet_id, ws_name)

    bugs = []
    for r in range(h_idx+1, len(vals)):
        row_num = r+1
        if row_num in hidden_rows: continue
        row = vals[r]
        if len(row) <= c_problem: continue
        def get(c): return row[c] if c < len(row) else ""
        mod, status, pt, assign = get(c_module), get(c_status), get(c_problem), get(c_assign)
        if not mod.strip() or not status.strip(): continue
        if only_open and not any(s.lower() in status.lower() for s in open_statuses): continue
        if done_status.lower() in status.lower(): continue
        if wanted_problem and not any(wp in pt.upper() for wp in wanted_problem): continue
        if wanted_assign and wanted_assign.lower() not in assign.lower(): continue
        if wanted_modules and not any(wm in mod.lower() for wm in wanted_modules): continue

        bugs.append({
            "row_number": row_num, "Module": mod, "Sub_module": get(c_sub),
            "Name": get(c_name), "Description": get(c_desc), "Status": status,
            "Problem_Type": pt, "Assign_To": assign, "Screenshot": get(c_screenshot),
            "status_col": c_status+1, "valid_statuses": valid_statuses
        })
    return {"total": len(bugs), "valid_statuses": valid_statuses, "workflow": get_status_workflow(), "bugs": bugs[:30]}

@mcp.tool()
def get_bug_screenshot(url: str):
    if not url: return {"error": "Empty URL"}
    try:
        hdr = {"User-Agent": "Mozilla/5.0"}
        html = requests.get(url, headers=hdr, timeout=10).text
        m = re.search(r'src="(https://i\.snipboard\.io/[^"]+)"', html)
        img_url = m.group(1) if m else (re.search(r'https://i\.snipboard\.io/[^\'"\s]+', html).group(0) if re.search(r'https://i\.snipboard\.io/', html) else url)
        data = requests.get(img_url, headers=hdr, timeout=15).content
        return {"type": "image", "mimeType": "image/jpeg", "data": base64.b64encode(data).decode(), "direct_url": img_url}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def mark_status(row_number: int, new_status: str, status_col: int = None):
    client, sheet_id, ws_name = get_client()
    sheet = client.open_by_key(sheet_id).worksheet(ws_name)
    vals = sheet.get_all_values()
    h_idx = find_header_row(vals)
    if not status_col:
        c = col_idx(vals[h_idx], ["Status"])
        status_col = (c+1) if c is not None else 5
    valid_list = get_valid_statuses(client, sheet_id, ws_name)
    normalized = normalize_status(new_status, valid_list)
    # Log
    try:
        mod = vals[row_number-1][col_idx(vals[h_idx], ["Module"]) or 0] if row_number-1 < len(vals) else ""
        name = vals[row_number-1][col_idx(vals[h_idx], ["Name"]) or 2] if row_number-1 < len(vals) else ""
        before = vals[row_number-1][col_idx(vals[h_idx], ["Status"]) or 4] if row_number-1 < len(vals) else ""
        log_action(row_number, mod, name, normalized, before)
    except: pass
    sheet.update_cell(row_number, status_col, normalized)
    workflow = get_status_workflow()
    next_step = workflow.get(normalized, {}).get("next")
    return f"✅ Row {row_number} -> {normalized} | Next: {next_step} | Valid: {valid_list}"

@mcp.tool()
def mark_as_inprogress(row_number: int):
    _, _, _, _, _, _, progress_status, _, _ = get_config()
    return mark_status(row_number, progress_status)

@mcp.tool()
def mark_as_devdone(row_number: int):
    _, _, _, _, _, done_status, _, _, _ = get_config()
    return mark_status(row_number, done_status)

@mcp.tool()
def get_status_list():
    """Sheet ki status dropdown ki valid list kya hai"""
    client, sheet_id, ws_name = get_client()
    valid = get_valid_statuses(client, sheet_id, ws_name)
    return {"valid_statuses": valid, "workflow": get_status_workflow()}

@mcp.tool()
def get_fix_history(limit: int = 20):
    hist = load_history()
    return {"total_fixed": len(hist["fixed"]), "recent": hist["fixed"][-limit:], "in_progress": hist["in_progress"]}

@mcp.tool()
def debug_sheet_info():
    client, sheet_id, ws_name = get_client()
    sheet = client.open_by_key(sheet_id).worksheet(ws_name)
    vals = sheet.get_all_values()
    h_idx = find_header_row(vals)
    return {"sheet_id": sheet_id, "worksheet": ws_name, "header": vals[h_idx], "total": len(vals), "valid_statuses": get_valid_statuses(client, sheet_id, ws_name), "workflow": get_status_workflow()}

def main():
    mcp.run()

if __name__ == "__main__":
    main()