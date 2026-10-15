import pytest

from src.camera import camera_source, hikvision_url, port_open, redact


def test_hikvision_url_encodes_credentials():
    assert hikvision_url('192.168.1.64', 'admin', 'Pa@ss#1:/', 3) == \
        'rtsp://admin:Pa%40ss%231%3A%2F@192.168.1.64:554/Streaming/Channels/301'
    assert hikvision_url('10.0.0.5', 'op', 'x', 12, stream='sub', port=8554).endswith(':8554/Streaming/Channels/1202')


def test_camera_source_from_nvr_block_or_source():
    nvr = {'ip': '192.168.1.64', 'user': 'admin', 'password': 'secret'}
    assert camera_source({'name': 'Gate', 'channel': 2}, nvr) == \
        'rtsp://admin:secret@192.168.1.64:554/Streaming/Channels/201'
    assert camera_source({'channel': 1, 'ip': '192.168.1.70'}, nvr).startswith('rtsp://admin:secret@192.168.1.70')
    assert camera_source({'source': '0'}) == 0
    assert camera_source({'source': 'videos/gate.mp4'}) == 'videos/gate.mp4'
    with pytest.raises(ValueError, match='missing password'):
        camera_source({'name': 'Gate', 'channel': 1}, {'ip': '1.2.3.4', 'user': 'admin'})


def test_redact_and_unreachable():
    assert redact('rtsp://admin:p%40ss@192.168.1.64:554/x') == 'rtsp://***@192.168.1.64:554/x'
    assert not port_open('192.0.2.1', 554, timeout=0.5)   # TEST-NET address, never routable
