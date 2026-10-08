"""Quote verification must salvage a near miss instead of costing the batch."""
import pytest

from src.core.text_utils import reconcile_quote


def test_an_exact_quote_is_kept_verbatim():
    assert reconcile_quote("力度不足", "方向对但力度不足") == "力度不足"


def test_a_padded_quote_is_trimmed_to_the_longest_genuine_part():
    assert reconcile_quote("这刀砍得好啊", "挖机这一刀砍得好") == "刀砍得好"


def test_a_hallucinated_quote_is_dropped():
    assert reconcile_quote("完全没出现过的话", "狗子现在是真废了") == ""


def test_a_quote_shorter_than_the_floor_is_dropped():
    assert reconcile_quote("改了", "完全没提到别的") == ""


def test_empty_inputs_are_safe():
    assert reconcile_quote("", "任意正文") == ""
    assert reconcile_quote("引文", "") == ""


def test_width_and_case_differences_still_match():
    assert reconcile_quote("Ｒ９９", "r99 真的超标") == "Ｒ９９"


@pytest.mark.parametrize("quote", ["等于没改", "等于没改啊"])
def test_sloppy_suffixes_do_not_lose_the_quote(quote):
    assert reconcile_quote(quote, "这改动有啥用，等于没改") == "等于没改"
