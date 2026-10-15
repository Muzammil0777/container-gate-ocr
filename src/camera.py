"""Opening CCTV streams: Hikvision NVR/camera RTSP URLs, timeouts, connectivity checks."""
import os
import socket
from urllib.parse import quote

# RTSP over TCP: UDP (OpenCV's default) drops packets on busy site networks, which shows
# up as smeared/grey frames. Must be set before the first VideoCapture is opened.
os.environ.setdefault('OPENCV_FFMPEG_CAPTURE_OPTIONS', 'rtsp_transport;tcp')

import cv2  # noqa: E402


def hikvision_url(ip, user, password, channel=1, stream='main', port=554):
    """RTSP URL for a camera on a Hikvision NVR (or a Hikvision camera itself, channel 1).
    Channel N main stream is /Streaming/Channels/N01, sub stream N02. User and password
    are URL-encoded, so passwords with @ # : / etc. work."""
    return (f"rtsp://{quote(str(user), safe='')}:{quote(str(password), safe='')}@{ip}:{port}"
            f"/Streaming/Channels/{int(channel)}{'02' if stream == 'sub' else '01'}")


def camera_source(cam, nvr=None):
    """The VideoCapture source for a camera config entry: 'source' (URL, file or webcam
    index) if given, else a Hikvision URL from its 'channel' plus 'ip'/'user'/'password'
    (taken from the camera entry, or from the shared `nvr` block)."""
    if 'source' in cam:
        s = cam['source']
        return int(s) if str(s).isdigit() else s
    conf = {**(nvr or {}), **cam}
    missing = [k for k in ('ip', 'user', 'password', 'channel') if k not in conf]
    if missing:
        raise ValueError(f"camera {cam.get('name', '?')}: missing {', '.join(missing)} "
                         f"(give 'source', or 'channel' + an 'nvr' block with ip/user/password)")
    return hikvision_url(conf['ip'], conf['user'], conf['password'], conf['channel'],
                         conf.get('stream', 'main'), conf.get('port', 554))


def open_capture(source, timeout_ms=8000):
    """VideoCapture that gives up after timeout_ms instead of hanging ~30 s on a bad URL."""
    if isinstance(source, str) and source.startswith(('rtsp://', 'http://', 'https://')):
        return cv2.VideoCapture(source, cv2.CAP_FFMPEG, [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, timeout_ms,
                                                         cv2.CAP_PROP_READ_TIMEOUT_MSEC, timeout_ms])
    return cv2.VideoCapture(source)


def port_open(ip, port, timeout=3):
    """Can this computer reach ip:port at all? (network/IP problem vs. login problem)"""
    try:
        with socket.create_connection((ip, int(port)), timeout=timeout):
            return True
    except OSError:
        return False


def redact(source):
    """Hide the password in rtsp://user:pass@host URLs when printing."""
    s = str(source)
    if '@' in s and '://' in s:
        scheme, rest = s.split('://', 1)
        return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"
    return s
