# Runs the Discord bot 24/7 (docs/DISCORD.md#run-it-247). The bot plays into the voice
# channel itself, so no audio devices are needed. Listening inside a container needs
# discord_listen = "native" (experimental) or "off" (slash-command soundboard only).
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libopus0 libportaudio2 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY jevboard ./jevboard
RUN pip install --no-cache-dir ".[discord]"

# Mount your clips at /app/clips; pass keys with --env-file .env (never bake them in).
ENV JEVBOARD_TRANSPORT=discord \
    JEVBOARD_DISCORD_LISTEN=off \
    JEVBOARD_PANEL_HOST=0.0.0.0
VOLUME ["/app/clips", "/app/state"]
EXPOSE 8787
CMD ["jevboard", "discord"]
