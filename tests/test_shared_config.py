import importlib


def test_get_database_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "6543")
    monkeypatch.setenv("DB_USER", "db user")
    monkeypatch.setenv("DB_PASSWORD", "s3cr@t pass")
    monkeypatch.setenv("DB_NAME", "sirep")
    monkeypatch.setenv("DB_APP_NAME", "Sirep Prod")
    monkeypatch.setenv("DB_SSL_MODE", "require")
    monkeypatch.setenv("DB_POOL_MIN", "5")
    monkeypatch.setenv("DB_POOL_MAX", "15")
    monkeypatch.setenv("DB_POOL_TIMEOUT", "45.5")

    config = importlib.import_module("shared.config")
    try:
        config.get_database_settings.cache_clear()
        settings = config.get_database_settings()
    finally:
        config.get_database_settings.cache_clear()

    assert settings.host == "db.internal"
    assert settings.port == 6543
    assert settings.user == "db user"
    assert settings.password == "s3cr@t pass"
    assert settings.database == "sirep"
    assert settings.application_name == "Sirep Prod"
    assert settings.ssl_mode == "require"
    assert settings.pool_min_size == 5
    assert settings.pool_max_size == 15
    assert settings.timeout == 45.5

    assert (
        settings.dsn
        == "postgresql://db+user:s3cr%40t+pass@db.internal:6543/sirep?sslmode=require&application_name=Sirep+Prod"
    )
