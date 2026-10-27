# 🤖 AGENT GUIDE - qa-sheet-mcp

> For Antigravity / Gemini / Claude / Cursor - How to use QA Sheet MCP without seeing code

## What this MCP does
This MCP connects to **live Google Sheet** online. No CSV import.
It gives you QA bugs assigned to a dev, with screenshot vision support.

**You as agent will:**
1. Fetch bugs from sheet
2. SEE screenshot (base64 image)
3. Fix code in repo
4. Update sheet status

---

## 🔧 Setup - mcp.json (Antigravity)

Dev will add this in Antigravity MCP config. You don't configure, but know what envs mean:

```json
{
  "mcpServers": {
    "qa-sheet": {
      "command": "/home/bilal/qa-sheet-mcp-package/venv/bin/python",
      "args": ["-m", "qa_sheet_mcp.server"],
      "env": {
        "SHEET_ID": "1l03GUlLG1FJ9A1RBgLJoSulaP_DkxwVoGOHdnap8kDU",
        "WORKSHEET_NAME": "Admin bug report",
        "GOOGLE_CREDS_PATH": "/home/bilal/qa-sheet-mcp-package/credentials.json",
        "QA_ASSIGN_TO": "Bilal",
        "QA_PROBLEM_TYPE": "FE",
        "QA_STATUS_DONE": "Devdone",
        "QA_STATUS_INPROGRESS": "In-Progress"
      }
    }
  }
}
```

### Customization (for other devs/teams)

| Env | What to change | Example |
|-----|----------------|---------|
| `SHEET_ID` | Your sheet URL id | `1l03...` from docs.google.com/spreadsheets/d/<THIS>/edit |
| `WORKSHEET_NAME` | Tab name | `Admin bug report`, `Student bug report` |
| `GOOGLE_CREDS_PATH` | Service account json path | `C:/creds.json` or `/home/user/creds.json` |
| `QA_ASSIGN_TO` | Filter by dev name | `Bilal`, `Ahmar` |
| `QA_PROBLEM_TYPE` | FE or BE bugs | `FE`, `BE`, `FE,BE` |
| `QA_STATUS_DONE` | Done status exact name | `Devdone` (must match sheet dropdown) |
| `QA_STATUS_INPROGRESS` | Progress status | `In-Progress` |

**Note:** `Devdone` not `DevDone` - sheet dropdown is case-sensitive. MCP auto-fixes case.

---

## 🔄 Workflow you must follow

```
1. get_frontend_bugs_online(assign_to="Bilal", only_open=True)
   -> Returns bugs with row_number, Module, Name, Description, Screenshot URL, valid_statuses, workflow

2. For each bug:
   a. get_bug_screenshot(url) -> You will SEE the image (vision)
   b. mark_as_inprogress(row_number) -> Open -> In-Progress
   
   c. Fix code in repo based on Module:
      - Certificates, Dashboard, Student, System Setting, Planning
      - Student->Student List, Instructor->Instructor List
      - LMS->Lecture-notes, instructor->attendance
      - students->attendance->add, course-planner->add
      - planning->all-batches, planning->zoom-accounts
      - certificates->rules/templates, notifications->templates
      - system-setting->users/roles/branches
      
      Ignore: Announcement, Feedback, Fees (for testing)

   d. mark_as_devdone(row_number) -> In-Progress -> Devdone
      (or mark_status with Server Done for BE bugs)

3. get_fix_history() -> See what you fixed
```

---

## 📊 Status Workflow (auto mapped from sheet)

```
Open → In-Progress → Devdone / Server Done → QA → Verified
          ↑                                      |
          └────────── Re-Open ←──────────────────┘
Hold → Open
Discussion → Open
```

- `Open`: New bug, you should start -> `In-Progress`
- `In-Progress`: You are fixing
- `Devdone`: FE fixed, `Server Done`: BE fixed -> QA will check
- `QA`: QA team checking
- `Verified`: Done
- `Re-Open`: Bug came back -> `In-Progress` again

**MCP gives you valid_statuses and workflow in every response. Use that, don't guess.**

---

## ⚠️ Important Rules

1. **Always call get_bug_screenshot** - Don't fix without seeing image
2. **Use row_number from tool** - Don't guess row numbers
3. **Case matters** - Use exact status from valid_statuses list
4. **Hidden rows** - MCP already skips hiddenByUser rows, don't worry
5. **Assign To filter** - Only fix bugs assigned to current dev (Bilal/Ahmar)
6. **Problem Type** - Respect FE/BE filter from env
7. **One by one** - Fix row-by-row, not bulk

---

## 🛠️ Tools you have

- `get_frontend_bugs_online` - Get bugs
- `get_bug_screenshot` - See screenshot
- `mark_as_inprogress` - Start fixing
- `mark_as_devdone` - Mark done
- `mark_status` - Custom status (with auto case fix)
- `get_status_list` - Get valid dropdown values + workflow
- `get_fix_history` - See past fixes
- `debug_sheet_info` - Sheet info

---

## Example Agent Prompt

```
Fetch FE bugs for Bilal from online sheet.
For each bug, download screenshot, fix the UI issue in code, then mark Devdone.
Follow status workflow: Open -> In-Progress -> Devdone.
```

That's it. No code needed to know. Just use tools in order.
