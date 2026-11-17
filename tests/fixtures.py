"""分析模块测试用的小型确定性业务夹具。

刻意覆盖拆单、赠品、整单促销、老捆绑核销、退货与稀少商品，用于辨别
自然关联、促销诱导和证据不足，不代表真实总体。

时间布局：发现窗口 2026-07 月，持出窗口 2026-09 月；发现窗口内
07-01~15 为 early 阶段、16~31 为 late 阶段。
"""

CUTOFF = '2026-07-31'
PHASES = {'early': '2026-07-15', 'late': '2026-07-31'}


def stock(app):
    for sku, cost, price in [('A', 1000, 3000), ('B', 1000, 3000),
                             ('C', 1000, 3000), ('D', 1000, 3000),
                             ('E', 5000, 9000), ('Z', 1000, 3000)]:
        app.execute('inventory.stock', dict(id=sku, count=500, cost=cost, price=price))


def close(app, basket, purchase, person, at, items, promotion=None, gifts=None):
    app.execute('baskets.close', dict(
        id=basket, purchase=purchase, person=person, at=at,
        items=items, promotion=promotion, gifts=gifts or []))


def build_natural_evidence(app):
    """A+B 为稳定自然关联；C+D 仅在促销流共现（促销诱导）；Z 仅出现一次。"""
    stock(app)
    app.execute('offers.create', dict(id='old-bundle', items=['C', 'D'],
                                      discount=500, min_margin=500))
    # A+B 自然共现 8 次，跨两个客群与两个赛程阶段
    for i in range(8):
        at = '2026-07-03' if i < 4 else '2026-07-20'
        close(app, f'ab{i}', f'pab{i}', f'u{i % 2}', at, {'A': 1, 'B': 1})
    # 只买 A / 只买 B 的对照购买
    for i in range(4):
        close(app, f'a{i}', f'pa{i}', f'u{i}', '2026-07-10', {'A': 1})
        close(app, f'b{i}', f'pb{i}', f'u{i}', '2026-07-24', {'B': 1})
    # C、D 各自独立出现，自然流从不共现
    for i in range(11):
        close(app, f'c{i}', f'pc{i}', f'w{i % 3}', '2026-07-12' if i < 6 else '2026-07-26', {'C': 1})
        close(app, f'd{i}', f'pd{i}', f'w{i % 3}', '2026-07-26' if i < 6 else '2026-07-14', {'D': 1})
    # C+D 只通过老捆绑核销出现；另加无关促销购买作为促销流背景，
    # 使 C+D 的促销提升度可被度量而非恒为 1
    for i in range(8):
        app.execute('offers.redeem', dict(id=f'cd{i}', offer='old-bundle',
                                          person=f'w{i % 3}',
                                          at='2026-07-08' if i < 4 else '2026-07-22'))
    for i in range(6):
        close(app, f'gp{i}', f'pgp{i}', f'w{i % 3}',
              '2026-07-18', {'E': 1}, promotion='gift-day')
    # 稀少商品 Z 只有一个篮子，靠偶然共现不能上榜
    close(app, 'rare1', 'prare', 'u0', '2026-07-28', {'Z': 1, 'A': 1})
    # 持出窗口：A+B 继续共现
    for i in range(4):
        close(app, f'hab{i}', f'phab{i}', f'u{i % 2}', '2026-09-01',
              {'A': 1, 'B': 1})
    close(app, 'ha1', 'pha1', 'u1', '2026-09-02', {'A': 1})
    close(app, 'hc1', 'phc1', 'w1', '2026-09-03', {'C': 1})
