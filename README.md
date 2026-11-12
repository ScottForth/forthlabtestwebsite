# Forth Lab — Publications page

A clean, self-updating publications page built from Scott Forth's Google Scholar
profile (`Efwi0VsAAAAJ`). Newest papers appear first; visitors can search or
switch to "Most cited".

```
index.html                              the page (reads publications.json)
publications.json                       the data
scripts/update_publications.py          refreshes publications.json from Scholar
.github/workflows/update-publications.yml  runs the script every Monday
```

## Why there's a data file and a script

Google Scholar has no public API and blocks web pages from reading it directly,
so a page can't fetch Scholar "live" in a visitor's browser. Instead, a small
job runs once a week, pulls your profile, and saves it to `publications.json`.
The page reads that file. New papers show up within a week of appearing on
Scholar, with no hand editing.

## Setup (about 10 minutes, GitHub Pages)

1. **Create a GitHub repository** (e.g. `forth-lab-publications`) and upload all
   of these files, keeping the folder structure (including the hidden `.github`
   folder).
2. **Get a free SerpApi key** at <https://serpapi.com> (free plan: 250 searches a
   month; this job uses about 4–5). Google Scholar usually blocks GitHub's servers
   from reading it directly, so this key is what makes the updates reliable.
3. In the repository: **Settings → Secrets and variables → Actions → New
   repository secret**. Name: `SERPAPI_KEY`, value: your key.
4. **Settings → Pages**: Source = "Deploy from a branch", branch = `main`, folder
   = `/ (root)`. Your page will be at `https://<username>.github.io/<repo>/`.
5. **Actions tab → "Update publications from Google Scholar" → Run workflow** to
   fill the list immediately. After that it runs every Monday.

## Using it inside the lab website

- **Same site:** drop `index.html` and `publications.json` into the site (rename
  `index.html` to `publications.html` if you like) and run the script on
  whatever schedule your host supports.
- **Different site:** keep this repo running and point the page at it by
  changing `dataUrl` near the bottom of `index.html` to
  `https://<username>.github.io/<repo>/publications.json`, or embed the page
  with an `<iframe>`.

## Customizing

In `index.html`:

- `CONFIG.highlight` — author-name spellings shown in bold.
- `CONFIG.hide` — Scholar entries to leave off the page, by `id` (copy it from
  `publications.json`). Two mis-parsed entries are hidden to start with; add
  duplicate abstracts, theses, etc. as you like. The updater never touches this
  list, so hidden items stay hidden.
- The `:root` CSS variables set colors (the accent is RPI red); the tagline under
  "Publications" is plain text in the header.

## Running the updater by hand

```bash
pip install requests beautifulsoup4
SERPAPI_KEY=your_key python scripts/update_publications.py
```

Without a key it tries Scholar directly, which works from many home and campus
networks but not reliably from servers. If every source fails, or a response
looks truncated (20%+ fewer papers than before), the existing file is kept so
the page never goes blank.

## Previewing locally

Browsers won't load `publications.json` from a file opened by double-click.
From this folder run `python3 -m http.server` and open <http://localhost:8000>.
