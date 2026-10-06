# Discord

Discord gets a native bot. It joins your voice channel, plays clips straight into it (no loopback
setup to *play*), and is driven by slash commands everyone in the server can use:

| Command | What it does |
| --- | --- |
| `/soundboard join` | Joins the voice channel you're in, announces itself, starts reacting |
| `/soundboard leave` | Leaves (it also leaves on its own when everyone else has gone) |
| `/soundboard on` / `/soundboard off` | Pause and resume reacting (it stays in the channel) |
| `/soundboard vibe <text>` | Steers it: "only hype people up", "roast the losses, gently" |
| `/soundboard level chill\|normal\|trigger-happy` | How eager it is to react |
| `/soundboard play <clip>` | Plays a clip right now (autocompletes) |
| `/soundboard clips` | Lists the sounds and what each one is for |

Prefer another name? Set `discord_command = "sfx"` (or `JEVBOARD_DISCORD_COMMAND=sfx`) and the
commands become `/sfx join` and so on.

## How it hears the channel (read this first)

Since **March 2026** Discord requires its **DAVE** end-to-end encryption on every voice call, bots
included. *Sending* audio under DAVE works in today's libraries. *Receiving* it, so a bot can hear
the channel, is still unreliable everywhere as of **October 2026**:

| Library | Voice receive under DAVE |
| --- | --- |
| **Pycord 2.8** (what jevboard uses) | Supports DAVE for sending. Receive is officially broken: the library itself warns "Voice reception is currently broken due to Discord's DAVE" and is reworking it in [pycord#3139](https://github.com/Pycord-Development/pycord/issues/3139) (PR #3159 open). There's a separate open bug where receive stops after 5–9 minutes ([pycord#3388](https://github.com/Pycord-Development/pycord/issues/3388)). |
| discord.py 2.7 + discord-ext-voice-recv | discord.py 2.7 added DAVE for sending ("tentative"). The DAVE-capable receive extension is a [GitHub-only fork](https://github.com/zacker150/discord-ext-voice-recv) that pins its own discord.py fork and says "no guarantees". |
| discord.js @discordjs/voice 0.19 | Receive under DAVE reported broken: reconnect loops, zero audio, decryption failures ([discord.js#11419](https://github.com/discordjs/discord.js/issues/11419)). |

So jevboard is honest about it, with three listening modes (`discord_listen`):

- **`local` (default, works today):** the bot *plays* into the channel, and the computer running
  jevboard *hears* the channel through its own Discord desktop app. You (or a spare account) sit
  in the same voice channel with Discord's output routed through a loopback device, exactly like
  the [FaceTime setup](AUDIO-SETUP.md): Discord **Output Device** → Multi-Output (headphones +
  BlackHole 2ch), and `listen_device = "BlackHole 2ch"`. You keep your normal mic in Discord,
  because the bot is the one playing clips.
- **`native` (experimental, untested):** the bot hears the channel itself. Every member's audio is
  mixed into one "room" stream (one transcription, everyone in it). This uses Pycord's receive
  path, which upstream says is broken under DAVE right now, so expect silence until Pycord ships
  the fix. When it does, this becomes the zero-setup mode.
- **`off`:** no listening at all. The bot is a slash-command soundboard (`/soundboard play`) and
  needs no OpenAI key. This is what the Docker image runs by default.

## Setup

### 1. Create the bot

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and click
   **New Application**. Name it `Soundboard` (that's what people will see).
2. **Bot** tab: click **Reset Token** and copy it. This is your `DISCORD_BOT_TOKEN`: treat it
   like a password. No privileged intents are needed (jevboard only uses Guilds and Voice States).
3. **General Information** tab: copy the **Application ID**.

### 2. Put the token in `.env`

```sh
cp .env.example .env
# edit .env:
#   TYPESAFE_API_KEY=...      (Jev)
#   OPENAI_API_KEY=...        (speech-to-text; not needed with discord_listen = "off")
#   DISCORD_BOT_TOKEN=...
```

`.env` is git-ignored. Never paste the token into code, config files you commit, or chat.

### 3. Invite it to your server

Open this link with your Application ID in it:

```
https://discord.com/oauth2/authorize?client_id=YOUR_APPLICATION_ID&scope=bot+applications.commands&permissions=2150632448
```

`2150632448` grants exactly: **View Channels**, **Send Messages** (for the join notice),
**Connect**, **Speak** and **Use Application Commands**. The bot also prints this link when it starts.

### 4. Run it

```sh
uv sync --extra discord
brew install opus              # macOS; Debian/Ubuntu: apt install libopus0
uv run jevboard doctor --discord
uv run jevboard discord
```

Join a voice channel and type `/soundboard join`. Global slash commands can take up to an hour
to appear the first time. To see them instantly in your own server, set
`discord_guild_ids = "<your server ID>"` (Developer Mode → right-click the server → Copy Server ID).

The control panel (vibe, trigger level, on/off, cost) works for Discord too: open the URL
`jevboard discord` prints.

## Consent and privacy

Every time it joins, the bot posts:

> 🔊 **Soundboard** is in **General** and listening, to react with sound effects (powered by Jev).
> Speech is turned into text live and judged on the spot: no audio or transcripts are saved.
> `/soundboard off` pauses it, `/soundboard leave` sends it away.

That is how it works, and it's in line with Discord's
[Developer Policy](https://discord.com/developers/docs/policies-and-agreements/developer-policy)
on voice data:

- **No recording.** Audio is never written to disk. Live speech streams to the transcriber and
  is discarded.
- **Transcripts live only in memory:** a rolling ~25 s window that Jev judges, cleared on
  `/soundboard off` and when the bot leaves.
- What leaves the machine: audio to the speech-to-text API (OpenAI), and transcript text to Jev
  (TypeSafe). Check both providers' data policies if that matters for your server.
- Tell your server it's there. Don't run it in channels where people haven't agreed to it.

## Run it 24/7

Any always-on machine works (a home server, a small VPS, a Raspberry Pi 4/5). Docker:

```sh
docker build -t jev-soundboard .
docker run -d --restart unless-stopped --name soundboard \
  --env-file .env \
  -v "$PWD/clips:/app/clips" -v "$PWD/state:/app/state" \
  -p 127.0.0.1:8787:8787 \
  jev-soundboard
docker logs -f soundboard        # shows the invite link and the panel URL
```

A container has no sound card, so it runs `discord_listen = "off"` (manual soundboard) unless you
set `-e JEVBOARD_DISCORD_LISTEN=native` to try experimental receive. For full auto-reactions
today, run it on a desktop with the `local` listening setup above.

Without Docker: `uv run jevboard discord` under systemd, launchd, tmux, or anything that restarts it.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| No slash commands | Wait (global commands take up to an hour), or set `discord_guild_ids`. Re-invite with the link above if `applications.commands` was missing. |
| "Join a voice channel first" | Run `/soundboard join` while you're in a voice channel. |
| Bot joins but no sound | `jevboard doctor --discord`: Opus or `davey` missing? Check the bot has **Speak** in that channel, and isn't server-muted. |
| Bot plays but never reacts | `discord_listen = "local"`: is Discord's output going through BlackHole 2ch? `jevboard doctor` shows the listen device. `native`: expected for now, see above. |
| Reacts to the wrong things | `/soundboard level chill`, `/soundboard vibe`, and sharpen your clips' descriptions ([guide](BUILD-YOUR-CLIP-LIBRARY.md)). |
| `Unknown transport` / import errors | `uv sync --extra discord` (it installs py-cord, PyNaCl and davey). Don't install `discord.py` alongside: the two share the `discord` package name. |
