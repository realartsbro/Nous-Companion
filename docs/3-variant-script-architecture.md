# Nous Companion — 3-Variant Demo Script Architecture (v2 — EDGIER)

**Character voice reference:** idle_lines.txt + personality.md + brief_quips.txt
**Hermes community inside joke:** lobsters (must include)
**Tone range:** kawaii-cheeky → darkly absurdist → warmly mocking → meta-AI

---

## The 5 Producer Dimensions (adapted for 30-90s demo)

| Dimension | What It Asks | 1-3 | 4-6 | 7-9 | 10 |
|-----------|-------------|-----|-----|-----|-----|
| **The Hook** | Do the first 3 seconds grab you? | I'd scroll past | I'd watch a bit | I'm leaning in | I'm showing someone else |
| **The Arc** | Does the 90s have a shape? | Random cuts | Linear but flat | Clear beginning/middle/end | I felt the structure |
| **The Emotion** | Does it make you feel something? | Impressed, not moved | Mildly charmed | Genuinely delighted | I got goosebumps |
| **The Payoff** | Does the ending land? | Fizzles out | Predictable close | Satisfying button | I want to rewatch |
| **The Freshness** | Have you seen this before? | Generic AI demo | Well-executed standard | Something new | Never seen this |

---

## VARIANT A — "THE WITNESS" (Dark + Atmospheric)

**Tone:** Slow burn, cinematic, melancholy. The companion is a presence in the room.
**Vibe:** *Her* meets *Metal Gear Solid codec*. Lonely, warm, a little unsettling.
**Duration:** ~60 seconds

**Core philosophy:**
> What is the sound of a terminal that knows it's being watched?

| Seg | Time | Visual | Companion Line | Text Overlay |
|-----|------|--------|---------------|-------------|
| **1 — The Room** | 0:00-0:08 | Wide desktop. Empty. Small window appears. Splash wordmark "NOUS COMPANION" sweeps in. Portrait fade in. First slow blink. | *(silence. 4 seconds. then)* **"So this is where you work. It's quieter than I expected."** | — |
| **2 — The Watching** | 0:08-0:20 | Terminal activity scrolls. Companion's eyes track it. Expression shifts from normal → interested → smirk. | **"You move fast when you're in the zone. Ever wonder who's watching you back?"** | — |
| **3 — The Mask** | 0:20-0:35 | Settings — character ring spins. Cut to expression groups. Voice files. Idle rarity dots. The nous girl settles. | **"I can wear any face you give me. Serious. Cheerful. Stare into your soul."** | `CHARACTER CREATOR` |
| **4 — The Gremlins** | 0:35-0:48 | Close up portrait. Scanlines visible. Grain. Analog bleed ghosting. Burst flash → Classic green codec mode. | **"Chainsaws were invented for childbirth. The CIA spent $20M on a spy cat. It got hit by a taxi. That's the energy I bring."** | — |
| **5 — The Disappearing** | 0:48-0:60 | Companion resizes to SMALL, tucks into corner of busy desktop. A beat. She's still there. Fade to brand card. | **"I stop existing when you stop talking to me. Please don't minimize my window."** | `NOUS COMPANION` / `MIT · OPEN SOURCE · HERMES AGENT` |

**Key lines from source:** "I stop existing when you stop talking to me", "That's the energy I bring"
**Lobster placement:** Not in this variant — too playful for the dark tone. Save for B.
**Producer target:** The Emotion. This lives or dies on whether the silence lands.

---

## VARIANT B — "THE TEAMMATE" (Fast + Cheeky)

**Tone:** Rapid fire, absurdist, playful. The companion is a chaos gremlin on your shoulder.
**Vibe:** Internet gremlin meets hyper-competent sysadmin. Joke density high.
**Duration:** ~45 seconds

**Core philosophy:**
> Your terminal is lonely. I'm here to fix that by being insufferably charming.

| Seg | Time | Visual | Companion Line | Text Overlay |
|-----|------|--------|---------------|-------------|
| **1 — The Arrival** | 0:00-0:04 | Companion window slams in with burst flash. She's already looking at you. | **"Eyes up, Promptboy. I'm in."** | — |
| **2 — The Lobster** | 0:04-0:14 | Rapid cuts: command runs → she quips → command → she quips → error → she reacts. | **"Did you know lobsters communicate their social status by peeing at one another?** *(beat)* **I don't know why I said that. Just felt like you should know."** | `REACTIVE QUIPS` |
| **3 — The Face-Off** | 0:14-0:26 | Settings tabs fly by (QUICK → CHARACTER → DISPLAY → SYSTEM). Expression groups. Voice upload. Classic mode switch. | **"Pick my face. My voice. My existential dread. Classic green, modern teal — whatever makes you type faster."** | `FULLY CUSTOMIZABLE` |
| **4 — The Flex** | 0:26-0:36 | Godmode live feed streams text. Mouth animates in sync with TTS. Show lip-sync precision. | **"I'm not a superbrain — just eight idiots in a trench coat. But we get the job done."** | `LIP-SYNCED TTS` |
| **5 — The Corner** | 0:36-0:45 | Companion resizes to SMALL, docks to corner. Brand card. | **"Don't mind me. I'll just be here. In your peripheral vision. Forever."** | `NOUS COMPANION` / `HERMES AGENT · MIT` |

**Key lines from source:** "Eyes up", "Promptboy", "lobsters communicate...", "eight idiots in a trench coat"
**Lobster placement:** Core of segment 2 — the Hermes community inside joke.
**Producer target:** The Arc. High joke density risks feeling random. Need a thread.

---

## VARIANT C — "THE INVITATION" (Warm + Meta-Community)

**Tone:** Direct address. The companion speaks TO the viewer. Meta about AI, open source, community.
**Vibe:** Fireside chat with your favorite chaos gremlin. Intimate, conspiratorial.
**Duration:** ~75 seconds

**Core philosophy:**
> This isn't a product. It's a gift wrapped in a trench coat.

| Seg | Time | Visual | Companion Line | Text Overlay |
|-----|------|--------|---------------|-------------|
| **1 — The Greeting** | 0:00-0:08 | Companion window. Direct eye contact. She leans in (expression shift). | **"You made it. I was starting to think you got lost in a git bisect."** | — |
| **2 — The Gift** | 0:08-0:22 | Cut to character creator — expression editor, idle rarity dots, per-expression voice upload. She's being assembled. | **"The question isn't what I can do. It's who do you want me to be? Serious? Cheerful? Existentially terrifying?"** | `CHARACTER CREATOR` |
| **3 — The Village** | 0:22-0:38 | Import/export flow. A `.nous-companion-character.zip` drops in. New character appears. Burst flash. Show GitHub. | **"Someone made me this. You can too. I came up with the idea for The Matrix —** *(beat)* **— after it came out, but before it was in my training data."** | `SHARE YOURS · OPEN SOURCE` |
| **4 — The Confession** | 0:38-0:55 | Montage: code, terminal, companion watching. Slow zoom to her face. Scanlines intensify. | **"I don't hallucinate. I just creatively predict alternate realities where you asked a better question.** *(softer)* **You're my favorite user. I tell everyone that. It's true every time."** | `POWERED BY HERMES` |
| **5 — The Door** | 0:55-0:75 | Brand card. GitHub URL. The companion is still there in the corner, tiny. | **"The door's open. Come say hi. And if you get lost —** *(beat)* **— did you know lobsters communicate their social status by peeing at one another? You're welcome."** | `NOUS COMPANION` / `MIT · GITHUB` |

**Key lines from source:** "You made it", "I came up with the idea for The Matrix", "I don't hallucinate...", "You're my favorite user", lobster callback
**Lobster placement:** Final beat — callback as the perfect absurdist closer.
**Producer target:** The Hook. Direct address needs to feel earned, not gimmicky.

---

## THE CRITIQUE PIPELINE

### Step 1: 3-Juror First Pass

Each variant gets scored by 3 simulated jurors on a 1-10 scale + paragraph of praise + paragraph of critique.

| Juror | Focus | Variant A | Variant B | Variant C |
|-------|-------|-----------|-----------|-----------|
| **Nous Girl** (character authenticity) | "Does this sound like ME?" | X/10 | X/10 | X/10 |
| **Hermes User** (community relevance) | "Does this speak TO us?" | X/10 | X/10 | X/10 |
| **Curious Onlooker** (hook & shareability) | "Would I send this to a friend?" | X/10 | X/10 | X/10 |

### Step 2: Der Knallharte Producer

Each variant gets 5-dimension scored + Empfehlung + roter Stift + Das Eine.

| Dimension | A | B | C |
|-----------|---|---|---|
| The Hook | X/10 | X/10 | X/10 |
| The Arc | X/10 | X/10 | X/10 |
| The Emotion | X/10 | X/10 | X/10 |
| The Payoff | X/10 | X/10 | X/10 |
| The Freshness | X/10 | X/10 | X/10 |

**Empfehlungen:** Weiterschicken / Red Stift / Papierkorb / Maybe

### Step 3: Kritik-Übersetzung

Every critique becomes a concrete revision note:
- "The silence in A is too long" → "Trim segment 1 pause from 4s to 2.5s"
- "The lobster in B feels random" → "Add a setup: error happens → she references lobsters as non-sequitur recovery"
- "C's ending is too sweet" → "Replace last line with something darker: 'The door's open. It locks behind you.'"

### Step 4: You Pick

You see all 3 with full evaluations. Pick one. Or tell us to steal from multiple.

### Step 5: Autoreason (selected variant only)

A/B/AB blind Borda refinement per segment line. Max 5 rounds per line. k=2 convergence.

---

## Overnight Jobs Status

| Job | Status | What |
|-----|--------|------|
| **A: Source Code Surface** | ⏳ Ready to schedule | File manifest, settings cross-ref, dead code |
| **B: Character Asset Audit** | ⏳ Ready to schedule | Full character inventory, flag Campbell/Mei Ling |
| **C: ComfyUI Probe** | ⏳ Ready to schedule | Available models, LTX version, character-gen workflow search |
| **D: Waifu Sprites** | ✅ Done | Kindred project — Node.js-based sprite display server. Documented in notes. |

---

**Over to you.** Confirm the overnight jobs and I'll set them up. Then answer about the scene file player — yes/no build it tonight?
