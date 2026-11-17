"""组合优惠小范围试用。

试用必须绑定一次关联发现（discovery）中的具体规则：商品集合即证据集合，
不允许替换商品后沿用旧证据；只有 verdict=association 的规则可以开试用，
促销诱导与无法判断的规则不具备自然偏好依据。

兑现失败（缺件、互斥、停用等）写入 unfulfilled 记录并保留原因，不扣库存、
不留半截事务。所有试用核销在 basket/redemption 上带 trial 标记，净购物篮
构建会把它们归入促销流，因此试用自己促成的共现不会回流成下一次“独立发现”。
"""

from .store import require, money
from .offers import Offers


class Trials:
    def __init__(self, store):
        self.store = store

    def create(self, id, discovery_id, rule_id, discount, min_margin,
               capacity, exclusive=True):
        """依据发现规则创建可兑现的组合优惠与试用计划。"""
        require(isinstance(capacity, int) and capacity > 0, '试用名额须为正整数')
        discovery = self.store.get('discovery', discovery_id)
        rule = self._find_rule(discovery, rule_id)
        require(rule['verdict'] == 'association',
                f'规则 {rule_id} 结论为 {rule["verdict"]}，不能作为组合试用依据')
        items = list(rule['items'])
        for sku in items:
            self.store.get('product', sku)

        offer_id = f'{id}.offer'
        Offers(self.store).create(
            offer_id, items, money(discount), money(min_margin), exclusive)
        return self.store.put('trial', id, {
            'discovery': discovery_id, 'rule_id': rule_id, 'offer': offer_id,
            'items': items, 'capacity': capacity, 'redeemed': 0,
            'unfulfilled': 0, 'state': 'active',
            'evidence_cutoff': discovery['cutoff']}, create=True)

    def attempt(self, id, trial_id, person, at, other_offer=None):
        """尝试兑现一次试用；失败留痕 unfulfilled 并返回原因码。"""
        trial = self.store.get('trial', trial_id)
        with self.store.atomic():
            reason = self._blocker(trial, other_offer)
            if reason:
                trial['unfulfilled'] += 1
                self.store.put('trial', trial_id, trial)
                return self.store.put('unfulfilled', id, {
                    'trial': trial_id, 'person': person, 'at': at,
                    'reason': reason}, create=True)
            redemption = Offers(self.store).redeem(
                id, trial['offer'], person, at,
                other_offer=other_offer, trial=trial_id)
            trial['redeemed'] += 1
            if trial['redeemed'] >= trial['capacity']:
                trial['state'] = 'capacity_reached'
            self.store.put('trial', trial_id, trial)
            return redemption

    def close(self, trial_id):
        trial = self.store.get('trial', trial_id)
        trial['state'] = 'closed'
        return self.store.put('trial', trial_id, trial)

    def report(self, trial_id):
        """汇总本次试用的净收入、退货与未兑现，并给出发现前基线对照。

        基线只统计发现截止日之前的自然流购买（同商品对），描述性对照，
        不构成增收因果结论。
        """
        trial = self.store.get('trial', trial_id)
        items = set(trial['items'])
        redemptions = [row for row in self.store.all('redemption')
                       if row.get('trial') == trial_id]
        unfulfilled = [row for row in self.store.all('unfulfilled')
                       if row.get('trial') == trial_id]

        redeemed_baskets = [self.store.get('basket', row['basket'])
                            for row in redemptions]
        gross = sum(sum(self.store.get('product', sku)['price']
                        for sku in basket['items']) for basket in redeemed_baskets)
        discount_total = gross - sum(basket['cents'] for basket in redeemed_baskets)
        returns = []
        for basket in redeemed_baskets:
            for sku, count in basket.get('returned', {}).items():
                returns.append({'basket': basket['id'], 'product': sku,
                                'count': count,
                                'cents': count * basket['unit_cents'][sku]})
        refund_total = sum(row['cents'] for row in returns)
        basket_ids = {basket['id'] for basket in redeemed_baskets}
        exchanges = [row['id'] for row in self.store.all('exchange')
                     if self._belongs(row, basket_ids)]

        cutoff = trial['evidence_cutoff']
        baseline_rows = []
        for basket in self.store.all('basket'):
            if basket['at'] > cutoff or basket.get('promotion'):
                continue
            if items <= set(basket['items']) - set(basket.get('gifts', ())):
                baseline_rows.append(basket)
        baseline_gross = sum(basket['cents'] for basket in baseline_rows)
        baseline_refunds = sum(
            count * basket['unit_cents'][sku]
            for basket in baseline_rows
            for sku, count in basket.get('returned', {}).items())

        return {
            'trial': trial_id, 'state': trial['state'],
            'capacity': trial['capacity'],
            'redeemed': len(redemptions),
            'unfulfilled_count': len(unfulfilled),
            'unfulfilled_reasons': self._reason_counts(unfulfilled),
            'gross_cents': gross,
            'discount_cents': discount_total,
            'net_cents': gross - discount_total - refund_total,
            'refund_cents': refund_total,
            'returns': returns,
            'exchanges': exchanges,
            'baseline_before_cutoff': {
                'natural_baskets': len(baseline_rows),
                'gross_cents': baseline_gross,
                'refund_cents': baseline_refunds,
                'net_cents': baseline_gross - baseline_refunds,
            },
            'note': '基线为发现前自然流描述性对照，不证明试用导致增收',
        }

    def _blocker(self, trial, other_offer):
        if trial['redeemed'] >= trial['capacity']:
            return 'capacity_exhausted'
        if trial['state'] != 'active':
            return 'trial_not_active'
        offer = self.store.get('offer', trial['offer'])
        if offer['state'] != 'active':
            return 'offer_not_active'
        if other_offer and offer['exclusive']:
            return 'offer_exclusive'
        for sku in trial['items']:
            if self.store.get('product', sku)['count'] < 1:
                return f'out_of_stock:{sku}'
        return None

    @staticmethod
    def _find_rule(discovery, rule_id):
        for rule in discovery['rules']:
            if rule['rule_id'] == rule_id:
                return rule
        raise ValueError(f'发现中不存在规则 {rule_id}')

    @staticmethod
    def _reason_counts(rows):
        counts = {}
        for row in rows:
            counts[row['reason']] = counts.get(row['reason'], 0) + 1
        return counts

    def _belongs(self, exchange, basket_ids):
        if exchange['replacement'] in basket_ids:
            return True
        source_return = self.store.get('return', exchange['returned'])
        return source_return['basket'] in basket_ids
