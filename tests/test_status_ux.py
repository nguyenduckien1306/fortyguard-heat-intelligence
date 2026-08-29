"""Unit and AppTest tests for task status UX and workflow states."""

from streamlit.testing.v1 import AppTest

from frontend.components.status import render_task_status


def _app_test(script, **kwargs):
    kwargs.setdefault("default_timeout", 15)
    return AppTest.from_function(script, **kwargs)


def _run_render_task_status(status, activity_id=None):
    from frontend.components.status import render_task_status

    render_task_status(status=status, activity_id=activity_id)



def test_render_task_status_ready() -> None:
    at = _app_test(_run_render_task_status, args=("Ready",))
    at.run()
    assert not at.exception
    assert any("Ready" in md.value for md in at.markdown)


def test_render_task_status_processing_with_activity_id() -> None:
    at = _app_test(
        _run_render_task_status, args=("Processing", "act-12345")
    )
    at.run()
    assert not at.exception
    assert any("Processing" in md.value for md in at.markdown)
    assert any("act-12345" in cap.value for cap in at.caption)


def test_render_task_status_completed() -> None:
    at = _app_test(
        _run_render_task_status, args=("Completed", "act-12345")
    )
    at.run()
    assert not at.exception
    assert any("Completed" in md.value for md in at.markdown)


def test_render_task_status_failed() -> None:
    at = _app_test(
        _run_render_task_status, args=("Failed", "act-12345")
    )
    at.run()
    assert not at.exception
    assert any("Failed" in md.value for md in at.markdown)


def test_render_task_status_error() -> None:
    at = _app_test(
        _run_render_task_status, args=("Error",)
    )
    at.run()
    assert not at.exception
    assert any("Error" in md.value for md in at.markdown)
