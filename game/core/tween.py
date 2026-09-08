"""补间数值器(设计文档 §5.2 模块 M9):lerp + easing 纯函数,零 pygame。

ui 每帧用 dt 推进 Tween,把 0..1 的插值交给回调——牌飞入槽、消除淡出的
动画全部由它驱动,帧率无关(Game Loop 模式,§3.3)。单测直接给定 t 断言值。
"""


def lerp(a, b, t):
    """线性插值:lerp(0, 10, 0.5) == 5。"""
    return a + (b - a) * t


def ease_out_quad(t):
    """先快后慢的缓动:ease(0)=0、ease(1)=1、中段 > 线性。"""
    return 1 - (1 - t) * (1 - t)


class Tween:
    """动画队列:add(duration, on_update, on_done) 后每帧 update(dt) 推进。

    on_update 收到的值是"缓动后的进度 0..1"(不是原始 t),回调自己拿它
    去算位置/透明度;on_done 在动画完成那一帧触发一次。
    """

    def __init__(self):
        self._items = []

    def add(self, duration, on_update, on_done=None, ease=ease_out_quad):
        if duration <= 0:
            raise ValueError(f"动画时长必须为正数,收到 {duration!r}")
        self._items.append({"left": duration, "dur": duration, "cb": on_update,
                            "done": on_done, "ease": ease})

    def update(self, dt):
        finished = []
        for it in self._items:
            it["left"] -= dt
            t = 1 - max(it["left"], 0.0) / it["dur"]
            it["cb"](it["ease"](min(max(t, 0.0), 1.0)))
            if it["left"] <= 0:
                finished.append(it)
        for it in finished:
            self._items.remove(it)
            if it["done"] is not None:
                it["done"]()

    def __len__(self):
        return len(self._items)
