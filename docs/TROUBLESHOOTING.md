# Troubleshooting

- **pydantic-core wheel failure:** use Python 3.12, not Python 3.14.
- **No module named uvicorn:** activate the project `.venv` or rerun `run_windows.bat`.
- **Server appears to repeat:** do not use `--reload` for normal use.
- **AI disabled:** configure one authorized provider model or `OLLAMA_MODEL`.
- **AI provider cooling down:** wait for its reset or reorder the task route.
- **No jobs:** enable sources, check source health and retry the failed source.
- **Too many unrelated jobs:** verify target titles and relevant experience, then rescan.
- **Cloud sync pending:** local data is safe; verify database URLs and run sync again.
- **Export blocked:** explicitly approve the generated artifact first.
- **Restore blocked:** select a listed backup and type `RESTORE BACKUP` exactly.

Run `python scripts/preflight.py` and `python -m pytest -q` when reporting a defect.
Never paste secrets, full connection strings or private resume text into an issue.
