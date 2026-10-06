# Your clips

Everything in this folder except this README and `index.example.json` is git-ignored: it's
your audio, on your machine.

The board works with zero clips: 15 synthesized sounds are built in (`jevboard effects`).
To add your own, put them here and list them in `index.json`:

```json
{
  "bruh": {"file": "bruh.mp3", "desc": "a friend says something cringe or dumb"}
}
```

- `file` is relative to this folder; any format ffmpeg can read works.
- `desc` is **when to use it**. Jev matches the conversation against these descriptions, so they
  matter more than anything else. See [the clip library guide](../docs/BUILD-YOUR-CLIP-LIBRARY.md).
- A clip named like a built-in (`airhorn`) replaces it.

The easy way is `jevboard clips add`, which cuts, normalizes, screens for swearing and indexes a
clip in one step:

```sh
jevboard clips add ~/Downloads/applause.wav --start 0.4 --end 3.2 \
  --name applause --desc "someone nails an idea or wins an argument fair and square"
```

**Only use clips you have the right to use.** This repo ships no third-party audio.
