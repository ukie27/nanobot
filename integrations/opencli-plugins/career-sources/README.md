# Career Sources OpenCLI Plugin

This project-owned plugin extends the external OpenCLI installation without modifying OpenCLI source.

Install or relink it once per machine:

```powershell
opencli plugin install file:///D:/project/job-agent/nanobot-career/integrations/opencli-plugins/career-sources
```

Daily automation is deliberately limited to the current China calendar day:

```powershell
opencli nowcoder schedule --lookback 0 --limit 500 -f json
```

Historical retrieval is manual-only and capped at the latest 30 days:

```powershell
opencli nowcoder schedule --lookback 7 -f json
opencli nowcoder schedule --lookback 14 -f json
opencli nowcoder schedule --lookback 30 -f json
```

The command is read-only. It does not apply, subscribe, follow, message, bypass access controls, or read credentials.
