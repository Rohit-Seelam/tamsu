---
name: frontend-tsx
description: Rules specific to frontend TypeScript / React in `frontend/`.
paths: [frontend/**]
---

# Frontend TS/React rules

## Routing

- TanStack Router only. Do not introduce `react-router-dom`.
- Route files live at `frontend/routes/*.tsx`. One route per file.
- Loaders fetch data; components render.

## State

- TanStack Query for server state.
- React Context for UI-only ephemeral state (modal open, theme).
- No Redux. No Zustand. Picked early; no value in adding more.

## Components

- Function components only.
- Co-locate styles (Tailwind classes inline or `.module.css`).
- Each component has its own file unless ≤30 lines and only used in the same file.

## Data fetching

- All API calls through the typed `frontend/lib/api.ts` client (generated from OpenAPI).
- Never `fetch()` directly in components.

## Tests

- vitest, not jest.
- Render components with `@testing-library/react`.
- Mock the API client at the boundary (`frontend/lib/api.ts`); never mock individual hooks.

## TypeScript

- `strict: true`. No `any` without a `// @ts-expect-error` comment with reason.
- Types live next to code. Shared types in `frontend/types/`.
