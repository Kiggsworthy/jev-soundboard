# Build your clip library

The 15 built-in sounds get you started. What makes a soundboard *legendary* is a library of
short, instantly recognisable reaction moments that your group already knows: the clips that
make everyone laugh before the second word. This guide is the method we used, plus the prompts
to hand an AI assistant (Claude or similar) at each step.

> **Rights first.** Only use clips you have the right to use. A private call between friends is a
> very different thing from a public stream, a recording or a YouTube upload. Respect YouTube's
> Terms of Service and creators' rights, and when you're unsure, don't. This repo ships no
> third-party audio, and `clips/` is git-ignored so yours stays on your machine.

## The method

```
Plan slots ─> Find ─> Fetch ─> Trim ─> Screen ─> Describe ─> Add ─> Test on a real call ─> Tune
```

1. **Plan:** decide the *moments* you want to react to before hunting for sounds. That's slots,
   not clips.
2. **Find:** YouTube Shorts is the richest source of short, punchy reaction moments, already cut
   down by someone else. Search per slot.
3. **Fetch:** download just the audio (and just the part you need) with `yt-dlp`.
4. **Trim:** **1–4 seconds**, starting on the first sound with no lead-in, faded out, and
   loudness-normalised so nothing is louder than anything else.
5. **Screen:** transcribe every clip and reject swearing, slurs, sexual lines or anything mean.
   Family-safe by default.
6. **Describe:** write a sharp **"when to use it"** line. This is the secret sauce: Jev never hears
   the clip, only reads the description, so the description *is* the clip as far as the
   decision goes.
7. **Add** it to `clips/index.json`, then **test** it on a real call and tune.

`jevboard clips add` does steps 3–7 in one command:

```sh
uv sync --extra clips       # installs yt-dlp (or: brew install yt-dlp)

jevboard clips add "https://www.youtube.com/shorts/VIDEO_ID" --start 3.2 --end 5.9 \
  --name deflate_bruh \
  --desc "Deflating 'bruh': someone says something painfully obvious, cringe, or brags about something tiny."
```

It downloads only that section, trims leading silence, caps the length (`--max`, default 4 s),
fades the tail, normalises loudness (-18 LUFS), converts to mono 48 kHz, transcribes it, rejects
it if the screen trips (into `clips/rejected/`), and writes the index entry. A local file works
the same way: `jevboard clips add ~/Downloads/thing.m4a --start 1 --end 3 ...`.

Other tools:

```sh
jevboard clips list              # built-ins + yours, flags anything unscreened
jevboard clips screen            # screen clips you added by hand
jevboard clips screen --again    # re-screen everything (e.g. after editing clips/banned.txt)
jevboard try "line one" "line two"   # see what Jev picks, without a call
```

Screening uses OpenAI speech-to-text (`OPENAI_API_KEY`) plus a family-safe word list. Add your own
patterns, one regex per line, in `clips/banned.txt`. The screen only catches *words*: always listen
to a clip yourself before your group hears it.

## Library tips

- **Variety beats volume.** 40 clips that each own a distinct moment beat 200 that blur together.
  Jev picks better from a menu where every option means something different.
- **Short wins.** A reaction lands in the second after the moment, or it doesn't land. Most great
  clips are 1–2 s. Save 3–4 s for the rare "theme music" moment.
- **No near-duplicates.** Two different "sad" clips with similar descriptions split Jev's choice
  and make both weaker. Either merge them, or describe the *difference* ("a small fail" versus
  "a total catastrophe").
- **Recognisable is everything.** The best clip is the one your group knows instantly. Ask them.
- **Tune after real calls.** Watch the control panel log: every reaction shows the line that
  triggered it. If a clip fires at the wrong moments, rewrite its description. If it never fires,
  the description is too narrow or overlaps a stronger one. Use `/soundboard level` or the panel
  for overall eagerness, and the description for *which* clip.
- **Anti-repeat helps you:** a clip can't replay until up to 25 others (or half the board) have
  played, so a bigger, varied library also feels fresher.

## Writing descriptions Jev matches well

Jev reads the rolling transcript and picks the description that best fits **the meaning** of the
newest line. Good descriptions:

- **Lead with the moment, not the sound.** "Someone confidently says something completely wrong."
  Don't write "a funny buzzer noise".
- **Name 2–4 concrete situations,** in the words people actually say on a call.
- **Draw a boundary** when a neighbouring clip exists: "a *small* fail (for a big disaster, use
  something bigger)".
- **Keep it to one or two sentences,** with no clip trivia, source names or in-jokes Jev can't know.
- **Say the tone** if it matters: affectionate, mock-serious, triumphant.

| Weak | Strong |
| --- | --- |
| "bruh sound" | "Deflating 'bruh': someone states the painfully obvious, says something cringe, or brags about something tiny." |
| "funny laugh" | "A mocking laugh: someone fails right after bragging, or walks straight into an obvious trap." |
| "victory music" | "Triumphant fanfare: someone finally wins after struggling, or pulls off something that seemed impossible." |
| "suspense" | "Tense suspense sting: someone is about to reveal a result, make a risky move, or confess something." |
| "scream from a movie" | "Over-the-top scream: a sudden scare, a jump-out moment, or someone reacting way too dramatically." |

## Prompts

Copy these into Claude (or any capable assistant). Fill in the `<angle brackets>`.

### 1. Brainstorm a balanced library

```text
I'm building a soundboard for an AI sidekick that listens to a live voice call and plays a
short reaction clip at the right moment. The group: <who: e.g. a family that plays games
together / five friends who play co-op games>. The vibe: <e.g. silly and affectionate, never mean>.

Design a library of <40> "slots". A slot is a MOMENT worth reacting to, not a specific clip.
Balance it across moods: hype, celebration, fail, cringe, shock, suspense, wholesome,
awkward silence, confusion, a "bruh"-style deflate, triumphant comeback, mock-dramatic,
plus anything else that comes up on calls like ours.

For each slot give:
- slot_name (lower_snake_case)
- mood
- the moment it's for (1 sentence, concrete, in call language)
- 2 example lines someone might say that should trigger it
- what makes it different from its nearest neighbour slot

Avoid near-duplicates. Flag any slot that would need a mean or embarrassing clip and propose a
kinder version. Output a table.
```

### 2. Turn slots into YouTube Shorts searches

```text
For each slot below, write 3 YouTube Shorts search queries likely to surface a SHORT (1–4 s),
punchy, instantly recognisable audio moment that fits it. Favour queries ending in phrases like
"sound effect", "meme sound", "reaction", or "short". Prefer sounds a <age/group> group would
already recognise. Skip anything that is likely to contain swearing.

Slots:
<paste slot_name + moment for each>

Output: slot_name | query 1 | query 2 | query 3
```

### 3. Pick the exact 1–4 s cut

Get a timestamped transcript (YouTube's "Show transcript", or
`yt-dlp --write-auto-subs --skip-download URL`), then:

```text
Here's a timestamped transcript of a short video. I want ONE reaction clip for this moment:
"<the slot's moment>".

Pick the single best cut:
- 1 to 4 seconds long (shorter is better)
- starts right on the first sound (no lead-in or breath)
- ends right after the punchline word or beat
- contains NO swearing, slurs or sexual content, and nothing mean about a real person
- makes sense with zero context

Reply with: start seconds, end seconds, the exact words in the cut, and one line on why it
works. If nothing in this video fits, say so.

Transcript:
<paste>
```

Then run `jevboard clips add URL --start S --end E --name ... --desc ...` and *listen to it*.
Nudge `--start` and `--end` by 0.1–0.3 s until it snaps.

### 4. Write the "when to use it" description

```text
Write the "when to use it" description for a soundboard clip. An AI that has only read the
description (it never hears the audio) will decide, from a live call transcript, whether this
clip fits the newest line.

The clip: <what it sounds like, in plain words>
The slot it fills: <moment>
Its nearest neighbours on the board: <names + descriptions>

Rules:
- Lead with the moment, not the sound. 1–2 sentences, under 30 words.
- Name 2–4 concrete situations, in words people actually say on calls.
- If a neighbour is close, state the boundary ("small fails; not disasters").
- Say the tone if it matters (affectionate, mock-serious, triumphant).
- No source names, quotes, trivia or in-jokes.

Good: "Deflating 'bruh': someone states the painfully obvious, says something cringe, or brags
about something tiny."
Bad: "bruh sound effect" (that's the sound, not the moment).
Bad: "Use when funny" (too vague: everything is funny).

Give 3 options, then recommend one.
```

### 5. Family-safety screen

`jevboard clips add` already transcribes each clip and checks a word list. For a second opinion
on tone (which a word list can't judge):

```text
Here are transcripts of short soundboard clips that will play on a family call with kids
aged <ages>. For each one, answer SAFE or REJECT, and give the reason for anything rejected.

Reject: swearing (including bleeped or mumbled), slurs, sexual content or innuendo, violence
that's more than cartoonish, anything that mocks someone's body, identity or ability, and
anything that would sting if aimed at a sibling. Allow: silly, cartoon-mild, mock-dramatic,
playful teasing.

<name>: "<transcript>"
...
```

### 6. Audit the finished library

```sh
jevboard clips list > my-clips.txt
```

```text
Here is my soundboard: clip names and their "when to use it" descriptions. An AI picks one
per moment on a live call, using only these descriptions.

Audit it:
1. Overlaps: pairs whose descriptions would compete for the same moments. Suggest a boundary
   for each, or say which one to drop.
2. Gaps: common call moments with no good clip (think: wins, fails, brags, confusion, awkward
   silence, someone joining or leaving, a surprise, a great idea, a dumb idea, suspense,
   wholesome moments).
3. Weak descriptions: vague, sound-first, or too narrow to ever fire. Rewrite them.
4. Balance: count clips per mood. Is the board too negative, too mean, or too samey?

Give a prioritised list of changes, max 10.

<paste my-clips.txt>
```

## Then: play

Run it on a real call, keep the panel open, and watch the log. After a session, take the three
clips that misfired and the three moments that deserved a reaction but didn't get one, and fix
those descriptions. A library tuned over three or four calls feels like it can read the room.
