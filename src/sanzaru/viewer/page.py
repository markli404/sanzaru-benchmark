"""Render every run under an output tree as a browsable page.

    python3 -m sanzaru page output

Walks output/<model>/<task>/run-<n>/ and embeds what it finds, so the picker's options
come from the directory rather than from anything written by hand. Three boxes across,
one per monkey: what it received on the left, what it sent on the right, and a blank
wherever its senses could not take something in.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ..output import read_runs


def parse_manual(text: str) -> list[dict]:
    """Turn the manual's pipe tables into blocks a page can lay out properly."""
    blocks: list[dict] = []
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(set(cell) <= {"-", ":"} for cell in cells):
                continue  # the ---|--- rule carries no content
            rows.append(cells)
            continue
        if rows:
            blocks.append({"kind": "table", "rows": rows})
            rows = []
        if line:
            blocks.append({"kind": "note", "text": line})
    if rows:
        blocks.append({"kind": "table", "rows": rows})
    return blocks


def bundle(root: Path) -> list[dict]:
    runs = []
    for run in read_runs(root):
        board = run["puzzle"]["initial_state"]
        runs.append({
            "run": run["number"],
            "saved": run.get("saved_at", 0),
            "model": run["model"],
            "task": run["task"],
            "problem": run.get("problem") or f"seed {run.get('seed')}",
            "hints": run.get("hints") or "none",
            "mode": run.get("mode") or run.get("crew") or "norm",
            "crewRoles": run.get("mode_roles") or run.get("crew_roles") or ["deaf", "mute", "blind"],
            "success": run["success"],
            "reason": run["reason"],
            "stats": {
                "seed": run.get("seed"),
                "order seed": run.get("order_seed"),
                "rounds": run.get("rounds"),
                "silences": run.get("silences"),
                "repairs": run.get("repairs"),
            },
            "order": run.get("order") or [],
            "board": {
                "display": board.get("display"),
                "light": board.get("light"),
                "wires": board.get("wires", []),
                "plate": board.get("plate", []),
            },
            "manual": parse_manual(run["puzzle"]["manual"]),
            "systems": {role: chat.get("system", "") for role, chat in run.get("chats", {}).items()},
            "turns": [
                {
                    "round": turn["round"],
                    "role": turn["role"],
                    "label": turn["private_label"],
                    "view": turn["private"],
                    "note": turn.get("note", ""),
                    "inbox": turn["inbox"],
                    "calls": turn["calls"],
                }
                for turn in run["turns"]
            ],
        })
    return runs


PAGE = r"""<meta charset="utf-8">
<title>Sanzaru</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root {
  --ground: #E6E7E1; --panel: #FBFBF8; --sunk: #DCDED6; --line: #C6C9BE;
  --ink: #1B1E19; --dim: #63685E; --faint: #8E9389; --brass: #A9772A;
  --deaf: #A9772A; --mute: #4A5C93; --blind: #9A5738;
  --fatal: #A8332B; --safe: #3F7A4E;
  --red: #B33A33; --blue: #3B5EA8; --green: #3F7A4E; --yellow: #A08423; --white: #7A7F76; --purple: #6C4E9C; --orange: #B06A2C;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #121417; --panel: #1A1D21; --sunk: #0D0F12; --line: #2C3138;
    --ink: #E7E9E4; --dim: #9AA096; --faint: #6C7269; --brass: #D8A64A;
    --deaf: #D8A64A; --mute: #8CA0DC; --blind: #D08A62;
    --fatal: #E0655A; --safe: #6FBE83;
    --red: #E0655A; --blue: #7B9BE0; --green: #6FBE83; --yellow: #D6BA4E; --white: #C9CDC4; --purple: #A98BD8; --orange: #D89A5A;
  }
}
:root[data-theme="dark"] {
  --ground: #121417; --panel: #1A1D21; --sunk: #0D0F12; --line: #2C3138;
  --ink: #E7E9E4; --dim: #9AA096; --faint: #6C7269; --brass: #D8A64A;
  --deaf: #D8A64A; --mute: #8CA0DC; --blind: #D08A62;
  --fatal: #E0655A; --safe: #6FBE83;
  --red: #E0655A; --blue: #7B9BE0; --green: #6FBE83; --yellow: #D6BA4E; --white: #C9CDC4; --purple: #A98BD8; --orange: #D89A5A;
}

* { box-sizing: border-box; }
body {
  margin: 0; background: var(--ground); color: var(--ink);
  font: 400 15px/1.5 "IBM Plex Sans", system-ui, sans-serif;
}
.sheet { max-width: 1500px; margin: 0 auto; padding: 30px 20px 72px; }

.masthead { display: flex; align-items: center; gap: 14px; margin: 0 0 20px; }
.masthead .mark { width: 52px; height: 52px; flex: none; }
h1 {
  margin: 0; font: 800 30px/1.0 "IBM Plex Sans Condensed", system-ui, sans-serif;
  letter-spacing: 0.14em;
}
.slogan {
  margin: 5px 0 0; font: 500 11px/1 "IBM Plex Mono", monospace;
  letter-spacing: 0.14em; text-transform: uppercase; color: var(--faint);
}

.controls { display: flex; flex-wrap: wrap; gap: 14px 22px; align-items: flex-end; }
.field { display: grid; gap: 5px; }
.field span {
  font: 600 10px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .12em; color: var(--faint);
}
select {
  appearance: none; min-width: 165px; padding: 7px 30px 7px 11px;
  background: var(--panel); color: var(--ink);
  border: 1px solid var(--line); border-radius: 3px;
  font: 500 14px/1.2 "IBM Plex Mono", monospace; cursor: pointer;
}
.field { position: relative; }
.field::after {
  content: ""; position: absolute; right: 12px; bottom: 14px; pointer-events: none;
  border: 5px solid transparent; border-top-color: var(--faint);
}
select:focus-visible { outline: 2px solid var(--brass); outline-offset: 1px; }
.verdict-pill {
  display: inline-flex; padding: 6px 12px; border: 1px solid currentColor; border-radius: 2px;
  font: 600 12px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .1em;
}
.stats {
  display: flex; gap: 16px; padding-bottom: 7px;
  font: 500 12px/1 "IBM Plex Mono", monospace; color: var(--faint);
  font-variant-numeric: tabular-nums;
}
.stats b { color: var(--dim); font-weight: 600; }
.detonated { color: var(--fatal); }
.defused { color: var(--safe); }

.truth {
  display: grid; grid-template-columns: auto 1fr; gap: 18px 52px; align-items: start;
  margin: 20px 0 24px; padding: 16px 18px;
  background: var(--panel); border: 1px solid var(--line); border-radius: 3px;
}
.truth h2 {
  margin: 0 0 10px; font: 600 10px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .12em; color: var(--faint);
}
.readout { display: grid; gap: 12px; }
.gauges { display: flex; gap: 26px; }
.gauge { display: grid; gap: 3px; }
.gauge b { font: 600 21px/1 "IBM Plex Mono", monospace; font-variant-numeric: tabular-nums; }
.gauge b.marks { letter-spacing: .12em; }
.gauge small {
  font: 600 9.5px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .12em; color: var(--faint);
}
.lamp::before {
  content: ""; display: inline-block; width: 10px; height: 10px; margin-right: 8px;
  border-radius: 50%; background: currentColor; box-shadow: 0 0 9px currentColor;
}
.wires { display: flex; gap: 7px; }
.wire {
  display: grid; gap: 2px; justify-items: center; min-width: 50px;
  padding: 5px 8px; border: 1px solid currentColor; border-radius: 2px;
}
.wire b { font: 600 13px/1 "IBM Plex Mono", monospace; }
.wire small { font-size: 10px; letter-spacing: .03em; }
.red { color: var(--red); } .blue { color: var(--blue); } .white { color: var(--white); } .purple { color: var(--purple); } .orange { color: var(--orange); }
.green { color: var(--green); } .yellow { color: var(--yellow); }

.manual { display: grid; gap: 12px; justify-items: start; }
.manual table { border-collapse: collapse; }
.manual th, .manual td { padding: 5px 18px 5px 0; text-align: left; border-bottom: 1px solid var(--line); }
.manual thead th {
  font: 600 9.5px/1.2 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .1em; color: var(--faint);
  border-bottom: 1px solid var(--dim);
}
.manual td { font: 500 13px/1.4 "IBM Plex Mono", monospace; }
.manual tbody th, .manual td:first-child { color: var(--dim); }
.manual .note { margin: 0; font-size: 12.5px; color: var(--dim); font-style: italic; }

.lanes { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; align-items: start; }
.lane { background: var(--panel); border: 1px solid var(--line); border-radius: 3px; overflow: hidden; min-width: 0; }
.lane.deaf { --hue: var(--deaf); }
.lane.mute { --hue: var(--mute); }
.lane.blind { --hue: var(--blind); }
.head {
  position: sticky; top: 0; z-index: 2;
  display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 1px 11px;
  align-items: center; padding: 10px 14px;
  background: var(--sunk); border-bottom: 2px solid var(--hue);
}
.head .avatar {
  grid-row: 1 / 4; width: 40px; height: 40px; display: grid; place-items: center;
  font-size: 24px; line-height: 1; border-radius: 50%;
  background: var(--panel); border: 1.5px solid var(--hue);
}
.head .name {
  font: 700 16px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .09em; color: var(--hue);
}
.head .holds { font-size: 12.5px; }
.head .sense { font-size: 12px; color: var(--faint); font-style: italic; }

.thread { padding: 6px 0 12px; }
.turn { display: grid; gap: 7px; padding: 11px 14px; border-top: 1px solid var(--line); }
.turn:first-child { border-top: 0; }
.round {
  font: 600 10px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .14em; color: var(--faint);
  font-variant-numeric: tabular-nums;
}
.stream { display: flex; flex-direction: column; gap: 11px; min-width: 0; }

.view summary {
  cursor: pointer; color: var(--faint); list-style: none;
  font: 600 9.5px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .12em; padding: 2px 0;
}
.view summary::-webkit-details-marker { display: none; }
.view summary::before { content: "\25B8\00a0"; }
.view[open] summary::before { content: "\25BE\00a0"; }
.view summary:hover { color: var(--ink); }
.view pre {
  margin: 5px 0 0; padding: 8px 10px; overflow-x: auto;
  background: var(--sunk); border: 1px solid var(--line); border-radius: 3px;
  font: 400 11.5px/1.55 "IBM Plex Mono", monospace; color: var(--dim);
}

.msg { display: flex; align-items: flex-end; gap: 8px; }
.msg.out { flex-direction: row-reverse; }
.msg .pic {
  flex: 0 0 auto; width: 28px; height: 28px; display: grid; place-items: center;
  font-size: 16px; line-height: 1; border-radius: 50%;
  background: var(--sunk); border: 1px solid var(--line);
}
.msg .body { display: grid; gap: 3px; max-width: calc(100% - 40px); min-width: 0; }
.msg.out .body { justify-items: end; }
.msg .who {
  font: 600 9.5px/1 "IBM Plex Sans Condensed", sans-serif;
  text-transform: uppercase; letter-spacing: .1em; color: var(--faint); padding: 0 3px;
}
.bubble {
  padding: 8px 12px; border-radius: 14px; word-break: break-word;
  font: 400 13.5px/1.5 "IBM Plex Sans", sans-serif;
  border: 1px solid var(--line); background: var(--sunk);
}
.msg.in .bubble { border-bottom-left-radius: 4px; }
.msg.out .bubble {
  border-bottom-right-radius: 4px; text-align: right;
  background: color-mix(in srgb, var(--hue) 14%, var(--panel));
  border-color: color-mix(in srgb, var(--hue) 40%, var(--line));
}
.bubble.gesture { font-size: 20px; line-height: 1.3; letter-spacing: .06em; }
.bubble .note {
  display: block; margin-top: 4px; font: 500 11.5px/1.3 "IBM Plex Mono", monospace;
  font-style: normal; color: var(--dim);
}
.msg.in.deaf .pic { border-color: var(--deaf); }
.msg.in.mute .pic { border-color: var(--mute); }
.msg.in.blind .pic { border-color: var(--blind); }
.msg.out .pic { border-color: var(--hue); }

/* What a monkey wrote outside its calls. It reached nobody, so it is folded away by
   default: open it to see why a message was sent, from any of the three lanes. */
/* The system prompt: the first thing the monkey ever read, folded into a bubble. */
.sysprompt { margin: 0 0 6px; }
.sysprompt > summary {
  display: inline-block; cursor: pointer; list-style: none;
  padding: 8px 12px; border-radius: 14px; border-bottom-left-radius: 4px;
  border: 1px dashed var(--line); background: var(--sunk);
  font: 500 11px/1 "IBM Plex Mono", monospace; letter-spacing: .08em;
  text-transform: uppercase; color: var(--dim);
}
.sysprompt > summary::-webkit-details-marker { display: none; }
.sysprompt > summary:hover { border-color: var(--dim); color: var(--ink); }
.sysprompt[open] > summary { border-style: solid; }
.sysprompt > pre {
  margin-top: 6px; padding: 10px 12px; white-space: pre-wrap; overflow-x: auto;
  border: 1px solid var(--line); border-radius: 10px; background: var(--panel);
  font: 400 11.5px/1.55 "IBM Plex Mono", monospace; color: var(--dim);
}

.thought { margin: -2px 0 4px; }
.msg.out + .thought, .thought.own { text-align: right; }
.thought > summary {
  display: inline-block; cursor: pointer; list-style: none;
  font: 500 10.5px/1 "IBM Plex Mono", monospace; letter-spacing: .08em;
  text-transform: uppercase; color: var(--faint);
  border: 1px dashed var(--line); border-radius: 999px; padding: 3px 8px;
}
.thought > summary::-webkit-details-marker { display: none; }
.thought > summary:hover { color: var(--ink); border-color: var(--dim); }
.thought[open] > summary { color: var(--ink); border-style: solid; }
.thought .said {
  margin-top: 5px; padding: 7px 10px; text-align: left; white-space: pre-wrap;
  border-left: 2px solid color-mix(in srgb, var(--hue) 45%, var(--line));
  background: color-mix(in srgb, var(--hue) 5%, transparent);
  font: 400 12px/1.55 "IBM Plex Sans", sans-serif; color: var(--dim);
}
.thought.deaf .said { border-left-color: var(--deaf); }
.thought.mute .said { border-left-color: var(--mute); }
.thought.blind .said { border-left-color: var(--blind); }

.bubble.quiet {
  background: transparent; border-style: dashed; color: var(--faint);
  font-style: italic; font-size: 12.5px;
}
.bubble.blocked {
  background: transparent; border-style: dashed;
  border-color: var(--line); color: var(--faint);
}
.bubble.acted, .bubble.fatal { font-family: "IBM Plex Mono", monospace; font-weight: 500; }
.bubble.acted { border-color: var(--safe); background: color-mix(in srgb, var(--safe) 12%, var(--panel)); }
.bubble.fatal { border-color: var(--fatal); background: color-mix(in srgb, var(--fatal) 12%, var(--panel)); }
.bubble.acted .note { color: var(--safe); }
.bubble.fatal .note { color: var(--fatal); }

.blank {
  display: inline-block; min-width: 1.05em; text-align: center; color: var(--faint);
  background: var(--sunk); border-bottom: 1px dotted currentColor; border-radius: 2px;
}
.legend {
  margin-top: 28px; padding-top: 14px; border-top: 1px solid var(--line);
  color: var(--faint); font-size: 12.5px; max-width: 68ch;
}
@media (max-width: 980px) {
  .lanes { grid-template-columns: 1fr; }
  .head { position: static; }
  .truth { grid-template-columns: 1fr; }
}
</style>

<div class="sheet">
  <header class="masthead">
    <svg viewBox="0 0 512 512" class="mark" aria-hidden="true">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#FFE07A"/>
      <stop offset="100%" stop-color="#F2AC3C"/>
    </linearGradient>
    <filter id="soft" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="7" stdDeviation="9" flood-color="#8A5A12" flood-opacity="0.35"/>
    </filter>
    <filter id="tiny" x="-30%" y="-30%" width="160%" height="160%">
      <feDropShadow dx="0" dy="4" stdDeviation="4" flood-color="#8A5A12" flood-opacity="0.3"/>
    </filter>
  </defs>
  <rect width="512" height="512" rx="115" fill="url(#bg)"/>
  <circle cx="256.0" cy="256.0" r="168" fill="none" stroke="#2A2D2C" stroke-width="13" opacity="0.92"/>
  <path d="M 401.5 340.0 L 426.5 324.4" stroke="#2A2D2C" stroke-width="13" stroke-linecap="round" opacity="0.92"/>
  <path d="M 401.5 340.0 L 400.5 309.4" stroke="#2A2D2C" stroke-width="13" stroke-linecap="round" opacity="0.92"/>
  <path d="M 110.5 340.0 L 111.5 369.4" stroke="#2A2D2C" stroke-width="13" stroke-linecap="round" opacity="0.92"/>
  <path d="M 110.5 340.0 L 137.5 354.4" stroke="#2A2D2C" stroke-width="13" stroke-linecap="round" opacity="0.92"/>
  <path d="M 256.0 88.0 L 230.0 74.1" stroke="#2A2D2C" stroke-width="13" stroke-linecap="round" opacity="0.92"/>
  <path d="M 256.0 88.0 L 230.0 104.1" stroke="#2A2D2C" stroke-width="13" stroke-linecap="round" opacity="0.92"/>
  <circle cx="256.0" cy="256.0" r="100" fill="#FFFDF4" filter="url(#soft)"/>
  <text x="256.0" y="262.0" font-size="128" text-anchor="middle" dominant-baseline="central">💣</text>
  <circle cx="401.5" cy="172.0" r="56" fill="#FFFDF4" filter="url(#tiny)"/>
  <text x="401.5" y="174.0" font-size="82" text-anchor="middle" dominant-baseline="central">🙉</text>
  <circle cx="256.0" cy="424.0" r="56" fill="#FFFDF4" filter="url(#tiny)"/>
  <text x="256.0" y="426.0" font-size="82" text-anchor="middle" dominant-baseline="central">🙊</text>
  <circle cx="110.5" cy="172.0" r="56" fill="#FFFDF4" filter="url(#tiny)"/>
  <text x="110.5" y="174.0" font-size="82" text-anchor="middle" dominant-baseline="central">🙈</text>
    </svg>
    <div>
      <h1>SANZARU</h1>
      <p class="slogan">cooperation under asymmetric perception</p>
    </div>
  </header>

  <div class="controls">
    <label class="field"><span>mode</span><select id="mode"></select></label>
    <label class="field"><span>model</span><select id="model"></select></label>
    <label class="field"><span>task</span><select id="task"></select></label>
    <label class="field"><span>problem</span><select id="problem"></select></label>
    <label class="field"><span>hints</span><select id="hints"></select></label>
    <label class="field"><span>run</span><select id="run"></select></label>
    <span class="verdict-pill" id="verdict"></span>
    <span class="stats" id="stats"></span>
  </div>

  <section class="truth">
    <div>
      <h2>the bomb</h2>
      <div class="readout" id="bomb"></div>
    </div>
    <div>
      <h2>the manual</h2>
      <div class="manual" id="manual"></div>
    </div>
  </section>

  <div class="lanes" id="lanes"></div>

  <p class="legend">
    Each box is one monkey's view. What it received sits on the left, what it sent on the
    right, and a greyed message is one that reached nobody. A <span class="blank">?</span>
    marks something its senses could not take in.
  </p>
</div>

<script>
const RUNS = __RUNS__;
const HOLDS = {deaf: "the bomb's face", mute: "the manual", blind: "the only hands",
               almighty: "everything"};
const FACE = {deaf: "\u{1F649}", mute: "\u{1F64A}", blind: "\u{1F648}", almighty: "\u{1F435}"};
const SENSE = {deaf: "hears nothing", mute: "cannot speak", blind: "sees nothing",
               almighty: "misses nothing"};
const HARD_SENSE = {blind: "sees nothing, cannot speak"};

const $ = (id) => document.getElementById(id);
const esc = (t) => String(t).replace(/[&<>"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const blanks = (t) => esc(t).split("?").join('<span class="blank" title="not perceived">?</span>');
const uniq = (list) => [...new Set(list)];
const label = (run) => `run ${run.run} — ${run.success ? "defused" : "detonated"}`;

function fill(select, values, keep) {
  select.innerHTML = values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("");
  select.value = values.includes(keep) ? keep : values[0];
}

// The page opens on whatever finished last: run it, refresh, and you are looking at it.
const LATEST = RUNS.reduce((a, b) => (b.saved > (a ? a.saved : -1) ? b : a), null);

// Where the pickers land on first load: the URL if it names a run, else the newest.
const Q = new URLSearchParams(location.search);
// The house default is the norm-mode gpt-5 run that finished last; a URL or the
// gallery of everything else is one dropdown away.
const HOME = RUNS.filter((r) => r.mode === "norm" && r.model === "gpt-5")
  .reduce((a, b) => (b.saved > (a ? a.saved : -1) ? b : a), null) || LATEST;
const PRESET = (Q.has("model") || Q.has("task"))
  ? {mode: Q.get("mode"), model: Q.get("model"), task: Q.get("task"),
     problem: Q.get("problem"), hints: Q.get("hints"), run: Q.get("run")}
  : (HOME ? {mode: HOME.mode, model: HOME.model, task: HOME.task,
             problem: String(HOME.problem), hints: HOME.hints, run: ""} : {});

function chosen() {
  const pick = (id) => $(id).value || PRESET[id] || "";
  fill($("mode"), uniq(RUNS.map((r) => r.mode)), pick("mode"));
  const byMode = RUNS.filter((r) => r.mode === $("mode").value);
  const models = uniq(byMode.map((r) => r.model));
  fill($("model"), models, pick("model") || models[0]);
  const byModel = byMode.filter((r) => r.model === $("model").value);
  fill($("task"), uniq(byModel.map((r) => r.task)), pick("task"));
  const byTask = byModel.filter((r) => r.task === $("task").value);
  fill($("problem"), uniq(byTask.map((r) => String(r.problem))), pick("problem"));
  const byProblem = byTask.filter((r) => String(r.problem) === $("problem").value);
  fill($("hints"), uniq(byProblem.map((r) => r.hints)), pick("hints"));
  const byHints = byProblem.filter((r) => r.hints === $("hints").value);
  fill($("run"), byHints.map(label), pick("run") || (byHints.includes(HOME) ? label(HOME) : ""));
  return byHints.find((r) => label(r) === $("run").value) || byHints[0];
}

function bomb(run) {
  const wires = (run.board.wires || []).map((w) =>
    `<div class="wire ${esc(w.color)}"><b>${w.position}</b><small>${esc(w.color)}</small></div>`).join("");
  const plate = (run.board.plate || []).length
    ? `<div class="gauge"><b class="marks">${esc(run.board.plate.join(" "))}</b><small>plate, felt only</small></div>`
    : "";
  return `<div class="gauges">
      <div class="gauge"><b>${esc(run.board.display)}</b><small>display</small></div>
      <div class="gauge ${esc(run.board.light)}"><b class="lamp">${esc(run.board.light)}</b><small>light</small></div>
      ${plate}
    </div>${wires ? `<div class="wires">${wires}</div>` : ""}`;
}

function manual(blocks) {
  return blocks.map((block) => {
    if (block.kind === "note") return `<p class="note">${esc(block.text)}</p>`;
    const [head, ...body] = block.rows;
    return `<table><thead><tr>${head.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>`
      + body.map((row) => `<tr>${row.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")
      + `</tbody></table>`;
  }).join("");
}

const VERB = {speech: "says", gesture: "gestures"};

function message(side, role, body, extra, to) {
  const pic = `<span class="pic">${FACE[role] || "\u2699"}</span>`;
  const name = `<span class="who">${esc(role)}${to ? " \u2192 " + esc(to) : ""}</span>`;
  const bubble = `<div class="bubble ${extra || ""}">${body}</div>`;
  return `<div class="msg ${side}">${pic}<div class="body">${name}${bubble}</div></div>`;
}

// A monkey's private prose, folded shut. `own` puts it under this lane's own turn.
function thought(role, note, own) {
  if (!note) return "";
  const who = own ? "my thinking" : `${role} thinking`;
  return `<details class="thought ${esc(role)}${own ? " own" : ""}">`
    + `<summary>${esc(who)}</summary><div class="said">${esc(note)}</div></details>`;
}

function bubbles(turn, notes) {
  const seen = new Set();
  const parts = turn.inbox.map((m) => {
    const said = m.perceived === false ? blanks(m.payload) : esc(m.payload);
    const row = message("in", m.sender, said, m.modality === "gesture" ? "gesture" : "")
      .replace('class="msg in"', `class="msg in ${esc(m.sender)}"`);
    // The sender's own reasoning, offered once however many messages it sent.
    const key = `${m.turn}/${m.sender}`;
    if (m.sender === turn.role || seen.has(key)) return row;
    seen.add(key);
    return row + thought(m.sender, (notes[key] || ""), false);
  });

  for (const call of turn.calls) {
    if (!call.accepted) {
      parts.push(message("out", turn.role,
        `${esc(call.said || call.payload || "")}<em class="note">${esc(call.reason || "")}</em>`,
        "blocked" + (call.kind === "gesture" ? " gesture" : "")));
    } else if (call.kind === "wait") {
      parts.push(message("out", turn.role, "waits", "quiet"));
    } else if (call.kind === "act") {
      const result = call.result || "";
      const tone = /expected|does not exist|already/.test(result) ? "fatal" : "acted";
      parts.push(message("out", turn.role,
        `${esc(call.said || call.payload)}<em class="note">${esc(result)}</em>`, tone));
    } else {
      parts.push(message("out", turn.role, esc(call.message ? call.message.payload : call.said),
        call.kind === "gesture" ? "gesture" : "", call.message && call.message.to));
    }
  }
  const sent = parts.join("") || message("out", turn.role, "waits", "quiet");
  return sent + thought(turn.role, turn.note, true);
}

function lanes(run) {
  // Every note in the run, so a lane can open the thinking behind a message it received.
  const notes = {};
  for (const turn of run.turns) notes[`${turn.round}/${turn.role}`] = turn.note || "";
  const senseOf = (role) => run.mode === "info" ? "full communication, private view"
    : (run.mode === "hard" && HARD_SENSE[role]) || SENSE[role];
  const nameOf = (role) => (run.mode === "hard" && role === "blind") ? "blind & mute" : role;
  $("lanes").style.gridTemplateColumns = `repeat(${run.crewRoles.length}, minmax(0, 1fr))`;
  return run.crewRoles.map((role) => {
    const system = run.systems && run.systems[role]
      ? `<div class="turn"><details class="sysprompt"><summary>system prompt</summary>`
        + `<pre>${esc(run.systems[role])}</pre></details></div>`
      : "";
    const turns = system + run.turns.filter((t) => t.role === role).map((turn) =>
      `<div class="turn"><span class="round">round ${turn.round}</span>`
      + `<details class="view"><summary>${esc(turn.label.toLowerCase())}</summary>`
      + `<pre>${esc(turn.view)}</pre></details>`
      + `<div class="stream">${bubbles(turn, notes)}</div></div>`).join("");
    return `<section class="lane ${role}"><div class="head">`
      + `<span class="avatar">${FACE[role]}</span>`
      + `<span class="name">${nameOf(role)}</span><span class="holds">holds ${HOLDS[role]}</span>`
      + `<span class="sense">${senseOf(role)}</span></div>`
      + `<div class="thread">${turns}</div></section>`;
  }).join("");
}

function draw() {
  const run = chosen();
  if (!run) return;
  $("verdict").className = "verdict-pill " + (run.success ? "defused" : "detonated");
  $("verdict").textContent = (run.success ? "defused" : "detonated") + " — " + run.reason;
  // A silent round and a deliberate wait read the same in a transcript. Only the
  // counts tell them apart, so they sit beside the verdict.
  $("stats").innerHTML = [
    ["seed", run.stats.seed],
    ["order seed", run.stats["order seed"]],
    ["rounds", run.stats.rounds],
    ["silent", run.stats.silences],
    ["rewrites", run.stats.repairs],
  ].filter(([, v]) => v !== null && v !== undefined)
   .map(([k, v]) => `<span>${k} <b>${v}</b></span>`).join("");
  $("bomb").innerHTML = bomb(run);
  $("manual").innerHTML = manual(run.manual);
  $("lanes").innerHTML = lanes(run);
}

for (const id of ["mode", "model", "task", "problem", "hints", "run"]) $(id).addEventListener("change", draw);
draw();
</script>
"""


def write_page(root: Path, target: Path) -> int:
    """Render every run under `root` into `target`; returns how many runs it holds."""
    runs = bundle(root)
    Path(target).write_text(
        PAGE.replace("__RUNS__", json.dumps(runs, ensure_ascii=False)), encoding="utf-8"
    )
    return len(runs)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    root = Path(args[0]) if args else Path("output")
    target = Path(args[1]) if len(args) > 1 else root / "rollout.html"
    count = write_page(root, target)
    print(f"{target}: {count} runs from {root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
