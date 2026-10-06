"""Offline checks of the Discord transport (no network, no real token)."""

import pytest

discord = pytest.importorskip("discord")

from jevboard.config import Config  # noqa: E402
from jevboard.transports.discord_bot import FRAME, DiscordTransport, LaneSource, invite_url  # noqa: E402


def test_slash_commands_are_registered_under_the_configured_group():
    transport = DiscordTransport(Config(discord_bot_token="placeholder", discord_command="soundboard"))
    groups = [c for c in transport.bot.pending_application_commands if c.name == "soundboard"]
    assert len(groups) == 1
    names = {sub.name for sub in groups[0].subcommands}
    assert names == {"join", "leave", "on", "off", "vibe", "level", "play", "clips"}


def test_command_group_can_be_renamed():
    transport = DiscordTransport(Config(discord_bot_token="placeholder", discord_command="sfx"))
    assert [c.name for c in transport.bot.pending_application_commands] == ["sfx"]


def test_needs_a_token():
    with pytest.raises(RuntimeError):
        DiscordTransport(Config())


def test_invite_url_asks_for_voice_permissions():
    url = invite_url(1234)
    assert "client_id=1234" in url and "applications.commands" in url
    permissions = discord.Permissions(int(url.split("permissions=")[1].split("&")[0]))
    assert permissions.connect and permissions.speak and permissions.use_application_commands


def test_lane_source_emits_20ms_stereo_frames_then_ends():
    import numpy as np

    transport = DiscordTransport(Config(discord_bot_token="placeholder"))
    transport.lanes.add(np.ones(FRAME + 10, dtype=np.float32) * 0.1)
    source = LaneSource(transport)
    assert len(source.read()) == FRAME * 4
    assert len(source.read()) == FRAME * 4
    assert source.read() == b""
