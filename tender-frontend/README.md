# Tender Registry — frontend

React interface for the tender fetching automation backend. Sign in, then
manage the sites the scraper visits and the categories tenders are classified
into.

## Setup

```bash
npm install
cp .env.example .env      # only needed if the backend is not on localhost:8000
npm run dev
```

Opens on http://localhost:5173

The backend must be running, and its `CORS_ORIGINS` must include
`http://localhost:5173`.

## Pages

| Route         | Access        | Purpose                                  |
|---------------|---------------|------------------------------------------|
| `/login`      | public        | Sign in, receive a JWT                   |
| `/register`   | public        | Create a standard user account           |
| `/sites`      | signed in     | List sites; admins can add, edit, pause, delete |
| `/categories` | signed in     | List categories and keywords; admins can edit |

Everyone signed in can read. Only admins see the write controls, and the
backend enforces that independently — hiding a button is convenience, not
security.

## How auth works

`POST /api/v1/authenticate` returns a JWT, which is stored in `localStorage`
and sent as `Authorization: Bearer <token>` on every request.

On page load `AuthContext` calls `GET /api/v1/me` with the stored token. That
restores the session across refreshes and confirms the token is still valid,
rather than trusting a token that may have expired.

Note that `localStorage` is readable by any script running on the page. It is a
reasonable choice for an internal tool, but `httpOnly` cookies would be safer
if this is ever exposed more widely.

## Layout

```
src/
  api/client.js        fetch wrapper: base URL, bearer token, error handling
  auth/                AuthContext (session state) + ProtectedRoute (gate)
  components/          Layout shell, Modal, PageHeader
  pages/               Login, Register, Sites, Categories
  styles.css           all styling
```

Sans-serif for interface chrome, monospace for machine-generated data (URLs,
usernames, dates, strategy names, keywords).
