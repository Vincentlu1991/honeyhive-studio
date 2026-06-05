# Hermes Personal Secretary

A local-first file secretary system powered by Hermes-style summarization.

## What It Does

- Collects files from:
  - Telegram bot uploads
  - Outlook email attachments
  - Existing local folders (for bulk onboarding)
- Reads and extracts text from: txt, md, json, csv, pdf, xlsx/xls, docx, pptx
- Auto-classifies files by project and category.
- Places files into organized folders per project.
- Builds a dashboard with:
  - Expense/income estimation with strict expense scope policy
  - Category distribution
  - Hermes summaries for quick review

## Finance Scope Policy

- Expense is counted when a document is from Outlook or uploaded files (`chat_upload`) and matches one of these categories:
  - UOB transfer
  - Utilities (water/electric/gas)
  - Internet/broadband
  - Phone/telco bill
- Expense also requires audit evidence in file content:
  - has valid amount and billing/payment context
  - has expense/bill style wording
  - passes date audit (bill date evidence or file created date, with consistency check)
- Dashboard provides an expense audit review queue for rejected candidates and supports one-click manual override.
- Documents outside this scope are ignored for expense totals to reduce false positives.

## Dedicated Life Expense Folder

- Life expense related files are auto-organized to a dedicated folder:
  - `data/organized/life_expenses/uob_transfer`
  - `data/organized/life_expenses/utilities`
  - `data/organized/life_expenses/internet`
  - `data/organized/life_expenses/phone`

## Current Test Source

- `E:/Dropbox` -> recursive scan of the whole Dropbox tree

## Folder Layout

```text
personal-secretary/
  app_dashboard.py
  run_sync.py
  .env
  data/
    inbox/
    organized/
    reports/
  src/personal_secretary/
```

## Quick Start

1. Create venv and install requirements:

```powershell
cd "C:\Users\User\OneDrive\文档\New project\personal-secretary"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. Run one sync:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe run_sync.py
```

3. Open dashboard:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\streamlit.exe run app_dashboard.py
```

## Dashboard UI Features

- Sidebar status panel for Telegram/Outlook/folder connectors
- Agent runtime controls:
  - Start/Stop agent button
  - Backend select: Auto (Hermes -> Ollama), Hermes CLI, Ollama Local
  - Task Profile selector with one-click recommended local model
  - Local model select (with custom model override)
  - Precision mode: Fast / Balanced / High Accuracy
- `Run Full Sync` button (collect + classify + analyze)
- `Run Analysis Only` button
- `Secretary Chat` tab:
  - ask questions to your secretary
  - attach files in the same message
  - uploaded files are auto-indexed and auto-classified
  - assistant answers based on indexed files + new attachments
- Folder incremental organizer:
  - input any folder path and project name
  - system scans and skips already indexed files automatically
  - only new files are organized and analyzed

## Multi-Agent Collaboration (New)

- New tab: `Agent Collaboration`
- Shows recommended agent team for your current project mix (entrepreneurship + data science)
- Visual flow graph of collaboration:
  - Supervisor -> Retriever/DocumentReader/FileOps/Finance/Learning/BusinessPlan -> Report -> QA
- One-click orchestration run with objective selection:
  - Weekly Executive Review
  - Expense and Income Review
  - Study Roadmap
  - Business Plan Draft
  - Cross-Project Strategic Summary
- Live execution progress:
  - progress bar updates after each agent finishes
  - live step table shows current status in run-time
- Agent parameter panel:
  - Retriever Top-K and include-subject option
  - Finance minimum amount filter
  - Learning weeks and topic limit
  - Business plan style (concise/detailed/investor)
  - QA business-plan-required toggle
- New employee: Document Reader Agent
  - Focuses on precise reading for image/Word/PDF/CSV evidence
  - Produces evidence-backed summary, format coverage, and image-readiness hints
- Execution board includes per-agent:
  - status (completed/failed)
  - duration
  - duty
  - error if any

Persistence:
- Latest multi-agent run is saved in SQLite (`agent_runs` table)
- Chat history is saved in SQLite (`chat_messages` table)

## Incremental Folder Behavior

- If a folder was already fully processed, dashboard shows `Folder already organized`.
- If only part of the folder is new, only new files are copied/classified.
- Deduping is done by source identity (path + size + mtime fingerprint).

## Telegram Setup

- Bot token already set in local `.env`.
- Send a file to `t.me/Bee_Lu_Bot`.
- Send a text message to the bot to get a secretary-style reply based on your indexed files.
- To get real-time replies, run the Telegram poller in a separate terminal:

```powershell
cd "C:\Users\User\OneDrive\文档\New project\personal-secretary"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe run_telegram_bot.py
```
- If you want to restrict uploads to your chat only:
  - set `TELEGRAM_ALLOWED_CHAT_ID`
  - run once and inspect `data/state.json` to see update offsets

## Outlook Setup (Microsoft Graph)

1. Register an app in Azure Portal.
2. Add delegated permission: `Mail.Read`.
3. Set `OUTLOOK_CLIENT_ID` in `.env`.
4. Set `OUTLOOK_ENABLED=true`.
5. First run uses device login flow.

## Notes

- `SECRETARY_COPY_ONLY=true` means source files are copied, not moved.
- If Hermes CLI is installed at default path under LOCALAPPDATA, it is used automatically.
- If Hermes is unavailable, system falls back to a lightweight local summary.
- For image OCR, install Tesseract and set `TESSERACT_CMD` to `tesseract.exe` full path.
- Document Reader Agent now outputs evidence references, confidence, conflict hints, and redaction stats.

## Requirement Validation

Run this command to validate the read -> analyze -> classify requirements:

```powershell
cd "C:\Users\User\OneDrive\文档\New project\personal-secretary"
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m unittest tests/test_requirements_read_analyze_classify.py
```

The test verifies:
- Docx/pptx text extraction is available.
- Expense policy counts only qualified Outlook expense documents.
- File classification writes project/category correctly.
