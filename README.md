# Tender Fetching Automation

Finds public tender notices relevant to an IT services firm.

Thirty-eight Bangladeshi bank and government notice boards are scraped on
demand, each notice is classified against fifteen service categories, and
staff pick the ones worth keeping into saved lists.

Built for E Generation as a replacement for an existing n8n workflow.

```
tender-fetching-automation/
├── tender-backend/     FastAPI, PostgreSQL, scraping and classification
└── tender-frontend/    React interface
```

## How it works

A search is the main thing people do. It runs in three steps:

1. **Sites** — pick which notice boards to search, or select all
2. **Categories** — pick which categories matter, optionally including
   notices the classifier could not place
3. **Fetch** — the chosen sites are scraped there and then, and the results
   appear with a checkbox each

Nothing is kept until you tick the tenders worth keeping and press **Save (N)
selected tenders**. That turns the search into a saved list, recorded with the
sites and categories it was run for.

```
pick sites → pick categories → scrape now → review results → save a selection
                                   │
                     Firecrawl → parse → classify → store
```

Scraping happens when a search runs, so results are current. A full run across
all 38 sites takes several minutes; a handful of sites takes under a minute.

**Review** is where scraped tenders wait. A scheduled run stores tenders
nobody asked for, so they land here rather than disappearing into the
database. Tick the ones worth keeping and save them, either as a new list or
into one that already exists.

**Saved tenders** is the registry of everything kept. It has filters for
category, source, deadline window and search text, and a switch to view
everything ever scraped rather than only the saved set.

## The pages

| Page | Who sees it | What it is for |
|---|---|---|
| New search | `search_tenders` | Pick sites, pick categories, scrape, keep what matters |
| Saved lists | `save_lists` | Lists kept from earlier searches |
| Review | signed in | Tenders a scrape brought in that nobody has kept yet |
| Saved tenders | signed in | The registry of everything kept, with filters |
| Sites | signed in, edit with `manage_sites` | The notice boards that get scraped |
| Categories | signed in, edit with `manage_categories` | Categories and their keywords |
| Scheduling | signed in, edit with `manage_schedules` | Groups of sites scraped automatically |
| Users | `manage_users` | Accounts and what each can do |
| Maintenance | `run_admin_tasks` | Reclassify, scrape now, clear data |
| Your account | signed in | Your permissions, and changing your password |

## Classification

There is no LLM in the pipeline. Titles are scored against keyword lists held
in the database, which means no API cost, no rate limits, and identical
results on every run.

Longer keyword matches weigh more, so "cyber security training" lands in Cyber
Security rather than Training & Consultancy. Short abbreviations such as `erp`
and `ai` must match whole words, otherwise "interpretation" and "maintenance"
would produce false hits. A match needs either two separate keywords or one of
at least eight characters, which stops a single generic word from
miscategorising a notice.

The lists cover English and Bengali, and include vendor names, abbreviations
and procurement phrasings like "procurement of laptop" that the category names
alone would miss. They are editable in the app, so tuning classification does
not require a redeploy, and re-running classification applies the new keywords
to everything already stored without scraping again.

## Dates

Sites are inconsistent about which date they publish, so every tender records
which kind it holds and the interface labels it:

- most notice boards give a **publish date**
- some tables carry a **submission deadline** in a second column, which is
  detected automatically as a date in the same row falling after the publish
  date
- many notices state the deadline inside the title
  ("Date of submission: on or before August 30, 2026"), which is read too

Where no deadline is published, none is shown. Deadlines within a fortnight
are highlighted, and passed ones are struck through.

## Permissions

There is no self-registration. The first admin is created by the seed script
when the system is first set up, and that account creates everyone else and
decides what each can do.

| Capability | Grants |
|---|---|
| `search_tenders` | Run searches across the tender sites |
| `save_lists` | Save search results as a list |
| `triage_tenders` | Mark tenders as not interested, and restore them |
| `manage_sites` | Add, edit and pause the sites that get scraped |
| `manage_categories` | Add and edit categories and their keywords |
| `manage_schedules` | Create and change scheduled scrapes |
| `manage_users` | Create user accounts and set what they can do |
| `run_admin_tasks` | Re-run classification and start scrapes manually |

Any combination is valid, so an account can be search-only, search-and-save,
or a site administrator that cannot see user management. Users can see their
own permissions under **Your account**, where they can also change their
password.

Permissions are read from the database on every request rather than from the
sign-in token, so granting or revoking one takes effect immediately.

The last account holding `manage_users` cannot remove that permission from
itself, disable itself, or be deleted. Without that guard it is possible to
lock everyone out with no way back short of editing the database by hand.
Create a second admin and the restriction lifts.

## Setup

Start the backend first.

### Backend

```bash
cd tender-backend
python -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env              # then fill in the values below
alembic upgrade head
python -m scripts.seed_admin           # creates the first admin
python -m scripts.seed_reference_data  # the 15 categories and 38 sites
uvicorn app.main:app --reload
```

Interactive API docs: <http://localhost:8000/docs>

`.env` needs at minimum:

| Variable | Notes |
|---|---|
| `DATABASE_URL` | Supabase session pooler URI, with `postgresql+asyncpg://` as the scheme |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `ADMIN_PASSWORD` | At least 8 characters; used once by the seed script |
| `FIRECRAWL_API_KEY` | Required for scraping |
| `CORS_ORIGINS` | Must include `http://localhost:5173` |
| `TIMEZONE` | Zone for scheduled times, default `Asia/Dhaka` |

Python 3.12 is recommended. On 3.13 and later, `asyncpg` and `pydantic-core`
have no prebuilt wheels yet and pip falls back to compiling from source.

`tzdata` is in the requirements because Windows ships no system timezone
database, which scheduling needs. It is harmless elsewhere.

### Frontend

```bash
cd tender-frontend
npm install
npm run dev
```

Opens on <http://localhost:5173>. Sign in with the admin account created by
the seed script, then create the other users under **Users**.

## Scheduling

Sites are scheduled in groups rather than one at a time, so one change covers
a dozen sites and the runner makes a single pass instead of a dozen.

Creating one is two steps: pick the sites from a paginated list, then set how
often and at what time. Frequencies are daily, weekly, every two weeks,
monthly, or every N days. Groups can be edited and deleted, and turned off
without losing their settings.

**A site belongs to at most one group.** Two groups covering the same site
would scrape it twice on overlapping days, and there would be no clear answer
to when it is next fetched. Sites already spoken for appear greyed out in the
picker, naming the group holding them, so the reason is visible rather than
surfacing as an error on save. The constraint is enforced in the database too.

Times are wall-clock times in the timezone set by `TIMEZONE` (default
`Asia/Dhaka`), not UTC, so a group set for 08:00 stays at 08:00 through the
year. A monthly group set for the 31st runs on the last day of shorter months
rather than skipping them.

The runner lives in the API process and checks every minute. Before scraping
it moves the group forward with a conditional update, so if more than one
process is running — under `--reload`, or with several workers — only one of
them fires a given group. Set `SCHEDULER_ENABLED=false` to turn it off.

Each group records when it last ran and what happened. A group whose sites are
all paused is marked skipped rather than reporting a run that did nothing, and
one where a site fails records the error while the other sites still scrape.

Creating and changing schedules needs the `manage_schedules` capability;
anyone signed in can see them.

## Maintenance

An account with `run_admin_tasks` gets a **Maintenance** page holding three
actions:

- **Re-run classification** applies the current keywords to every stored
  tender, which picks up notices that previously matched nothing.
- **Start scrape** fetches every active site in the background.
- **Clear collected data** removes the saved lists, and optionally every
  stored tender as well. Users, sites and categories are never touched, so the
  tool still works afterwards. It requires typing CLEAR to confirm.

Clearing lists only is the lighter option: the saved tenders page empties, but
the tenders stay in the database and remain visible under "Everything
scraped", so nothing has to be scraped again.

## Scraping from the command line

Searches scrape automatically, but a manual run is useful for testing a site
or filling the database ahead of a demo.

```bash
cd tender-backend
python -m scripts.run_ingestion                 # every active site
python -m scripts.run_ingestion --site DPE      # one site
python -m scripts.run_ingestion --pages 1       # first page only
```

It prints a per-site table showing pages fetched, notices found, how many were
stored, and any errors. Start with a single site when checking whether a
parser still matches a live page.

If a site's dates look wrong, inspect its table columns:

```bash
python -m scripts.inspect_columns --site BangladeshBank
```

That prints each column with its configured role, which shows at a glance
whether a date column is being missed.

## API

Everything is under `/api/v1`. All endpoints except sign-in require
`Authorization: Bearer <token>`.

| Method | Path | Needs | Purpose |
|---|---|---|---|
| POST | `/authenticate` | — | Sign in, receive a JWT |
| GET | `/me` | signed in | Current user and capabilities |
| POST | `/change-password` | signed in | Change your own password |
| GET | `/users/capabilities` | signed in | Every capability and what it grants |
| GET, POST | `/users` | `manage_users` | List and create accounts |
| PATCH, DELETE | `/users/{id}` | `manage_users` | Edit or remove an account |
| POST | `/searches` | `search_tenders` | Start a search; scrapes in the background |
| GET | `/searches/{id}` | `search_tenders` | Progress while it runs |
| GET | `/searches/{id}/tenders` | `search_tenders` | Results, or the saved list |
| GET | `/searches/{id}/tender-ids` | `search_tenders` | Every result id, for select all |
| POST | `/searches/{id}/save` | `save_lists` | Keep the selected tenders |
| GET | `/searches` | `search_tenders` | Saved lists |
| DELETE | `/searches/{id}` | `save_lists` | Delete a saved list |
| GET | `/tenders` | signed in | Browse, search, filter, sort |
| GET | `/tenders/summary` | signed in | Counts by triage state |
| GET | `/tenders/ids` | signed in | Every matching id, for select all |
| POST | `/searches/from-tenders` | `save_lists` | Keep reviewed tenders as a list |
| PATCH | `/tenders/{id}` | `triage_tenders` | Not interested, or restore |
| GET | `/sites`, `/categories` | signed in | Read, for the filter controls |
| POST, PATCH, DELETE | `/sites` | `manage_sites` | Manage the scrape list |
| POST, PATCH, DELETE | `/categories` | `manage_categories` | Manage categories and keywords |
| POST | `/admin/reclassify` | `run_admin_tasks` | Re-score every stored tender |
| POST | `/admin/ingest` | `run_admin_tasks` | Start a scrape in the background |
| GET | `/admin/clear` | `run_admin_tasks` | What clearing would remove |
| POST | `/admin/clear` | `run_admin_tasks` | Delete saved lists, optionally all tenders |
| GET | `/schedules` | signed in | All schedule groups |
| GET | `/schedules/site-availability` | signed in | Which sites are free to schedule |
| POST | `/schedules` | `manage_schedules` | Create a group |
| PATCH | `/schedules/{id}` | `manage_schedules` | Change a group |
| DELETE | `/schedules/{id}` | `manage_schedules` | Delete a group |

## Tests

```bash
cd tender-backend
pip install -r requirements-dev.txt
export PYTHONPATH=.                # Windows: $env:PYTHONPATH="."

python tests/classifier_test.py    # scoring, date parsing, Bengali
python tests/parsers_test.py       # all 13 site strategies
python tests/fetching_test.py      # Firecrawl client, pagination
python tests/ingestion_test.py     # fetch, parse, classify, store
python tests/search_test.py        # the search wizard and saving
python tests/schedules_test.py     # schedule groups and timing
python tests/review_test.py        # the review inbox
python tests/maintenance_test.py   # clearing collected data
python tests/smoke_test.py         # sign-in, capabilities, passwords
python tests/reference_test.py     # sites and categories
python tests/tenders_test.py       # browse, filter, deadlines, triage
```

Nothing here touches Supabase or the network: the database tests run against a
throwaway SQLite file, and Firecrawl is mocked, so the suite costs no credits.

The classifier and the parsers were ported from the existing n8n workflow and
verified by running the original JavaScript under Node against the same
inputs. Both matched exactly: 38 of 38 titles for the classifier, and all 13
strategies for the parsers. The expected values in those two test files are
therefore the production behaviour, not an interpretation of it.

## Design decisions

**Every notice is stored, including ones with no category.** Filtering happens
when reading. A notice the classifier rejected today may match once someone
adds a keyword, and re-running classification is instant where re-scraping 38
sites is not. Notices older than the cutoff year are the exception and are
dropped at ingestion, since a passed deadline cannot become relevant again.

**A saved list records which tenders it holds.** Tenders are globally unique by
title, so one found by an earlier search is not stored again; without an
explicit membership table a later search covering the same site would appear
to return nothing.

**A tender belongs to one saved list.** Results already kept elsewhere are
shown with an "Already saved" marker and cannot be selected, so the same
notice does not appear twice across lists.

**Deadline columns are detected, not configured.** A deadline is a date in the
same row falling after the publish date. Hand-configuring 22 sites would mean
rechecking each one whenever a layout changed.

**Site and category are stored on each tender twice**, as a foreign key and as
text. The key makes filtering reliable; the text is a snapshot, so a tender
still shows where it came from after a rename.

**Deleting a site with tenders is refused.** Cascading would destroy the
provenance of everything it found, so admins pause a site instead.

**The parsers use regular expressions rather than a DOM parser.** That is
normally the wrong choice, but these selectors were tuned by hand against 38
real sites, and swapping in a different parser would silently change what each
one matches.

## Known limitations

**Some sites publish tenders as reference numbers only.** IDLC lists notices
titled `E-Tender-2026-150` and nothing more. There is no text to classify, so
these are always stored without a category. Reading the linked PDF would fix
it, at the cost of an extra fetch and parse per notice.

**Not every notice has a deadline.** Where a site publishes only one date, no
deadline is shown, and the "submission within" filter excludes those notices
because they cannot be placed in a window.

**Parsers depend on site markup.** When a portal changes its HTML, its
strategy returns nothing. `last_scrape_error` on the Sites page, and a site
returning zero notices, are the signals to watch.

**Saved lists do not update.** Reopening one shows what was saved at the time,
not tenders found since. Running a new search picks those up.

**A tender found on two sites keeps one source.** Sites are scraped
concurrently, so which of the two is recorded depends on which finished first.
