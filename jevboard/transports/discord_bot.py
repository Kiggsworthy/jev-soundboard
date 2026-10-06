"""The `discord` transport: a bot that joins a voice channel, plays clips straight into it, and
is driven by slash commands (/soundboard join, /soundboard vibe ... the group name is
configurable with JEVBOARD_DISCORD_COMMAND).

Status as of October 2026 (see docs/DISCORD.md for sources):

  * Playing into a voice channel works. Discord requires DAVE end-to-end encryption on every
    call since March 2026; Pycord 2.8 supports DAVE for sending audio.
  * Hearing the channel natively (bot voice receive) is NOT reliable under DAVE yet: Pycord
    2.8.1 itself warns that voice reception is broken and tracks the rework in issue #3139.
    So by default the bot listens through the host machine instead (discord_listen = "local":
    the Discord desktop app on the same computer, in the same channel, outputs into a loopback
    device that jevboard hears). discord_listen = "native" turns on the experimental receive
    path below; it is untested against DAVE and may hear nothing until Pycord ships the fix.

Privacy: audio is never written to disk. Speech becomes text in memory, Jev judges the last
~25 s of it, and older lines are dropped. The bot announces this every time it joins.
"""

import asyncio
import logging

import discord
import numpy as np

from ..effects import RATE
from ..pcm import ClipLanes, RoomMixer, float_to_stereo_s16, stereo_s16_to_float, to_api
from ..sidekick import TRIGGER
from . import Transport

log = logging.getLogger("jevboard.discord")

FRAME = RATE // 50  # Discord voice frames are 20 ms of 48 kHz stereo int16
PERMISSIONS = discord.Permissions(view_channel=True, send_messages=True, connect=True, speak=True,
                                  use_application_commands=True)

CONSENT = ("🔊 **Soundboard** is in **{channel}** and listening, to react with sound effects "
           "(powered by Jev). Speech is turned into text live and judged on the spot: no audio or "
           "transcripts are saved. `/{cmd} off` pauses it, `/{cmd} leave` sends it away.")
CONSENT_MANUAL = ("🔊 **Soundboard** joined **{channel}**. It isn't listening, it only plays what you ask for "
                  "with `/{cmd} play`. `/{cmd} leave` sends it away.")


def invite_url(application_id: int | str) -> str:
    return discord.utils.oauth_url(application_id, permissions=PERMISSIONS,
                                   scopes=("bot", "applications.commands"))


class LaneSource(discord.AudioSource):
    """Streams whatever clips are queued; ends (returns b"") when they've all finished."""

    def __init__(self, transport: "DiscordTransport"):
        self.transport = transport

    def read(self) -> bytes:
        lanes = self.transport.lanes
        if not lanes.active():
            return b""
        block = lanes.mix(FRAME)
        if self.transport.muted:
            block[:] = 0
        return float_to_stereo_s16(block)

    def is_opus(self) -> bool:
        return False


class RoomSink(discord.sinks.Sink):
    """Experimental native receive: every user's decoded audio goes into one RoomMixer.
    Nothing is kept: no files, no per-user recordings."""

    def __init__(self, room: RoomMixer):
        super().__init__()
        self.room = room

    def write(self, data, user):  # called on Pycord's reader thread
        pcm = getattr(data, "pcm", data)
        if pcm:
            self.room.add(getattr(user, "id", user), stereo_s16_to_float(pcm))

    def cleanup(self):
        self.room.buffers.clear()


class DiscordTransport(Transport):
    name = "discord"

    def __init__(self, config):
        super().__init__(config)
        if not config.discord_bot_token:
            raise RuntimeError("The Discord transport needs DISCORD_BOT_TOKEN (see docs/DISCORD.md).")
        self.lanes = ClipLanes()
        self.room = RoomMixer(RATE)
        self.vc: discord.VoiceClient | None = None
        self.local = None  # host-machine listening (discord_listen = "local")
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        self.bot = discord.Bot(intents=intents, debug_guilds=config.guild_ids() or None)
        self._register()

    # --- transport interface ---------------------------------------------------------

    @property
    def receives_audio(self) -> bool:
        return self.config.discord_listen != "off"

    def play(self, samples: np.ndarray) -> None:
        if self.vc is None or not self.vc.is_connected():
            return
        self.lanes.add(samples, self.config.gain)
        if not self.vc.is_playing():
            self.vc.play(LaneSource(self))

    def playing(self) -> bool:
        return self.lanes.active()

    async def run(self) -> None:
        if self.config.discord_listen == "local":
            from .local import LocalTransport

            self.local = LocalTransport(self.config, play_audio=False)
            self.local.on_audio = lambda pcm: self.on_audio(pcm)
            self.local.start()
        ticker = asyncio.create_task(self._room_ticker())
        try:
            await self.bot.start(self.config.discord_bot_token)
        except discord.LoginFailure:
            raise RuntimeError("Discord rejected DISCORD_BOT_TOKEN: reset it in the Developer Portal "
                               "and update .env (docs/DISCORD.md)") from None
        finally:
            ticker.cancel()

    async def close(self) -> None:
        if self.vc is not None and self.vc.is_connected():
            await self.vc.disconnect(force=True)
        if self.local is not None:
            await self.local.close()
        await self.bot.close()

    # --- native receive (experimental) -------------------------------------------------

    async def _room_ticker(self) -> None:
        """Every 50 ms, hand the mixed room to the transcriber."""
        frames = RATE // 20
        while True:
            await asyncio.sleep(0.05)
            if self.config.discord_listen == "native" and self.room.speakers():
                self.on_audio(to_api(self.room.drain(frames), RATE, self.config.api_rate))

    def _start_native_receive(self) -> None:
        try:
            self.vc.start_recording(RoomSink(self.room), self._receive_stopped)
            log.warning("native voice receive is experimental under DAVE; if Jev hears nothing, "
                        "use discord_listen = local (docs/DISCORD.md)")
        except Exception:  # noqa: BLE001
            log.exception("couldn't start native voice receive")

    async def _receive_stopped(self, exception=None):
        if exception:
            log.warning("native voice receive stopped: %s", exception)

    # --- slash commands ----------------------------------------------------------------

    def _register(self) -> None:
        cmd = self.config.discord_command
        group = self.bot.create_group(cmd, "Soundboard: reacts to your voice channel with sound effects")

        def board():
            return self.sidekick.board

        async def clip_names(ctx: discord.AutocompleteContext):
            typed = (ctx.value or "").lower()
            return [name for name in board().names() if typed in name.lower()][:25]

        @group.command(name="join", description="Join your voice channel and start reacting")
        async def join(ctx: discord.ApplicationContext):
            voice = getattr(ctx.author, "voice", None)
            if voice is None or voice.channel is None:
                await ctx.respond("Join a voice channel first, then run this again.", ephemeral=True)
                return
            await ctx.defer()
            channel = voice.channel
            if self.vc is not None and self.vc.is_connected():
                await self.vc.move_to(channel)
            else:
                self.vc = await channel.connect()
            if self.config.discord_listen == "native":
                self._start_native_receive()
            template = CONSENT if self.receives_audio else CONSENT_MANUAL
            await ctx.respond(template.format(channel=channel.name, cmd=cmd))
            self.sidekick.log(f"🎧 joined {channel.name}")

        @group.command(name="leave", description="Leave the voice channel")
        async def leave(ctx: discord.ApplicationContext):
            await self._leave()
            await ctx.respond("👋 Left the voice channel.")

        @group.command(name="on", description="Start reacting again")
        async def turn_on(ctx: discord.ApplicationContext):
            self.sidekick.enabled = True
            self.sidekick.log("🎛️ turned on (Discord)")
            await ctx.respond("▶️ Soundboard is on.")

        @group.command(name="off", description="Stop reacting (it stays in the channel)")
        async def turn_off(ctx: discord.ApplicationContext):
            self.sidekick.enabled = False
            self.sidekick.window.clear()
            self.sidekick.log("🎛️ turned off (Discord)")
            await ctx.respond("⏸️ Soundboard is off. Nothing is being judged until `/%s on`." % cmd)

        @group.command(name="vibe", description="Steer what it reacts to")
        @discord.option("text", str, description="e.g. only hype people up, no roasting")
        async def vibe(ctx: discord.ApplicationContext, text: str):
            self.sidekick.vibe = text.strip()[:300]
            self.sidekick.log(f"🎛️ vibe (Discord): {self.sidekick.vibe}")
            await ctx.respond(f"🎛️ Vibe set: {self.sidekick.vibe}")

        @group.command(name="level", description="How eager it is to react")
        @discord.option("level", str, choices=["chill", "normal", "trigger-happy"])
        async def level(ctx: discord.ApplicationContext, level: str):
            key = level.replace("-", "_")
            if key in TRIGGER:
                self.sidekick.trigger = key
                self.sidekick.log(f"🎛️ trigger: {key} (Discord)")
            await ctx.respond(f"🎚️ Trigger level: {level}")

        @group.command(name="play", description="Play a clip right now")
        @discord.option("clip", str, autocomplete=clip_names)
        async def play(ctx: discord.ApplicationContext, clip: str):
            if self.vc is None or not self.vc.is_connected():
                await ctx.respond(f"I'm not in a voice channel: `/{cmd} join` first.", ephemeral=True)
                return
            if self.sidekick.fire(clip, manual=True):
                await ctx.respond(f"🔊 {clip}", ephemeral=True)
            else:
                await ctx.respond(f"No clip called `{clip}`. Try `/{cmd} clips`.", ephemeral=True)

        @group.command(name="clips", description="List the sounds on the board")
        async def clips(ctx: discord.ApplicationContext):
            lines = [f"`{name}`: {desc}" for name, desc in board().menu().items()]
            text, shown = "", 0
            for line in lines:
                if len(text) + len(line) > 1900:
                    break
                text += line + "\n"
                shown += 1
            if shown < len(lines):
                text += f"…and {len(lines) - shown} more."
            await ctx.respond(text, ephemeral=True)

        @self.bot.event
        async def on_ready():
            log.info("Discord bot ready as %s. Invite link: %s", self.bot.user, invite_url(self.bot.user.id))
            log.info("In a voice channel, type /%s join", cmd)

        @self.bot.event
        async def on_voice_state_update(member, before, after):
            # Leave when everyone else has gone.
            if self.vc is None or not self.vc.is_connected() or member.id == self.bot.user.id:
                return
            if not [m for m in self.vc.channel.members if not m.bot]:
                await self._leave()

    async def _leave(self) -> None:
        if self.vc is not None and self.vc.is_connected():
            if self.vc.is_recording():
                self.vc.stop_recording()
            await self.vc.disconnect()
        self.vc = None
        self.lanes.clear()
        self.room.buffers.clear()
        if self.sidekick is not None:
            self.sidekick.window.clear()  # transcripts don't outlive the call
            self.sidekick.log("👋 left the voice channel")
