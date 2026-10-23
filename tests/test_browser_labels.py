import pytest
import security


@pytest.mark.parametrize('agent,label',[
    ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36 Edg/131.0','Edge · Windows'),
    ('Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/131.0 Safari/537.36','Chrome · Windows'),
    ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1 Version/18.0 Safari/605.1','Safari · macOS'),
    ('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) CriOS/131.0 Mobile Safari/604.1','Chrome · iOS'),
    ('Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) FxiOS/131.0 Mobile Safari/605.1','Firefox · iOS'),
    ('Mozilla/5.0 (Linux; Android 14) SamsungBrowser/27.0 Chrome/125.0 Safari/537.36','Samsung Internet · Android'),
    ('Mozilla/5.0 (X11; CrOS x86_64) Chrome/131.0 Safari/537.36','Chrome · ChromeOS'),
    ('Mozilla/5.0 (X11; Linux x86_64) Firefox/131.0','Firefox · Linux'),
    ('Mozilla/5.0 (Linux; Android 14) Chrome/131.0 Safari/537.36 OPR/80.0','Opera · Android'),
    ('unrecognized client with private details','Browser'),
    ('','Browser'),(None,'Browser'),
])
def test_browser_labels(agent,label):
    assert security.browser_label(agent)==label
