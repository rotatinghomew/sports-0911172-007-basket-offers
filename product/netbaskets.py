"""净购物篮构建。

把小票级 basket 记录还原为购买（purchase）级别的净商品集合，规则见
docs/业务约定.md：

- 同一 purchase 拆出的多张小票合并为一个购买项集，支持度按购买计一次，
  拆单不会增加任何关联的支持度；
- 赠品（gifts）不是顾客自然选择，整行剔除，赠品造成的共现不进入分析；
- 退货按数量从净篮子中扣除，净数量不大于 0 的商品剔除；换货通过其关联的
  退货单沿用同一逻辑，换入商品所在的替换小票按自身属性独立判断；
- 任一小票带 promotion（含整单折扣活动、老捆绑优惠、试用核销）的购买归入
  促销流，不得作为自然偏好证据；
- 全为赠品/退净的自然购买仍计入购买总数（作为“都未购买”的观测）。
"""

from collections import Counter


def _net_items(ticket, summary):
    returned = ticket.get('returned', {})
    gifts = set(ticket.get('gifts', ()))
    items = []
    for sku, count in ticket['items'].items():
        if sku in gifts:
            summary['gift_lines_dropped'] += 1
            continue
        remaining = count - returned.get(sku, 0)
        if remaining <= 0:
            summary['returned_lines_dropped'] += 1
            continue
        items.append(sku)
    return items


def build_purchases(store):
    """返回 (按日期排序的购买级净篮子列表, 剔除统计)。

    每行：{purchase, stream('natural'/'promotion'), at, persons, tickets, items}
    """
    summary = Counter()
    grouped = {}
    for ticket in store.all('basket'):
        summary['tickets'] += 1
        row = grouped.setdefault(ticket['purchase'], {
            'purchase': ticket['purchase'], 'tickets': [], 'persons': set(),
            'dates': [], 'promoted': False, 'items': set()})
        row['tickets'].append(ticket['id'])
        row['persons'].add(ticket['person'])
        row['dates'].append(ticket['at'])
        if ticket.get('promotion'):
            row['promoted'] = True
        row['items'].update(_net_items(ticket, summary))

    purchases = []
    for row in grouped.values():
        summary['purchases'] += 1
        stream = 'promotion' if row['promoted'] else 'natural'
        summary[f'{stream}_purchases'] += 1
        if stream == 'natural' and not row['items']:
            summary['empty_natural_purchases'] += 1
        purchases.append({
            'purchase': row['purchase'],
            'stream': stream,
            'at': min(row['dates']),
            'persons': sorted(row['persons']),
            'tickets': sorted(row['tickets']),
            'items': sorted(row['items']),
        })
    purchases.sort(key=lambda row: (row['at'], row['purchase']))
    return purchases, dict(summary)
