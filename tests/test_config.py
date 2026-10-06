import os

from jevboard.config import load_config, load_dotenv


def test_env_beats_file_beats_default(tmp_path):
    path = tmp_path / "jevboard.toml"
    path.write_text('min_gap = 6.5\nvibe = "from the file"\ntrigger = "chill"\n')
    config = load_config(path, env={"JEVBOARD_MIN_GAP": "2", "JEVBOARD_TRIGGER": "trigger-happy"})
    assert config.min_gap == 2.0
    assert config.vibe == "from the file"
    assert config.trigger == "trigger_happy"
    assert config.recent == 25


def test_keys_only_from_environment(tmp_path):
    path = tmp_path / "jevboard.toml"
    path.write_text('typesafe_api_key = "should-be-ignored"\n')
    config = load_config(path, env={"OPENAI_API_KEY": "placeholder-openai"})
    assert config.typesafe_api_key == ""
    assert config.openai_api_key == "placeholder-openai"
    assert "placeholder-openai" not in repr(config)


def test_guild_ids_parse():
    config = load_config(None, env={"JEVBOARD_DISCORD_GUILD_IDS": "123, 456,abc"})
    assert config.guild_ids() == [123, 456]


def test_dotenv_does_not_override(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nJEVBOARD_TEST_A=from-file\nexport JEVBOARD_TEST_B='quoted'\n")
    monkeypatch.setenv("JEVBOARD_TEST_A", "already-set")
    monkeypatch.delenv("JEVBOARD_TEST_B", raising=False)
    load_dotenv(env_file)
    assert os.environ["JEVBOARD_TEST_A"] == "already-set"
    assert os.environ["JEVBOARD_TEST_B"] == "quoted"
    monkeypatch.delenv("JEVBOARD_TEST_B")
