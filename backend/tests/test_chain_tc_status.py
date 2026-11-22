"""Chain panel: an executed test case with no result yet is "Executed",
not "Fail" (same labels as the attack graph)."""

from types import SimpleNamespace

from routers.chain_links import _ref_from_entity


def test_executed_without_result_is_not_fail():
    tc = lambda ex, ok: SimpleNamespace(id="t", title="T", category="c", is_executed=ex, is_successful=ok)  # noqa: E731
    assert [_ref_from_entity("testcase", tc(*a)).status for a in
            ((False, None), (True, None), (True, True), (True, False))] == ["Not Executed", "Executed", "Pass", "Fail"]
