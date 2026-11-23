# Where to look, by kind of thing

Pick sources by what the need would be if it already existed. Searching everything
everywhere mostly adds noise.

| The thing would be… | Start with | Then |
|---|---|---|
| a library or SDK | the registry for the language (`npm`, `crates`, `pypi`), `github` | the registry page's "dependents", the project's docs |
| a CLI or developer tool | `github`, `hn` | awesome-lists for the language or domain |
| an app or product | `hn`, web search for `<category> open source`, `<known product> alternative` | Product Hunt, AlternativeTo |
| an agent skill, MCP server or plugin | what is installed locally, then skill and MCP directories (see below) | `github` with `SKILL.md` or `mcp server` in the term |
| a hosted service | web search for `<category> SaaS`, `<known product> alternative`, pricing pages | `hn`, AlternativeTo |
| a pattern or a snippet, not a project | code search: grep.app, GitHub code search | the library's own docs (Context7 or the docs site) |
| a method or algorithm | web search, arXiv, Papers with Code | the reference implementation's repository |
| a dataset or model | Hugging Face, Kaggle | the paper that introduced it |

## Notes on each `scout.py` channel

- `github` — repository search over names, descriptions and topics. Unauthenticated search
  is limited to about 10 requests a minute; set `GITHUB_TOKEN` (or `GH_TOKEN`) to raise it.
- `hn` — "Show HN" posts only, so results are launches rather than discussions. Good for
  tools and products; many link straight to a repository.
- `npm`, `crates` — full-text registry search. Good for library names, poor for concepts:
  "idea validation" returns whatever mentions those two words.
- `pypi` — PyPI offers no search API. This channel only checks whether a package is *named*
  after the term. A miss means nothing; for Python libraries use `github` or web search.

## Agent skills, plugins and MCP servers

These have their own shelves, and the shelves change fast. Treat this list as places to
try, and check that each still exists before relying on it.

- what is already installed: grep the names *and descriptions* of local skills
- the `skills` CLI and its directory at skills.sh
- first-party collections such as github.com/anthropics/skills
- awesome-lists for agent skills and for MCP servers
- GitHub code search: `path:**/SKILL.md <keyword>`
- MCP registries and directories

Directory listings describe a skill in one line and are often out of date. Open the
SKILL.md itself before writing anything about what it does.

## Chinese-language sources

Work described only in Chinese rarely appears in English keyword results. When the user
works in Chinese, or the need is specific to the Chinese internet (WeChat, Feishu, Bilibili,
Xiaohongshu, domestic model APIs), also try:

- Gitee search, for projects that are not mirrored to GitHub
- web search restricted to the term in Chinese plus "开源" or "GitHub"
- Juejin (掘金), V2EX, SegmentFault, Zhihu and sspai (少数派) for announcements and roundups
  — these are where a project gets introduced, and the post usually links the repository

GitHub's own search handles Chinese terms; include them as `-t` terms alongside the English.

## Ways to snowball

From any one relevant project:

1. Its README's "Alternatives", "Comparison", "Related", "Inspired by", "相关项目" sections
   (`scout.py related` extracts these).
2. `<project> alternative`, `<project> vs`, `<project> 替代` in web search. Comparison posts
   list the whole field.
3. The awesome-list it appears in: search `awesome <topic>` and open the section it sits in.
4. Its GitHub topics: each topic page lists other repositories that chose the same label.
5. Its dependents and forks. An active fork is sometimes the maintained version.
6. The issue tracker: users often post "how does this compare with X?" there.

## Reading results

- The same project found through three different terms is a stronger signal than a high
  star count found through one.
- An archived or year-quiet repository with a named successor is a pointer, not a dead end.
  Follow it.
- A directory listing or a search snippet is a lead. Open the project itself before writing
  anything about what it does.
- To read one skill or one package inside a large monorepo, fetch that folder only (a sparse
  checkout, or the hosting site's file API). Cloning the whole repository is slow and often
  times out. Take the entire folder, though: a SKILL.md usually points at scripts and
  references beside it.
