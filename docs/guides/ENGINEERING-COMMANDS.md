# Engineering Commands

## One-time

```powershell
powershell -ExecutionPolicy Bypass -File scripts/enable-hooks.ps1
```

## Health Check (Before Start)

```powershell
powershell -ExecutionPolicy Bypass -File agent-platform/scripts/health-check.ps1
```

## Plan Mode

```powershell
powershell -ExecutionPolicy Bypass -File scripts/plan-mode.ps1 -Root . -Goal "your change goal"
```

## Compact Context

```powershell
powershell -ExecutionPolicy Bypass -File scripts/compact-context.ps1 -Topic "what changed"
```

## Quality Gate

```powershell
powershell -ExecutionPolicy Bypass -File scripts/quality-gate.ps1
```

## Hermes Reinforcement Loop

```powershell
powershell -ExecutionPolicy Bypass -File scripts/hermes-reinforce.ps1 -Root .
```

输出报告目录：

```powershell
output/hermes-reports/
```

## Run GUI (Production)

```powershell
cd agent-platform
$env:PYTHONPATH = "src"
streamlit run app_robust.py
```
