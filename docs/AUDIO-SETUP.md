# Audio setup (FaceTime first)

jevboard's `local` transport works with any app that lets you pick its microphone and speaker:
FaceTime, the Discord desktop app, Zoom, Meet in a browser, OBS. It needs two things:

1. **The call's audio coming in**, so Jev can hear what's being said.
2. **The clips going out**, into the call, so everyone hears them.

On a Mac, both go through free virtual "loopback" audio devices.

```
                  ┌───────────── Multi-Output Device "Call + Me" ─────────────┐
FaceTime output ──┤                                                            │
                  ├──> your headphones      (you hear the call)               │
                  └──> BlackHole 2ch ──────> jevboard listens ──> Jev decides │
                                                                    │
your real mic ─────────────────────────────> jevboard (mic passthrough)
                                                  │  + clips
                                                  ▼
                                            BlackHole 16ch ──> FaceTime microphone
                                                                (everyone hears you + clips)
```

## 1. Install the loopback devices

```sh
brew install blackhole-2ch blackhole-16ch
```

(Or download [BlackHole](https://github.com/ExistentialAudio/BlackHole). Any loopback works:
Loopback, VB-CABLE and so on. Just use their names below.) You'll use two of them:
**BlackHole 2ch** carries the call to jevboard, and **BlackHole 16ch** carries jevboard to the call.
Two separate devices are what stop a feedback loop.

## 2. Hear the call and send it to jevboard (Multi-Output Device)

1. Open **Audio MIDI Setup** (in /Applications/Utilities).
2. Click **+** at the bottom left, then **Create Multi-Output Device**.
3. Tick **your headphones** first, then **BlackHole 2ch**. Turn on **Drift Correction** for BlackHole 2ch.
4. Double-click the new device's name and call it `Call + Me`.

Anything played to `Call + Me` now reaches your ears *and* jevboard.

## 3. Point FaceTime at it

During a FaceTime call, open the **Video** menu in the menu bar:

- **Microphone:** BlackHole 16ch
- **Output:** Call + Me

If your FaceTime version doesn't show an Output choice, set **System Settings → Sound → Output**
to `Call + Me` instead. Also open **Control Center → Mic Mode** and choose **Standard**: Voice
Isolation treats sound effects as background noise and can muffle them.

## 4. Point jevboard at it

```sh
jevboard devices                       # see the exact names on your Mac
cp jevboard.example.toml jevboard.toml
```

```toml
listen_device  = "BlackHole 2ch"           # the call comes in here
output_device  = "BlackHole 16ch"          # clips + your voice go out here (FaceTime's mic)
mic_device     = "MacBook Pro Microphone"  # your real mic (or your headset's)
monitor_device = "AirPods"                 # your headphones, so you hear the clips too
```

Names are matched by fragment, case-insensitively, and you can use the number from
`jevboard devices` instead. Then check everything:

```sh
jevboard doctor          # devices, routing, keys, tools
jevboard doctor --live   # also tries the keys (one tiny Jev call)
jevboard                 # go
```

### Why your mic goes through jevboard

FaceTime takes exactly one microphone. To be on the call yourself *and* have clips in it, jevboard
mixes your mic and the clips into BlackHole 16ch (adding about 10–30 ms). Your voice also goes into
what Jev hears, so it can react to you. **Mute** in the control panel silences the clips, never you.

### Mic safety: wear headphones

With your mic passed through, the call must **not** play out of your speakers. If it does, your
mic picks the call back up and everyone hears themselves echo, and Jev hears it all twice.
Headphones (wired, AirPods, anything) fix it. `jevboard doctor` warns about the setups it can spot:
the same device for listening and output, a mic that's also the listen device, or a monitor
that looks like speakers.

## A dedicated sidekick Mac (nobody sitting at it)

A spare Mac can sit on the call as its own participant, signed into its own Apple Account:

- FaceTime **Output:** BlackHole 2ch (no Multi-Output needed: nobody's listening locally)
- FaceTime **Microphone:** BlackHole 16ch
- jevboard: `listen_device = "BlackHole 2ch"`, `output_device = "BlackHole 16ch"`, no `mic_device`

Start `jevboard` once and leave it running. Every call that Mac joins, whether you call it or
open a FaceTime link on it, gets the soundboard. Open the control panel from your phone with
`panel_host = "0.0.0.0"` and the URL jevboard prints.

## Other apps

The pattern is the same everywhere: **app output → Multi-Output (headphones + BlackHole 2ch)**
and **app microphone → BlackHole 16ch**.

| App | Where to set it |
| --- | --- |
| Discord desktop | User Settings → Voice & Video → Input Device / Output Device. For Discord, see also the [native bot](DISCORD.md). |
| Zoom | Settings → Audio → Microphone / Speaker. Turn **background noise suppression** to Low. |
| Meet, Teams, others in a browser | The browser's or the site's device picker. Turn off noise cancellation. |
| OBS / streaming | Add BlackHole 16ch as an **Audio Input Capture** source. Clips land on the stream and your mic stays as it is (no `mic_device` needed). |

## Windows and Linux

Nothing in jevboard is Mac-only, but these recipes are untested:

- **Windows:** [VB-CABLE](https://vb-audio.com/Cable/) gives you a loopback device (install two
  cables, A and B, for the in and out paths). Use "Listen to this device" in the Sound control
  panel to hear the call.
- **Linux (PulseAudio/PipeWire):** create two null sinks
  (`pactl load-module module-null-sink sink_name=jev_in` and `... sink_name=jev_out`). Listen on
  `jev_in`'s monitor source, output to `jev_out`, and pick `Monitor of jev_out` as the call
  app's microphone.

## Quick test without a call

```sh
jevboard effects --play all                  # hear the built-in sounds
jevboard try "I just tripped over my own controller" "that was a huge brag"   # Jev's picks, no audio
```

With no devices configured, jevboard listens to your default mic and plays to your default
speakers. That's good for a test across the room, but use headphones for anything longer.
