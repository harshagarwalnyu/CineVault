# Frontend

Next.js frontend for the Movies Recommender UI.

## Local Run

Install dependencies with Bun:

```bash
bun install
```

Start the app on the shared local dev port:

```bash
bun run dev -- --port 3002
```

## Environment

Expected local defaults:

- `NEXTAUTH_URL=http://localhost:3002`
- `NEXT_PUBLIC_API_URL=http://localhost:8001`
- `API_URL=http://localhost:8001`

## Checks

```bash
bun run lint
bun run typecheck
bun run build
```
