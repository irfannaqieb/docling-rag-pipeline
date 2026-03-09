# N1 Care

Simple Docker-based setup for:

- `web`: Next.js frontend
- `api`: FastAPI backend
- `docling`: PDF parsing/OCR service

## Prerequisites

- Docker Desktop installed
- NVIDIA GPU support available if you want to run `docling` with `gpus: all`
- A root `.env` file with the ports you want to use
- `apps/api/.env` populated with API-side secrets like `OPENAI_API_KEY`

## Run The Stack

Note: the `docling` Docker image is relatively large and includes OCR/GPU-related dependencies, so the first build can take a while. That is normal.

From the project root:

```powershell
docker compose up --build
```

If you only changed the backend and want to rebuild just that service:

```powershell
docker compose up --build api
```

If the containers are already built and you just want to start them:

```powershell
docker compose up
```

## Main URLs

- Web UI: `http://localhost:<WEB_PORT>`
- API: `http://localhost:<API_PORT>`
- Docling: `http://localhost:<MINERU_PORT>`

The actual values come from the root `.env`.

## Normal Flow

1. Open the web app.
2. Add one or more PDF files.
3. Click `Generate Report`.
4. The frontend sends the files to the API.
5. The API sends each PDF to `docling` for parsing.
6. The API runs normalization, chunking, LLM extraction, and report generation.
7. The final report is returned to the web app.

## Check Progress In Docker Logs

To watch backend progress:

```powershell
docker compose logs api --tail=200 -f
```

To watch PDF parsing/OCR progress:

```powershell
docker compose logs docling --tail=200 -f
```

To watch everything:

```powershell
docker compose logs --tail=200 -f
```

## Useful API Log Messages

These messages were added as sanity checks and are the quickest way to see where a request is:

- `Received /reports/generate request`
- `Parsing upload file=...`
- `Validated parsed document ...`
- `Starting analysis pipeline ...`
- `Chunked document ...`
- `Starting structured extraction ...`
- `Structured extraction completed ...`
- `Completed /reports/generate ...`

If you see parsing logs in `docling` but do not see `Completed /reports/generate` in `api`, the request is getting stuck or failing in the backend after parse.

## Quick Debugging Guide

If nothing seems to happen after upload:

1. Confirm you clicked `Generate Report`, not just selected files.
2. Check the web page for a red error box.
3. Check `api` logs:

```powershell
docker compose logs api --tail=200
```

4. Check `docling` logs:

```powershell
docker compose logs docling --tail=200
```

## Common Cases

`docling` shows `POST /parse 200 OK` but no report appears:

- Parsing worked.
- The issue is likely in the `api` service after parsing.
- Check `api` logs for analysis or LLM errors.
- Maybe it is still loading.

You changed Python code but behavior did not change:

- Rebuild the `api` container:

```powershell
docker compose up --build api
```

You changed frontend code but do not see the update:

- Rebuild the `web` container:

```powershell
docker compose up --build web
```

## Stop The Stack

```powershell
docker compose down
```
