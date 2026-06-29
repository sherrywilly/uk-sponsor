# UK Sponsor CSV

This repository now includes a minimal Docker setup to preview the bundled CSV file.

## Build and run with Docker

```bash
docker build -t uk-sponsor-csv-preview .
docker run --rm uk-sponsor-csv-preview
```

## Build and run with Docker Compose

```bash
docker compose up --build
```

## Custom input file or row count

```bash
docker run --rm \
  -v "$PWD:/workspace" \
  uk-sponsor-csv-preview \
  --file /workspace/SP_-_Worker_and_Temporary_Worker_Web_Register_-_2026-06-26.csv \
  --rows 20
```
