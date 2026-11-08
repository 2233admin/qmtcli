# Where the code lives

Three copies of this project exist. Check which one you are editing before the first edit.

| Copy | Path | What it is |
|---|---|---|
| GitHub | `https://github.com/2233admin/qmtcli`, branch `main` | Published product. Canonical for anything shipped by `uv`/pip. |
| Local checkout | `F:/projects/qmtcli` | Ordinary git clone of the above. Can be behind `origin/main`. |
| LayerFS | project `qmtcli-20261024`, branch `main` | Working source for the QMT native bridge work. Not a git repository; it is a LayerFS project reached through the `layerfs` / `layerfs_script` tools. |

`F:/projects/qmtcli` and LayerFS `qmtcli-20261024` are separate stores. An edit in one is invisible in the other, and neither is automatically synced to the other.

## Check before you start

```bash
git -C F:/projects/qmtcli fetch origin
git -C F:/projects/qmtcli rev-list --left-right --count origin/main...HEAD
```

The left number is how many commits `origin/main` has that the checkout lacks. A non-zero left number means the published product has moved; read `git -C F:/projects/qmtcli log --oneline HEAD..origin/main` before editing, because published behaviour may already differ from what the checkout contains.

## What is only in LayerFS

`handoffs/`, `recovered/`, `recovery-input/`, `tools/`, and `docs/sdk/` exist only in LayerFS. `handoffs/`, `recovered/`, and `recovery-input/` are evidence from native-bridge investigation and are not product. `tools/` and `docs/sdk/` are the official 250807 SDK semantic map.

## What is not in either store

`README_OLD.md`, `README_BEFORE_POLISH.md`, and `.github-optimization.md` sit untracked in the local checkout. They are superseded drafts, not product.
