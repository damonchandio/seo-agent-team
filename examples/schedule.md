# Running the daily routine

`python -m seo_agent_team run` does one day's work: it tracks rankings every day, writes on `SEO_WRITE_DAYS` and
refreshes on `SEO_REFRESH_DAY`. Schedule it once a day.

## Linux or macOS (cron)

Run `crontab -e` and add (07:15 every day):

```
15 7 * * * cd /path/to/seo-agent-team && /path/to/venv/bin/python -m seo_agent_team run >> seo-data/run.log 2>&1
```

## Windows (Task Scheduler)

```
schtasks /Create /SC DAILY /ST 07:15 /TN "seo-agent-team" ^
  /TR "cmd /c cd /d C:\path\to\seo-agent-team && C:\path\to\venv\Scripts\python.exe -m seo_agent_team run >> seo-data\run.log 2>&1"
```

## From your own Python program

```python
from seo_agent_team import team
for line in team.run():
    print(line)
```
