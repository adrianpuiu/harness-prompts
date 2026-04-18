# meta-harness-cc

A bounded **coder ⇄ reviewer** coding harness with a pluggable gate,
written in Python on top of the Anthropic Messages API with tool use.

The loop is the same shape as the Claude-Code edition in `harness-cc/`
(slash command + three subagents), but repackaged so it can be run
standalone against any git repository, against any gate script, and
driven from CI or a terminal — no Claude Code installation required.

## How the loop works

Each round executes five stages:

1. **Snapshot** — record `HEAD` as the round's base.
2. **Coder agent** — reads the previous round's feedback + digest,
   edits the working tree with `read_file` / `write_file` / `edit_file`
   / `grep` / `glob`, and emits an `APPROACH / CHANGED / NOTES` block.
3. **Gate** — runs `.harness/gate.sh` (lint + types + tests by default).
   If it fails, stderr becomes the coder's next-round feedback and we
   skip straight to the digest.
4. **Reviewer agent** — if the gate passed, reads the round's diff +
   full changed files and emits a JSON findings object. Zero
   `blocker` / `major` findings = PASS.
5. **Digest agent** — compresses all rounds so far into ≤200 words so
   the coder has memory in the next round without reading the raw
   history.

The loop terminates on PASS, on `MAX_ROUNDS` exhausted (`MAX_CYCLES`),
or on a preflight abort (dirty tree, missing gate script, etc).

## Repository layout

```
meta-harness-cc/
├── README.md
├── pyproject.toml / requirements*.txt
├── .env.example
├── .harness/
│   └── gate.sh                         ← customise per project
├── harness/
│   ├── __init__.py / __main__.py
│   ├── cli.py                          ← argparse entry point
│   ├── orchestrator.py                 ← the outer loop
│   ├── agent.py                        ← Anthropic tool-use loop
│   ├── tools.py                        ← file tools (read/write/edit/grep/glob)
│   ├── gate.py                         ← gate runner
│   ├── state.py                        ← .harness/ state manager
│   ├── git_utils.py                    ← thin git wrappers
│   └── prompts/
│       ├── coder.md
│       ├── reviewer.md
│       └── digest.md
├── tests/                              ← pytest, no API calls
└── examples/fibonacci/                 ← walkthrough task
```

## Installation

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env     # fill in ANTHROPIC_API_KEY
set -a; . ./.env; set +a
```

## Usage

Inside any git repo that has a `.harness/gate.sh` (copy the default
from this package and adapt):

```bash
python -m harness "add input validation to parse_user() so empty strings raise ValueError"
```

Important flags:

| flag                            | default                          | what it does                     |
|---------------------------------|----------------------------------|----------------------------------|
| `--workdir PATH`                | `$PWD`                           | project root                     |
| `--max-rounds N`                | `4`                              | hard budget                      |
| `--gate-script PATH`            | `.harness/gate.sh`               | relative to workdir              |
| `--gate-timeout SECS`           | `180`                            | per-gate-run                     |
| `--coder-model ID`              | `claude-sonnet-4-6`              | model for the coder              |
| `--reviewer-model ID`           | `claude-sonnet-4-6`              | model for the reviewer           |
| `--digest-model ID`             | `claude-haiku-4-5-20251001`      | cheap model for the digest       |
| `--allow-dirty`                 | off                              | skip clean-tree preflight        |
| `--allow-unsatisfiable-gate`    | off                              | run even if gate fails on empty  |

The script exits `0` on PASS, `1` on MAX_CYCLES, `2` on preflight abort.

## Customising the gate

`.harness/gate.sh` is a pipe-separated command list. Each entry is
`name|argv`; stdout/stderr get tailed into the failure feedback. To
swap the default Python stack for Node + vitest:

```bash
COMMANDS=(
  "lint|npx eslint ."
  "types|npx tsc --noEmit"
  "tests|npx vitest run"
)
```

`PASS_ON_EXIT` whitelists non-zero exit codes per command (default:
`tests|0 5` so "pytest collected no tests" doesn't fail the gate on
non-test changes).

## Safety rules

- The working tree is mutated in place. Start clean.
- The orchestrator never edits project code itself — only the coder
  agent does, via its tools. The orchestrator only writes under
  `.harness/`.
- Gate commands run in the project root as subprocesses; if your tests
  are untrusted, run the whole thing in a container.
- Model API calls go through Anthropic. Your `ANTHROPIC_API_KEY` must
  be set.

## Tests

```bash
pytest -q
```

Tests cover the tool implementations, gate runner, git wrappers, state
manager, and orchestrator plumbing — no network calls.

## License

MIT
