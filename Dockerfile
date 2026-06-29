FROM python:3.12-slim

WORKDIR /app

COPY scripts/preview_csv.py /app/scripts/preview_csv.py
COPY SP_-_Worker_and_Temporary_Worker_Web_Register_-_2026-06-26.csv /app/data.csv

ENTRYPOINT ["python", "/app/scripts/preview_csv.py"]
CMD ["--rows", "10"]
