# Nous Companion — Creative Toolkit & Storytelling Framework

*Extracted methodology from the debut-fiction pipeline, applied to our demo.*

---

## PART 1: THE DEBUT-FICTION METHODOLOGY (What We Steal)

### 1.1 The Core Question (Before Anything)
```
What is this video saying?
What is the sub-text (never spoken)?
What does the viewer feel after watching?
```

**Our draft core:**
> SAID: "Your Hermes Agent has a face now. A living character that watches, reacts, speaks."
> SUB-TEXT: "We turned an invisible AI process into a relationship. That's what makes this different."
> VIEWER FEELS: Recognition. The terminal IS lonely. This fixes that in a way they've wanted but couldn't articulate.

### 1.2 The 3-Jury System (deployed on EVERY creative decision)

Debut-fiction uses three jurors: emotional, institutional, visionary. For our demo we have three audiences:

| Role | Asks | Sensitive To |
|------|------|-------------|
| **The Nous Girl** (Kawaii/Emotional) | "Does this feel like ME? Am I charming? Is there soul here?" | Generic AI vibes, soulless features, being treated as a tool |
| **The Hermes User** (Technical/Power) | "Does this actually help me work? Is it zero-friction? Does it perform?" | Bloat, complexity, solving problems nobody has |
| **The Curious Onlooker** (Community/Invite) | "Can I be part of this? Can I make my own? Is the door open?" | Closed ecosystems, "not for you" energy, high barriers |

**When we write a line of the script, when we choose which feature to show, we run it past these three.** If any one of them would reject it, we revise.

### 1.3 The Element Abstraction Method

From the Element Deep Dive skill: a Karteikarte (index card) describes what a feature COMMUNICATES, not what it LOOKS like.

**Applied to our features:**

| Feature | What It LOOKS Like | What It COMMUNICATES |
|---------|-------------------|---------------------|
| Character creator | Upload sprites, set expressions, configure rarity | "You are not limited to what we built. This is YOUR space." |
| Per-expression voice | Different WAV files per emotion | "Your companion can be serious when you're serious, warm when you need warmth." |
| Idle rarity system | Weighted dots 1-5 | "She has her own rhythms. She's alive between your interactions." |
| Analog bleed / interference | Ghost copies on canvas | "We cared enough to bring back the imperfections. This is made with love, not requirements." |
| Classic MGS1 mode | Green codec bars | "We know where our influences come from. We nod to them without pretending they're ours." |
| Godmode live feed | Streaming text overlay | "You can see her thinking. Trust through transparency." |
| Edge snapping | Window docks to screen corner | "She stays out of your way until you need her. But she's always there." |

### 1.4 Anti-Pattern Catalog (Do Not Violate)

From the voice contract, these are banned in our script and README:

| Banned | Why | Replace With |
|--------|-----|-------------|
| "Not just a companion, but a friend" | "Not X, but Y" template | Just say what it IS: "A companion for your terminal." |
| "The AI companion you deserve" | Slogan language, tells viewer how to feel | "Made for people who like their terminal to have a face." |
| "Join the future of agent interaction" | Generic truism, TED-talk energy | "Open source. MIT. Go make something." |
| "Isn't she adorable?" | Tells viewer how to feel, breaks trust | Let the companion's design speak. Describe her, don't sell her. |
| "Revolutionize your Hermes experience" | Overclaim, sets wrong expectation | "A small window. A character that reacts. That's it." |
| Questions in the copy ("What if your terminal had a face?") | Weak, rhetorical, LLM-speak | Declarative statements only. "Your terminal has a face now." |

---

## PART 2: THE DEMO VIDEO AS PERFORMANCE

### 2.1 The Insight

You mentioned: the companion should perform scripted lines timed to the video, not react live.

This is the right approach. The debut-fiction pipeline has a word for this: **Autoreason** — but applied to a script rather than prose. The loop is:

```
Draft Script → 3-Perspective Critique → Consensus?
  YES → Write companion lines to match
  NO  → Revise, Loop
```

### 2.2 Script Structure (5 Segments)

**Segment 1 — "Arrival"**
- Core: The desktop is empty. Then she appears.
- Companion line: *"So this is where you work. It's... quiet."*
- Visual: Blank desktop → companion window fades in → first blink
- What viewer feels: Anticipation. Something new.

**Segment 2 — "Witness"**
- Core: She watches what you do. She reacts to what she sees.
- Companion line: *"Writing something? Take your time. I'll be here."*
- Visual: Hermes terminal + companion side by side → companion expression shifts as work happens
- What viewer feels: Recognized. Someone is paying attention.

**Segment 3 — "Becoming"**
- Core: She's not static. You can shape her — expressions, voice, personality.
- Companion line: *"I can be whoever you need. Watch."*
- Visual: Quick cuts through settings — character ring, expression groups, voice files, idle rarity dots
- What viewer feels: Ownership. This is mine to shape.

**Segment 4 — "The Details"**
- Core: The imperfections are intentional. The love is in the cracks.
- Companion line: *"Old tech. New tricks. Somehow that feels right."*
- Visual: Close up — scanlines, grain, analog bleed, burst flash, switch to Classic green-codec mode
- What viewer feels: Delight. They cared about the experience.

**Segment 5 — "Yours"**
- Core: Open source. MIT. Community. The end is the beginning.
- Companion line: *"I'll be here. Right where you left me."*
- Visual: Companion tucks into corner of busy desktop → fade to brand card
- What viewer feels: Invitation. I can be part of this.

### 2.3 The Scene File Concept

To make the companion perform on cue, we could build a simple scene file:

```json
{
  "character": "nous",
  "scenes": [
    { "at": 0.0,  "expression": "normal",   "line": "So this is where you work. It's quiet.", "speed": 0.9 },
    { "at": 8.0,  "expression": "normal",   "line": "Writing something? Take your time. I'll be here.", "speed": 0.85 },
    { "at": 16.0, "expression": "serious",  "line": "I can be whoever you need. Watch.", "speed": 0.8 },
    { "at": 28.0, "expression": "cheerful", "line": "Old tech. New tricks. Somehow that feels right.", "speed": 0.9 },
    { "at": 38.0, "expression": "normal",   "line": "I'll be here. Right where you left me.", "speed": 0.75 }
  ]
}
```

The companion loads this file, plays through the scene at real-time. Each line triggers:
1. Expression change
2. TTS generation with the line
3. Wait for audio to finish
4. Freeze frame until next cue

**Overnight research question:** How hard is this to build? Can we modify `test_reaction` handling to accept timestamped queues?

---

## PART 3: THE CHARACTER — NOUS GIRL'S VOICE

### 3.1 Personality Brief

The `character/nous/personality.md` is the LLM system prompt that drives her quips. For the demo, we need her lines to serve the narrative, not just react to context. Two modes:

**Live Mode (what she does now):** Reads Hermes context, generates a quip. Variable, reactive, genuine.
**Scripted Mode (what we need for the video):** Plays pre-written lines on a timeline. Fixed, narrative, timed.

The personality.md needs to establish:
- She's a witness, not a protagonist. She observes your work.
- Her tone is warm but not saccharine. Direct but not cold.
- She uses short sentences. Punctuation is minimal.
- She can be playful but never at the expense of the moment.
- She references the tech without pretending to understand it deeply. "Your terminal" not "Your REPL."

### 3.2 The Nous Girl Brand (from your note: "absolutely adored by the team")

The Nous Research team loves this character. That's our green light. She's not a generic mascot — she's recognized internally. This matters for:
- The demo video: lean INTO her personality
- The community: she's the face of the project
- The GitHub repo: her presence is the brand

---

## PART 4: CREATIVE PRODUCTION RESEARCH

### 4.1 ComfyUI — Character Generation Pipeline (Research, Not Build)

**The dream:** A Hermes skill + ComfyUI workflow that lets anyone create a character by:
1. Providing a full-body or portrait reference image
2. The workflow inpaints eyes and mouth regions at pixel-perfect positions
3. Outputs a complete character folder with base + eyes + mouth sprites at the right size
4. Generates multiple expression variants (normal, serious, cheerful)

**What makes this hard:**
- Inpainting needs to be pixel-perfect — the eyes and mouth must align with the base head
- The sprite format (52×89 or custom ratio) is specific and unforgiving
- Expression groups need consistent character identity across variants

**Research questions for overnight:**
1. What's the current SOTA for local inpainting? (Flux Fill? SDXL Inpaint? Something newer?)
2. Are there community ComfyUI workflows for character sheet generation?
3. Can IP-Adapter + ControlNet be used to maintain character consistency across expressions?
4. What about AnimateDiff / LTX2.0 for generating the blink/mouth animations directly?
5. Is there a simpler path: generate a base head, then use img2img with region prompts for eyes/mouths?

**Available:**
- Portable ComfyUI at `D:\ComyBackup\ComfyUI-Easy-Install`
- LTX2.0 (older version — check if LTX2.3 is an upgrade worth doing)
- Need to check what models are actually installed

### 4.2 Video Generation (LTX2.0 / LTX2.3)

LTX Video is a transformer-based video model. LTX2.0 was the first release, LTX2.3 is the current version with improved quality.

**For our demo, video gen could be used for:**
- Short transition clips (desktop → companion window zoom)
- Atmospheric background loops for intro/outro
- Character intro animation (she appears via a text-to-video generation)

**Key capability to check:** i2v (image-to-video) — can we generate a short clip of the character blinking/waving from a single image?

### 4.3 Recording & Editing Tools

**Recordly** for screen recording.
**No copyright worries** for demo music.
**Available video pipelines:** video-compositing-production (PIL/Python), ascii-video, manim-video.

The simplest post-production pipeline:
1. Record companion window (Recordly or OBS) with the scene file playing
2. Record Hermes terminal activity separately
3. Compose in video editor (CapCut, DaVinci Resolve, or Python compositing)
4. Add music track, lower thirds, title cards
5. Export at 1080p, 60s-90s

---

## PART 5: OVERNIGHT RESEARCH JOBS (Revised)

Based on the creative focus, here's what should run:

### Job A: Source Code Surface
- Map every file, count lines, document purpose
- Find ALL "settings keys" across all 3 layers (settings.html ↔ companion_server.py ↔ renderer.js)
- Find ALL "codec" dead references (commented out, unused)
- **Purpose:** Know exactly what we have

### Job B: Character Asset Audit
- Walk every character directory
- Validate every config.yaml, positions.json
- Check PNG dimensions, existence of required files
- Flag everything that can't ship (Campbell, Mei Ling sprites)
- **Purpose:** Know what characters to remove before publishing

### Job C: ComfyUI / Creative Tools Probe
- Check if ComfyUI is running (or can be started)
- List available models and custom nodes
- Find LTX2.0 version → research LTX2.3 upgrade path
- Search for ComfyUI character generation workflows (CivitAI, Reddit, GitHub)
- **Purpose:** Know what's available for production without wasting time generating

### Job D: Competitor / Reference Research
- Search for other "desktop companion" AI tools — what exists, what doesn't
- Look at how Nous Research announces products (tone, format, style)
- Research how other Hermes hackathon entries present themselves
- **Purpose:** Know where we stand in the landscape

---

## EXECUTION PLAN

```
Thu Apr 30 (Tonight):
  02:30 — I set up cron jobs
  02:30-09:00 — Cron jobs run overnight
  
Fri May 1 (Morning):
  09:00 — Review overnight output
  09:00-12:00 — Tier 1 testing (character CRUD, settings, TTS)
  12:00-14:00 — Creative session: iterate demo script through 3-jury lens
  14:00-16:00 — Build scene file, test scripted companion performance
  16:00-18:00 — Produce video assets, generate title cards
  
Sat May 2:
  10:00-14:00 — Record footage (companion + terminal + transitions)
  14:00-18:00 — Edit demo video
  18:00-20:00 — Review cut, iterate
  
Sun May 3:
  10:00-12:00 — Final polish, tweak video
  12:00-14:00 — GitHub cleanup, README final pass
  14:00-16:00 — Tweet, submit, post in Discord
  16:00-17:00 — Done
```

---

## PART 6: AUTOREASON LOOP FOR DEMO SCRIPT REFINEMENT

*Directly adapted from debut-fiction Phase F methodology.*

### 6.1 The A/B/AB Jury Loop for Our Script

When we write companion lines for the demo, we DON'T just pick the first draft. We run each line through a mini jury loop:

```
Write companion line (A)
  → Critique (what works, what doesn't)
  → Write revision (B)
  → Write synthesis (AB = best of both)
  → 3 judges rank all 3 (blind)
  → Borda count decides winner
  → k=2 convergence or next round
  → FINAL line
```

### 6.2 Our 3 Judges (Adapted)

| Judge | Focus | What They Evaluate |
|-------|-------|-------------------|
| **Judge 1: Nous Girl** | Soul, warmth, character authenticity | "Does this sound like ME? Would I say this?" |
| **Judge 2: The Hermes User** | Clarity, relevance, tone | "Does this communicate the feature? Is it honest?" |
| **Judge 3: The Curious Onlooker** | Invitation, memorability | "Does this make me want to try it? Does it stick?" |

### 6.3 Example: Iterating Segment 2's Line

**Round 1:**
- A (Incumbent): *"Writing something? Take your time. I'll be here."*
- B (Revision, more active): *"I see you're working. What are we building today?"*
- AB (Synthesis): *"Working on something? I've got my eye on it."*

Each judge ranks blind (Proposal 1/2/3, not A/B/AB).

**After Borda count, if A wins:** keep A, move to next segment.
**If B or AB wins:** becomes new A, loop again.
**k=2 convergence:** same winner 2 rounds in a row → FINAL.

### 6.4 Conservative Tiebreak Rule

When two variants score equally: the SAFER option wins. Don't be clever at the expense of clarity. "Better preserved than regretted."

### 6.5 Scope Rule per Pass

Each refinement pass has ONE focused scope. Examples:
- "Make the line shorter — under 5 seconds spoken"
- "Strengthen the warmth — it's too clinical"
- "Add a tech reference — it's too generic"
- "Remove the tech reference — it's too jargon-y"

Never "make it better." Always a specific scope.

### 6.6 Max Rounds

5 rounds max per segment line. After 5, pick the best so far and move on. Perfection is the enemy.

### 6.7 When We Do This

Not now. This is for **Fri May 1 afternoon** — after overnight research completes and we have the landscape. We sit down, draft lines, run the jury loop, and converge on the FINAL 5 lines that become the companion's performance.
