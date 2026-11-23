#!/usr/bin/env python3
"""scout.py - the mechanical half of dont-reinvent-the-wheel.

    scout.py search -t "term one" -t "term two" [--channels github,hn,npm,crates,pypi]
                    [--limit 8] [--state FILE] [--all] [--json]
    scout.py related OWNER/REPO [--readme-file PATH] [--state FILE] [--all] [--json]
    scout.py keep --state FILE KEY [KEY ...]
    scout.py status --state FILE
    scout.py check

`search` sends every term to every channel in parallel and merges the results
into one candidate list; a candidate that several terms or channels point at
floats to the top. `related` reads a seed repository's README and topics and
lists the projects it names under headings such as "Alternatives".

With --state, each search/related call is a round, and candidates seen in
earlier rounds are hidden unless --all is given. New results are not the same
as useful results, so the reader marks the ones worth a closer look with
`keep`; `status` then reports how many rounds have passed since the shortlist
last grew. Two such rounds in a row is the stop signal.

Results keep the order each source returned them in. Stars and downloads are
printed but never used for ranking: a popular package that merely shares a
word with the query is still the wrong package.

Standard library only. A channel that fails is reported under "errors" and
never counted as "nothing found".
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "dont-reinvent-the-wheel/0.1"
TIMEOUT = 15
CHANNELS = ("github", "npm", "crates", "hn", "pypi")

# github.com paths whose first segment is not a repository owner.
_RESERVED = {
    "about", "apps", "collections", "customer-stories", "enterprise", "explore",
    "features", "issues", "login", "marketplace", "notifications", "orgs",
    "pricing", "pulls", "search", "security", "settings", "site", "sponsors",
    "topics", "trending", "users",
}
_REPO_URL = re.compile(r"github\.com[/:]([A-Za-z0-9][A-Za-z0-9-]*)/([A-Za-z0-9._-]+)", re.I)
_RELATED_HEADING = re.compile(
    r"alternativ|related|similar|compar|see also|inspir|prior art|acknowledg|credit"
    r"|\bvs\b|other (projects|tools)|borrow|替代|类似|相关|对比|比较|同类|致谢|参考|灵感|借鉴",
    re.I,
)


def repo_key(url: str | None) -> str | None:
    """Normalise any GitHub URL to 'github.com/owner/repo', else None."""
    if not url:
        return None
    m = _REPO_URL.search(url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    if owner.lower() in _RESERVED:
        return None
    if repo.endswith(".git"):
        repo = repo[:-4]
    repo = repo.rstrip(".")
    if not repo:
        return None
    return f"github.com/{owner}/{repo}".lower()


def http_get(url: str, headers: dict | None = None, raw: bool = False):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        body = resp.read().decode("utf-8", "replace")
    return body if raw else json.loads(body)


def _gh_headers(accept: str = "application/vnd.github+json") -> dict:
    headers = {"Accept": accept}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _day(value) -> str | None:
    return str(value)[:10] if value else None


def _short(text, n: int = 160) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


# --- channels: each returns a list of candidate dicts -----------------------

def search_github(term: str, limit: int) -> list[dict]:
    q = urllib.parse.urlencode({"q": term, "per_page": limit})
    data = http_get(f"https://api.github.com/search/repositories?{q}", _gh_headers())
    out = []
    for r in data.get("items", []):
        out.append({
            "key": repo_key(r["html_url"]), "name": r["full_name"], "url": r["html_url"],
            "description": _short(r.get("description")), "stars": r.get("stargazers_count"),
            "updated": _day(r.get("pushed_at")),
            "license": (r.get("license") or {}).get("spdx_id"),
            "archived": bool(r.get("archived")),
        })
    return out


def search_npm(term: str, limit: int) -> list[dict]:
    q = urllib.parse.urlencode({"text": term, "size": limit})
    data = http_get(f"https://registry.npmjs.org/-/v1/search?{q}")
    out = []
    for o in data.get("objects", []):
        p = o.get("package", {})
        links = p.get("links") or {}
        out.append({
            "key": repo_key(links.get("repository")) or f"npm:{p.get('name')}",
            "name": p.get("name"), "url": links.get("npm") or links.get("repository"),
            "description": _short(p.get("description")),
            "downloads": (o.get("downloads") or {}).get("monthly"),
            "updated": _day(p.get("date")), "license": p.get("license"),
        })
    return out


def search_crates(term: str, limit: int) -> list[dict]:
    q = urllib.parse.urlencode({"q": term, "per_page": limit})
    data = http_get(f"https://crates.io/api/v1/crates?{q}")
    out = []
    for c in data.get("crates", []):
        out.append({
            "key": repo_key(c.get("repository")) or f"crates:{c.get('name')}",
            "name": c.get("name"), "url": f"https://crates.io/crates/{c.get('name')}",
            "description": _short(c.get("description")),
            "downloads": c.get("recent_downloads"), "updated": _day(c.get("updated_at")),
        })
    return out


def search_hn(term: str, limit: int) -> list[dict]:
    """Show HN posts only: those are launches of things, not discussions about them."""
    q = urllib.parse.urlencode({"query": term, "tags": "show_hn", "hitsPerPage": limit})
    data = http_get(f"https://hn.algolia.com/api/v1/search?{q}")
    out = []
    for h in data.get("hits", []):
        item = f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append({
            "key": repo_key(h.get("url")) or f"hn:{h.get('objectID')}",
            "name": _short(h.get("title"), 90), "url": h.get("url") or item,
            "description": f"HN, {h.get('points') or 0} points, {item}",
            "updated": _day(h.get("created_at")),
        })
    return out


def search_pypi(term: str, limit: int) -> list[dict]:
    """PyPI has no search API, so this only probes whether a package is named
    after the term. A miss says nothing about whether PyPI has such a tool."""
    words = re.findall(r"[a-z0-9]+", term.lower())
    if not words or len(words) > 4:
        return []
    out = []
    for slug in dict.fromkeys(["-".join(words), "".join(words)]):
        try:
            data = http_get(f"https://pypi.org/pypi/{slug}/json")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        info = data.get("info", {})
        urls = " ".join(str(v) for v in (info.get("project_urls") or {}).values())
        uploads = [f.get("upload_time") for f in data.get("urls") or [] if f.get("upload_time")]
        out.append({
            "key": repo_key(urls) or f"pypi:{info.get('name')}",
            "name": info.get("name"), "url": f"https://pypi.org/project/{info.get('name')}/",
            "description": _short(info.get("summary")),
            "updated": _day(max(uploads)) if uploads else None,
            "license": _short(info.get("license"), 24) or None,
        })
    return out


SEARCHERS = {"github": search_github, "npm": search_npm, "crates": search_crates,
             "hn": search_hn, "pypi": search_pypi}


def _describe_error(exc: Exception) -> str:
    if isinstance(exc, urllib.error.HTTPError):
        hint = ""
        if exc.code in (403, 429):
            hint = " (rate limited; for GitHub set GITHUB_TOKEN)"
        return f"HTTP {exc.code}{hint}"
    return f"{type(exc).__name__}: {exc}"


def run_search(terms: list[str], channels: list[str], limit: int):
    merged: dict[str, dict] = {}
    errors: list[str] = []
    jobs = [(c, t) for c in channels for t in terms]
    with cf.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(SEARCHERS[c], t, limit): (c, t) for c, t in jobs}
        for fut in cf.as_completed(futures):
            channel, term = futures[fut]
            try:
                found = fut.result()
            except Exception as exc:  # one channel failing must not sink the round
                errors.append(f"{channel} [{term}]: {_describe_error(exc)}")
                continue
            for position, cand in enumerate(found):
                if not cand.get("key"):
                    continue
                entry = merged.setdefault(cand["key"], {"channels": [], "terms": [], "best": position})
                entry["best"] = min(entry["best"], position)
                for field, value in cand.items():
                    if value not in (None, "") and entry.get(field) in (None, ""):
                        entry[field] = value
                if channel not in entry["channels"]:
                    entry["channels"].append(channel)
                if term not in entry["terms"]:
                    entry["terms"].append(term)
    ranked = sorted(
        merged.values(),
        key=lambda c: (-len(c["terms"]), -len(c["channels"]), c["best"], c["key"]),
    )
    for c in ranked:
        c.pop("best", None)
    return ranked, sorted(errors)


def run_check() -> list[tuple[str, str]]:
    """One tiny query per channel, to see which sources are reachable from here."""
    probes = {"github": "test", "hn": "test", "npm": "test", "crates": "test", "pypi": "requests"}
    results = []
    with cf.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(SEARCHERS[ch], probes[ch], 1): ch for ch in CHANNELS}
        for fut in cf.as_completed(futures):
            ch = futures[fut]
            try:
                fut.result()
                results.append((ch, "ok"))
            except Exception as exc:
                results.append((ch, _describe_error(exc)))
    return sorted(results, key=lambda r: CHANNELS.index(r[0]))


# --- snowballing from a seed -------------------------------------------------

def parse_readme(text: str, self_key: str | None = None) -> list[dict]:
    """Return repositories a README links to, with the heading they sit under.
    Links under an alternatives/related style heading are flagged and listed first."""
    found: dict[str, dict] = {}
    heading, in_code = "", False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = re.match(r"\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", line)
        if m:
            heading = re.sub(r"[*_`]", "", m.group(1))
            continue
        if "shields.io" in line or "badge" in line.lower():
            continue
        for hit in _REPO_URL.finditer(line):
            key = repo_key(hit.group(0))
            if not key or key == self_key or key in found:
                continue
            found[key] = {
                "key": key, "name": key.split("/", 1)[1], "url": f"https://{key}",
                "section": heading or "(top)",
                "flagged": bool(_RELATED_HEADING.search(heading)),
                "description": _short(re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line).strip(" -*|>")),
            }
    return sorted(found.values(), key=lambda c: (not c["flagged"], c["section"]))


def run_related(repo: str, readme_file: str | None):
    key = repo_key(f"github.com/{repo}")
    if not key:
        raise SystemExit(f"not an OWNER/REPO: {repo}")
    slug = key.split("/", 1)[1]
    errors, topics, text = [], [], ""
    if readme_file:
        with open(readme_file, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    else:
        try:
            text = http_get(f"https://api.github.com/repos/{slug}/readme",
                            _gh_headers("application/vnd.github.raw"), raw=True)
        except Exception as exc:
            try:
                text = http_get(f"https://raw.githubusercontent.com/{slug}/HEAD/README.md", raw=True)
            except Exception:
                errors.append(f"readme: {_describe_error(exc)}")
    try:
        topics = http_get(f"https://api.github.com/repos/{slug}", _gh_headers()).get("topics", [])
    except Exception as exc:
        errors.append(f"topics: {_describe_error(exc)}")
    name = slug.split("/")[-1]
    follow_ups = [f"{name} alternative", f"{name} vs"]
    follow_ups += [f"topic:{t}" for t in topics[:5]] + [f"awesome {t}" for t in topics[:2]]
    return parse_readme(text, key), errors, topics, follow_ups


# --- rounds ------------------------------------------------------------------

def apply_state(path: str | None, cands: list[dict], label: str):
    """Mark each candidate new/seen against the state file and record the round."""
    if not path:
        for c in cands:
            c["new"] = True
        return None
    state = load_state(path)
    number = len(state["rounds"]) + 1
    fresh = 0
    for c in cands:
        c["new"] = c["key"] not in state["seen"]
        if c["new"]:
            state["seen"][c["key"]] = number
            fresh += 1
    info = {"round": number, "what": label, "new": fresh, "seen_total": len(state["seen"]),
            "at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")}
    state["rounds"].append(info)
    save_state(path, state)
    return info


def load_state(path: str) -> dict:
    state = {"seen": {}, "rounds": [], "kept": {}}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            state.update(json.load(fh))
    return state


def save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=1)


def keep(path: str, keys: list[str]) -> str:
    """Add candidates to the shortlist, stamped with the current round."""
    state = load_state(path)
    current = len(state["rounds"])
    added = []
    for raw in keys:
        key = repo_key(raw) or (repo_key(f"github.com/{raw}") if raw.count("/") == 1 and ":" not in raw else None) or raw
        if key not in state["kept"]:
            state["kept"][key] = state["seen"].get(key, current)
            added.append(key)
    save_state(path, state)
    return f"kept {len(added)} ({', '.join(added) or 'nothing new'}); shortlist is now {len(state['kept'])}"


def status(path: str) -> dict:
    state = load_state(path)
    rounds = len(state["rounds"])
    last_growth = max(state["kept"].values(), default=0)
    quiet = rounds - last_growth
    return {
        "rounds": rounds, "seen": len(state["seen"]), "shortlist": sorted(state["kept"]),
        "rounds_since_shortlist_grew": quiet,
        "saturated": bool(state["kept"]) and quiet >= 2,
        "history": state["rounds"],
    }


def render(cands, errors, info, show_all, extra=None) -> str:
    lines = []
    if info:
        lines.append(f"round {info['round']}: {info['new']} new, {info['seen_total']} seen so far ({info['what']})")
    for e in errors:
        lines.append(f"ERROR {e}  <- this channel was NOT searched")
    shown = [c for c in cands if show_all or c.get("new")]
    hidden = len(cands) - len(shown)
    for i, c in enumerate(shown, 1):
        bits = [c.get("name") or c["key"]]
        if c.get("stars") is not None:
            bits.append(f"★{c['stars']}")
        if c.get("downloads") is not None:
            bits.append(f"↓{c['downloads']}")
        if c.get("updated"):
            bits.append(c["updated"])
        if c.get("license"):
            bits.append(str(c["license"]))
        if c.get("archived"):
            bits.append("ARCHIVED")
        if c.get("channels"):
            bits.append(f"[{','.join(c['channels'])}] terms:{len(c['terms'])}")
        if c.get("section"):
            bits.append(("* " if c.get("flagged") else "") + f"under: {c['section']}")
        if not c.get("new", True):
            bits.append("(seen)")
        lines.append(f"{i:>2}. " + "  ".join(bits))
        if c.get("description"):
            lines.append(f"    {c['description']}")
        lines.append(f"    {c['url']}")
    if not shown:
        lines.append("nothing new this round")
    if hidden:
        lines.append(f"({hidden} already-seen candidates hidden; --all shows them)")
    for label, values in (extra or {}).items():
        if values:
            lines.append(f"{label}: " + ", ".join(values))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--state", help="JSON file that remembers what earlier rounds found")
    common.add_argument("--all", action="store_true", help="also show already-seen candidates")
    common.add_argument("--json", action="store_true", help="machine-readable output")
    s = sub.add_parser("search", parents=[common])
    s.add_argument("-t", "--term", action="append", required=True)
    s.add_argument("--channels", default="github,hn",
                   help="comma list from: github, hn, npm, crates, pypi (default: github,hn)")
    s.add_argument("--limit", type=int, default=8, help="results per term per channel")
    r = sub.add_parser("related", parents=[common])
    r.add_argument("repo", help="OWNER/REPO or a GitHub URL")
    r.add_argument("--readme-file", help="read this local README instead of fetching")
    k = sub.add_parser("keep", help="mark candidates as worth a closer look")
    k.add_argument("--state", required=True)
    k.add_argument("keys", nargs="+", help="OWNER/REPO, a GitHub URL, or a key such as npm:name")
    st = sub.add_parser("status", help="rounds so far, shortlist, and whether the search has gone quiet")
    st.add_argument("--state", required=True)
    sub.add_parser("check", help="see which sources are reachable from here")
    args = ap.parse_args(argv)

    if args.cmd == "check":
        results = run_check()
        for ch, state in results:
            print(f"{ch:<7} {state}")
        usable = [ch for ch, state in results if state == "ok"]
        print("use: --channels " + ",".join(usable) if usable else "no source reachable; search by hand")
        return 0
    if args.cmd == "keep":
        print(keep(args.state, args.keys))
        return 0
    if args.cmd == "status":
        info = status(args.state)
        for h in info.pop("history"):
            print(f"round {h['round']}: {h['new']} new  ({h['what']})")
        print(f"shortlist ({len(info['shortlist'])}): " + (", ".join(info["shortlist"]) or "empty"))
        print(f"rounds since the shortlist last grew: {info['rounds_since_shortlist_grew']}")
        print("saturated: " + ("yes - stop searching" if info["saturated"] else "no"))
        return 0

    extra = {}
    if args.cmd == "search":
        channels = [c.strip() for c in args.channels.split(",") if c.strip()]
        unknown = [c for c in channels if c not in SEARCHERS]
        if unknown:
            ap.error(f"unknown channel(s): {', '.join(unknown)}; choose from {', '.join(CHANNELS)}")
        cands, errors = run_search(args.term, channels, args.limit)
        label = "search: " + " | ".join(args.term)
    else:
        cands, errors, topics, follow_ups = run_related(args.repo, args.readme_file)
        extra = {"topics": topics, "try next": follow_ups}
        label = f"related: {args.repo}"
    info = apply_state(args.state, cands, label)
    if args.json:
        json.dump({"round": info, "errors": errors, "candidates": cands, **extra},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
    else:
        print(render(cands, errors, info, args.all, extra))
    return 0


if __name__ == "__main__":
    sys.exit(main())
