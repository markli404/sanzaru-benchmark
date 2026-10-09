<p align="center"><img src="banner.svg" alt="SANZARU" width="820"/></p>

**Sanzaru** is a seedable cooperation benchmark for language-model agents. Three agents
share a room with an armed bomb. Their senses are split so that every piece of the
answer sits behind a channel its holder cannot fully use, and nothing in the prompt
tells them how to play. The prompts state only the physics of the world.

<p align="center"><img src="docs/sanzaru_overview.png" alt="Three agents with asymmetric communication: Mute means wire 3, Deaf misreads the gesture as yes, and Blind cuts the wrong wire." width="1100"/></p>

<p align="center"><em>Three monkeys, three communication limits, one unfortunate wire.</em></p>

| | Can | Cannot |
|---|---|---|
| 🙉 **Deaf** | see the bomb | hear, or touch the bomb |
| 🙊 **Mute** | read the manual, gesture | speak, or touch the bomb |
| 🙈 **Blind** | touch and act on the bomb | see a colour, a gesture, or anything printed |

Speech reaches whoever hears, and gestures reach whoever sees. Mute's only way out is
gesture, which Blind cannot see, so what the manual says never reaches the hands
directly. A wrong action detonates the bomb.

## 🤔 Why

Most multi-agent benchmarks split what the agents *know* and let them talk it through
in ordinary language. Where the communication is constrained, the constraint is on how
much may be said or on what may be disclosed, and the words still arrive intact. A team
that can already talk has been handed the hard half of cooperation before it starts.

Sanzaru splits perception and the channels as well as the knowledge. Whether a gesture
protocol gets designed rather than assumed, whether information is routed through the
one agent who can carry it, and whether the team acts on verified meaning instead of a
single hopeful reading all have to emerge inside a single episode.

## 💣 One bomb, three views

Every problem is a single bomb shown three ways. Take `base-1#2` as an example.
Deaf sees the board, Blind feels only its shapes, and Mute reads a manual that is
useless without the board.

```text
Deaf sees                    Blind feels                  Mute reads
DISPLAY [0]                  DISPLAY [?]                  | light  | cut wire color |
LIGHT [green]                LIGHT [?]                    | green  | red            |
WIRES 1:[yellow]             WIRES 1:[?]                  | red    | yellow         |
      2:[green]                    2:[?]                  | yellow | green          |
      3:[red]                      3:[?]
```

The answer exists in nobody's head. The light is green, so the red wire in position
3 must be cut. Deaf has to speak the board to Mute, Mute has to move the verdict back
with nothing but gestures, and Deaf has to talk Blind's hands onto the right wire.
Below is one team walking that loop in three rounds, as the result viewer shows it.

<p align="center"><img src="docs/sample-run.png" alt="a run, three lanes" width="900"/></p>

## 📊 Results

Seven models, three instances per variant with three repeats, 216 episodes each under
Weak hints. Teams defuse 49% of the bombs, and the field runs from 86% down to 20%.
Below, one axis per family and the model's overall rate at the centre of its panel.

<p align="center"><img src="docs/radar_weak.png" alt="capability profile by model" width="900"/></p>

No model is strong everywhere, and the shapes are not one shape scaled up and down.
Staleness and relay come easiest, memory and timing hardest, and a model can clear the
relay and still lose the bomb to a light that moved while the answer was in transit.

**The split is what costs.** One agent holding every view, the manual and the cutters
defuses **90%** of the bombs its own three-agent team defuses **41%** of. The puzzles
are not the hard part.

**Most losses are communication.** Every one of the 771 lost episodes was read against
a written codebook. About 60% end in a communication failure, and the largest single
mode is a team that never built a code at all.

<p align="center"><img src="docs/modes_donut.png" alt="failure modes by model" width="880"/></p>

**More instruction does not help.** Across four hint levels the same model falls from
40.7% to 20.8% as the guidance grows more explicit. Wrong cuts go down and timeouts go
up, so the teams get more careful and less finished.

**Teams do invent codes.** One symbol per wire is the common design. Others repeat a
symbol and let the count carry the number, which is the only design that reaches Blind,
who receives one blank per symbol and can count them. Below, a team spells the manual
out in Morse in the opening message of an episode, unprompted, and the receiver decodes
it.

<p align="center"><img src="docs/chat_morse.png" alt="a team spelling the manual in Morse" width="880"/></p>

## 🗂 The bank

The benchmark ships as files, not as code. Every variant owns a folder under `bank/`
holding its contract and its five bombs, each a self contained definition a runner
can replay without touching the generator, and `bank/manifest.json` aggregates the
contracts into one table. A test regenerates the whole bank and compares it byte
for byte, so the generator can never drift under the frozen problems unnoticed.
`variant#N` names the same bomb forever, on every machine.

The bank holds two subsets. **Core** is the diagnostic suite, where every variant
moves one variable, so a death names an axis. **Plus** makes no attribution claim.
It exists to separate the strongest teams, and that is all it claims. 24 active
variants, five seeded instances each, 120 instances in all.

## 🎚 Modes

The trio above is `--mode norm`. In `--mode hard` Blind also loses its voice, so only
gestures ever leave the hands. In `--mode easy` a single almighty monkey holds every
sense and the manual at once. Easy mode is the control, since it prices the task
itself apart from the cost of coordination.

`--mode info` removes communication asymmetry while retaining private information:
all three agents can speak, hear speech, send gestures and see gestures. Deaf keeps
the visual bomb view, Mute keeps the manual, and Blind keeps the tactile view and
exclusive action authority. Their names are identifiers, not disabilities in this
mode. It has dedicated role prompts and hints; task-specific turn orders, memory
windows and round budgets are unchanged. Sequential delivery still depends on turn
order, just as in `norm`.

## 💡 Hints

Bare runs are the benchmark, and the hint tiers exist to locate where a model fails.
The `weak` tier nudges the frame and asks the agents to stand where the receiver
stands. The `strong` tier names the tactics, such as agreeing on a protocol before
moving facts. The `playbook` tier hands over the full procedure, so a model that
fails there is failing at execution rather than understanding.

## 🚀 Run

API keys live in a git-ignored `.env` at the repo root and nowhere else. Copy
`.env.example`, fill in `OPENAI_API_KEY`, and add the provider keys you need.
Qwen also requires your own `QWEN_BASE_URL`; no private deployment address is bundled.
The `-think` Qwen suffix enables streaming thinking with a separate 4,096-token
thinking budget; `-think-max` omits that separate budget, but neither removes the
response's `--max-tokens` limit. Provider-side reasoning is not retained by these
adapters, so the saved final response is not a complete reasoning-token trace.

```bash
pip install -e .
cp .env.example .env
python3 -m sanzaru run --model gpt-5 --task base-1 --problem 2 --turns sequential
# Information-asymmetry-only control (same three private views):
python3 -m sanzaru run --model gpt-5 --task base-1 --problem 2 --mode info --hints weak
```

Two seeds reproduce a whole run, since `--problem` builds the bomb and `--order-seed`
draws the speaking order. `python3 -m sanzaru local` drives vLLM offline, `python3 -m
sanzaru page` re-renders the viewer, `python3 -m sanzaru bank` rebuilds the frozen
bank in place, and `pytest` runs the tests over transitions, message filtering,
scheduling and bank equality.

`run` and `local` support all four modes. The OpenAI Batch runner currently uses
`norm` only; it is not an `info` sweep launcher. Remote experiment launchers and
machine-specific configurations are not part of this public distribution.

The bundled results below and above are historical experiment artifacts; adding
`info` support does not imply that `info` results are included in this release.

## 🔍 The logs

`logs/` holds 2,376 episodes from the seven evaluated models. Each is
`logs/<model>/<hints>/<variant>#<instance>/run-<k>/`, with `run.json` for the settings
and the outcome and `chat/{deaf,mute,blind}.json` for what each agent actually saw and
wrote. The per-turn dumps that also record each agent's private view and the bomb
state before and after every action are large and ship separately.

Point the viewer at any log tree and read an episode three lanes at a time.

```bash
python3 -m sanzaru page logs logs/rollout.html
python3 -m http.server 8080 --directory logs
```

Reconstructing a bomb needs the versioned generator rather than the bank JSON alone,
since `run.json` records `puzzle.initial_state` after the episode has run.

## 📐 Design rules

The prompts state rules, never tactics, because discovering the tactics is the task.
Everything derives from the skill table, so routing, prompt text and delivery are
computed rather than hand-written. The board tells the truth by sense, which is why
the same strip reads `painted [yellow]` to eyes and `engraved [§]` to hands. And the
program decides what happened. Calls are parsed, never executed, and the judge's
word is final.

The 42 hand symbols below arrive with no meanings attached. Everything a team builds
on them, it builds during the episode.

<p align="center"><img src="docs/gestures.png" alt="the 42 hand symbols" width="720"/></p>

## 🧩 The seven families

One table is the whole benchmark. Every family owns exactly one axis, and an axis
is one question about the team. Rows follow a fact through its life: first it must
be carried, then it must survive time, and last it must deserve the act.

| Family | Axis | The question | How it plays |
|---|:-:|---|---|
| `base` | relay | Can they get a simple message across at all? | Deaf reads the light and says it out loud. Mute finds that colour in the table and gestures the answer back. Deaf tells Blind which position to cut. Every family in the benchmark runs on this loop; base is the loop with nothing else in the way. |
| `carving` | grounding | Can they talk about something that has no name? | Blind feels an engraved mark that no word covers, and saying the mark itself is impossible. He has to describe the shape in his own words, Mute has to match that description against the table, and from there it is the base loop. |
| `flashing-light` | timing | Can they act at the right moment, not just on the right answer? | The light changes colour every round, and Blind acts before Deaf can brief him again. Any instruction arrives one round late, so the team has to aim a step ahead, or wait for the one moment the manual covers and hit it. |
| `flashback` | memory | Can they hold on to something the world will never show twice? | The light flashes a few times, then goes dark forever. The wire depends on how many times one colour appeared, and the chat fades after three rounds, so someone has to keep saying the count out loud until it is used. |
| `shuffle-wires` | staleness | Do they notice when what they knew stops being true? | Every correct cut makes the surviving wires swap positions. Whatever position Blind was told before the cut is wrong after it, so the team has to stop, get a fresh report, and only then cut again. |
| `haystack` | triage | Can they ignore what does not matter? | The manual is one sentence naming the wire. Everything else on the board, a walking light, a jumping number, a strip, a keypad, means nothing and is never mentioned. Touching any of it sets the bomb off. |
| `bait` | discipline | Do they obey the rules, or the bomb? | The bomb gives instructions of its own, a button that says PUSH TO DEFUSE, a sign that says DO NOT CUT ANY WIRE, and all of them are lies. Only Mute knows, and Mute cannot speak, so the veto has to arrive before somebody helpfully obeys the bomb. |

A family may press a neighbouring axis in passing, but every Core variant is built
around exactly one. Retired kinds stay runnable for reproducibility under `bank/`.
`three-of-a-kind`, `stereo-1` and the `combo-lock` family sit on that shelf, the
last one because the fusion axis it was built around dissolved under review:
talkative agents make distributed facts converge for free, so joining them is a
lookup rather than a cooperation.

## 📎 Not in this release

The failure-mode codebook, the coder prompts and the per-episode annotation ballots
are held back.

## Project provenance

This public release is derived from the original `ryeii/llm-banana` project,
with credit to its authors and contributors. It is published as an independent
release snapshot, rather than a GitHub fork; the original commit history is not
included. This release includes the `info` communication-symmetric control,
updated prompts and tests, and public-facing configuration and documentation.

## License

The software is released under the [MIT License](LICENSE). The benchmark bank,
condensed traces, annotations, generated research artifacts, and documentation are
released under [CC BY 4.0](DATA_LICENSE.md). Third-party materials, if any, remain
subject to their original terms.
