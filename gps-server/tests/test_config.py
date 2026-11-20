from valkery_gps.config import GpsServerConfig


def test_from_env_defaults(monkeypatch):
    for name in (
        "VALKERY_GPS_HOST",
        "VALKERY_GPS_PORT",
        "VALKERY_GPS_IDLE_TIMEOUT_S",
        "VALKERY_GPS_HANDSHAKE_TIMEOUT_S",
        "VALKERY_GPS_MAX_CONNECTIONS",
        "VALKERY_GPS_MAX_FRAME_BYTES",
        "VALKERY_GPS_ALLOWED_IMEIS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert GpsServerConfig.from_env() == GpsServerConfig()


def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("VALKERY_GPS_PORT", "6000")
    monkeypatch.setenv("VALKERY_GPS_MAX_CONNECTIONS", "3")
    monkeypatch.setenv("VALKERY_GPS_ALLOWED_IMEIS", " 111 , 222,,")
    cfg = GpsServerConfig.from_env()
    assert cfg.port == 6000
    assert cfg.max_connections == 3
    assert cfg.allowed_imeis == frozenset({"111", "222"})
    assert isinstance(cfg.idle_timeout_s, int)
