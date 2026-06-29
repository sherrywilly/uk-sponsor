Run backend API:
1) python -m venv .venv && source .venv/bin/activate
2) pip install -r requirements.txt
3) playwright install chromium
4) uvicorn backend.api:app --reload --port 8000
