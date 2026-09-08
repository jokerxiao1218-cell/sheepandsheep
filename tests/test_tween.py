"""batch 5 测试:补间数值器(设计文档 §6.6-24)。纯函数,零 pygame。"""
import pytest

from game.core.tween import Tween, ease_out_quad, lerp


def test_lerp():
    assert lerp(0, 10, 0) == 0
    assert lerp(0, 10, 0.5) == 5
    assert lerp(0, 10, 1) == 10
    assert lerp(3, 7, 0.25) == 4


def test_ease_out_quad():
    assert ease_out_quad(0) == 0
    assert ease_out_quad(1) == 1
    assert ease_out_quad(0.5) == 0.75          # 先快后慢:中点超过一半
    assert ease_out_quad(0.25) > 0.4


def test_tween_updates_and_finishes():
    tw = Tween()
    seen = []
    tw.add(0.2, ease_out_quad, seen.append)
    assert len(tw) == 1
    tw.update(0.1)                            # 走一半
    assert seen == [0.75]                      # ease_out_quad(0.5)
    tw.update(0.15)                            # 超时走完
    assert seen[-1] == 1.0
    assert len(tw) == 0                        # 完成即移除


def test_tween_on_done_once():
    calls = []
    tw = Tween()
    tw.add(0.1, ease_out_quad, lambda v: None, on_done=lambda: calls.append(1))
    tw.update(0.2)
    assert calls == [1]
    tw.update(0.2)                             # 已移除,不再触发
    assert calls == [1]


def test_tween_rejects_bad_duration():
    tw = Tween()
    with pytest.raises(ValueError, match="正数"):
        tw.add(0, ease_out_quad, lambda v: None)
    with pytest.raises(ValueError, match="正数"):
        tw.add(-0.5, ease_out_quad, lambda v: None)
