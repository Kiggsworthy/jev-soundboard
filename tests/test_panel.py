import asyncio

from aiohttp.test_utils import TestClient, TestServer

from jevboard.panel import make_app


def test_panel_needs_the_token_and_controls_the_sidekick(make_sidekick):
    sidekick, transport, _, _ = make_sidekick()

    async def go():
        client = TestClient(TestServer(make_app(sidekick, "secret-token", transport)))
        await client.start_server()
        try:
            assert (await client.get("/")).status == 403
            assert (await client.get("/?t=wrong")).status == 403
            state = await (await client.get("/api/state?t=secret-token")).json()
            assert state["enabled"] and state["trigger"] == "normal" and "airhorn" in state["clips"]
            await client.post("/api/trigger?t=secret-token", data={"level": "chill"})
            await client.post("/api/vibe?t=secret-token", data={"vibe": "only hype"})
            await client.post("/api/toggle?t=secret-token")
            await client.post("/api/mute?t=secret-token")
            assert (await client.post("/api/fire?t=secret-token", data={"name": "ding"})).status == 200
            assert (await client.post("/api/fire?t=secret-token", data={"name": "nope"})).status == 404
        finally:
            await client.close()

    asyncio.run(go())
    assert sidekick.trigger == "chill"
    assert sidekick.vibe == "only hype"
    assert not sidekick.enabled
    assert transport.muted
    assert transport.played == []  # muted, so the manual "ding" was swallowed
