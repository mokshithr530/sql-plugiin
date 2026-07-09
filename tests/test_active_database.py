import active_database


def test_save_get_and_clear_session_database_path(monkeypatch, tmp_path):
    sessions_dir = tmp_path / "runtime" / "sessions"
    database = tmp_path / "sample.sqlite"
    database.touch()
    monkeypatch.setattr(active_database, "SESSIONS_DIR", sessions_dir)

    active_database.save_session_database_path(
        "session-one",
        str(database),
        "sample.sqlite",
    )

    assert active_database.get_session_database_path("session-one") == str(
        database.resolve()
    )
    assert (sessions_dir / "session-one.json").exists()

    active_database.clear_session_database_path("session-one")

    assert active_database.get_session_database_path("session-one") is None
    assert not (sessions_dir / "session-one.json").exists()
