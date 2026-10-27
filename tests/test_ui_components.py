import sys


def _fake_st():
    class FakeSt:
        def __init__(self):
            self.calls = []

        def success(self, msg):
            self.calls.append(("success", msg))

        def error(self, msg):
            self.calls.append(("error", msg))

        def info(self, msg):
            self.calls.append(("info", msg))

        def warning(self, msg):
            self.calls.append(("warning", msg))

        def caption(self, msg):
            self.calls.append(("caption", msg))

        def spinner(self, msg):
            class Ctx:
                def __enter__(self):
                    return None

                def __exit__(self, *a):
                    return False

            self.calls.append(("spinner", msg))
            return Ctx()

    return FakeSt()


def test_show_success_calls_streamlit(monkeypatch):
    fake = _fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.ui_components as uc

    uc.show_success("ok")
    assert fake.calls == [("success", "ok")]


def test_show_error_calls_streamlit(monkeypatch):
    fake = _fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.ui_components as uc

    uc.show_error("bad")
    assert fake.calls == [("error", "bad")]


def test_show_info_calls_streamlit(monkeypatch):
    fake = _fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.ui_components as uc

    uc.show_info("note")
    assert fake.calls == [("info", "note")]


def test_show_warning_calls_streamlit(monkeypatch):
    fake = _fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.ui_components as uc

    uc.show_warning("warn")
    assert fake.calls == [("warning", "warn")]


def test_show_empty_renders_message_and_hint(monkeypatch):
    fake = _fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.ui_components as uc

    uc.show_empty("none here", hint="do x")
    assert fake.calls == [("info", "none here"), ("caption", "do x")]


def test_show_empty_without_hint(monkeypatch):
    fake = _fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.ui_components as uc

    uc.show_empty("none here")
    assert fake.calls == [("info", "none here")]


def test_loading_context_manager(monkeypatch):
    fake = _fake_st()
    monkeypatch.setitem(sys.modules, "streamlit", fake)
    import dashboard.ui_components as uc

    with uc.loading("wait"):
        pass
    assert fake.calls == [("spinner", "wait")]
