import unittest
from product.app import Application
from product.netbaskets import build_purchases
from tests.fixtures import build_natural_evidence, CUTOFF, PHASES


class TrialTests(unittest.TestCase):
    def setUp(self):
        self.app = Application()
        build_natural_evidence(self.app)
        self.result = self.app.execute('discovery.run', dict(
            id='d1', cutoff=CUTOFF, phases=PHASES, min_support=2))

    def tearDown(self):
        self.app.store.close()

    def create_trial(self, **overrides):
        arguments = dict(id='t1', discovery_id='d1', rule_id='d1:A+B',
                         discount=500, min_margin=1000, capacity=3)
        arguments.update(overrides)
        return self.app.execute('trials.create', arguments)

    def test_trial_requires_association_verdict(self):
        with self.assertRaises(ValueError):
            self.app.execute('trials.create', dict(
                id='bad', discovery_id='d1', rule_id='d1:C+D',
                discount=500, min_margin=1000, capacity=3))

    def test_trial_requires_existing_rule(self):
        with self.assertRaises(ValueError):
            self.app.execute('trials.create', dict(
                id='bad', discovery_id='d1', rule_id='d1:A+E',
                discount=500, min_margin=1000, capacity=3))

    def test_margin_violation_rejected_without_partial_state(self):
        before = self.app.store.snapshot()
        with self.assertRaises(ValueError):
            self.create_trial(min_margin=10 ** 9)
        self.assertEqual(self.app.store.snapshot(), before)

    def test_redeem_fulfills_and_links_back_to_trial(self):
        self.create_trial()
        redemption = self.app.execute('trials.attempt', dict(
            id='x1', trial_id='t1', person='new1', at='2026-10-01'))
        self.assertEqual(redemption['trial'], 't1')
        basket = self.app.store.get('basket', 'x1')
        self.assertEqual(basket['promotion'], 't1.offer')
        self.assertEqual(basket['trial'], 't1')
        self.assertEqual(sorted(basket['items']), ['A', 'B'])

    def test_capacity_exhaustion_records_unfulfilled(self):
        self.create_trial(capacity=1)
        self.app.execute('trials.attempt', dict(
            id='x1', trial_id='t1', person='new1', at='2026-10-01'))
        failed = self.app.execute('trials.attempt', dict(
            id='x2', trial_id='t1', person='new2', at='2026-10-02'))
        self.assertEqual(failed['reason'], 'capacity_exhausted')
        trial = self.app.store.get('trial', 't1')
        self.assertEqual(trial['redeemed'], 1)
        self.assertEqual(trial['unfulfilled'], 1)
        # 未兑现不扣库存：失败前后库存一致
        stock_before = self.app.store.get('product', 'A')['count']
        self.app.execute('trials.attempt', dict(
            id='x2b', trial_id='t1', person='new2b', at='2026-10-02'))
        self.assertEqual(self.app.store.get('product', 'A')['count'], stock_before)

    def test_out_of_stock_is_explained_not_substituted(self):
        self.create_trial()
        # 先成功核销一次，再把 A 的余量全部预留，下一次尝试必缺件
        self.app.execute('trials.attempt', dict(
            id='x0', trial_id='t1', person='new0', at='2026-10-01'))
        remaining = self.app.store.get('product', 'A')['count']
        self.app.execute('inventory.reserve', dict(items={'A': remaining}))
        failed = self.app.execute('trials.attempt', dict(
            id='x3', trial_id='t1', person='new3', at='2026-10-03'))
        self.assertEqual(failed['reason'], 'out_of_stock:A')
        # 证据里的商品不可替换：含其它商品的优惠是独立编号，不能沿用 t1 的证据
        self.app.execute('offers.create', dict(
            id='rogue', items=['A', 'E'], discount=500, min_margin=1000))
        self.assertNotEqual(self.app.store.get('offer', 'rogue')['items'],
                            self.app.store.get('trial', 't1')['items'])

    def test_exclusive_offer_rejects_stacking(self):
        self.create_trial()
        self.app.execute('offers.create', dict(
            id='other', items=['E'], discount=100, min_margin=1000))
        failed = self.app.execute('trials.attempt', dict(
            id='x4', trial_id='t1', person='new4', at='2026-10-04',
            other_offer='other'))
        self.assertEqual(failed['reason'], 'offer_exclusive')

    def test_closed_trial_rejects_attempts(self):
        self.create_trial()
        self.app.execute('trials.close', dict(trial_id='t1'))
        failed = self.app.execute('trials.attempt', dict(
            id='x9', trial_id='t1', person='new9', at='2026-10-09'))
        self.assertEqual(failed['reason'], 'trial_not_active')

    def test_exchange_is_traced_in_report(self):
        self.create_trial(capacity=5)
        self.app.execute('trials.attempt', dict(
            id='x1', trial_id='t1', person='new1', at='2026-10-01'))
        self.app.execute('aftersales.refund', dict(
            id='rr1', basket='x1', product='A', count=1, at='2026-10-03'))
        # 同一购买者的替换小票
        self.app.execute('baskets.close', dict(
            id='x1-repl', purchase='x1-repl', person='new1', at='2026-10-04',
            items={'C': 1}))
        self.app.execute('aftersales.exchange', dict(
            id='ex1', returned='rr1', replacement='x1-repl'))
        report = self.app.execute('trials.report', dict(trial_id='t1'))
        self.assertIn('ex1', report['exchanges'])
        self.assertEqual(report['refund_cents'],
                         self.app.store.get('basket', 'x1')['unit_cents']['A'])

    def test_report_tracks_net_income_returns_and_unfulfilled(self):
        self.create_trial(capacity=5)
        self.app.execute('trials.attempt', dict(
            id='x1', trial_id='t1', person='new1', at='2026-10-01'))
        self.app.execute('trials.attempt', dict(
            id='x2', trial_id='t1', person='new2', at='2026-10-01'))
        self.app.execute('trials.attempt', dict(
            id='x3', trial_id='t1', person='new3', at='2026-10-02'))
        self.app.execute('aftersales.refund', dict(
            id='rr1', basket='x2', product='A', count=1, at='2026-10-05'))
        report = self.app.execute('trials.report', dict(trial_id='t1'))
        self.assertEqual(report['redeemed'], 3)
        self.assertEqual(report['gross_cents'], 18000)
        self.assertEqual(report['discount_cents'], 1500)
        self.assertEqual(report['refund_cents'],
                         self.app.store.get('basket', 'x2')['unit_cents']['A'])
        self.assertEqual(report['net_cents'],
                         report['gross_cents'] - report['discount_cents']
                         - report['refund_cents'])
        self.assertEqual(len(report['returns']), 1)
        self.assertIn('baseline_before_cutoff', report)

    def test_trial_cooccurrence_does_not_reenter_discovery(self):
        self.create_trial(capacity=10)
        for index in range(6):
            self.app.execute('trials.attempt', dict(
                id=f'try{index}', trial_id='t1',
                person=f'new{index}', at='2026-10-10'))
        purchases, summary = build_purchases(self.app.store)
        trial_rows = [row for row in purchases
                      if any(basket.startswith('try') for basket in row['tickets'])]
        self.assertTrue(trial_rows)
        self.assertTrue(all(row['stream'] == 'promotion' for row in trial_rows))
        # 试用后仍有新的自然购买，保证第二次发现的持出样本非空
        self.app.execute('baskets.close', dict(
            id='post1', purchase='ppost1', person='new9', at='2026-10-20',
            items={'C': 1}))
        self.app.execute('baskets.close', dict(
            id='post2', purchase='ppost2', person='u1', at='2026-10-21',
            items={'A': 1, 'B': 1}))
        # 再跑一次发现：试用核销全部进入促销流，不会抬高 A+B 的自然支持度。
        # cutoff 延至 9 月底，自然训练集因此包含原持出窗口的 4 次共现（8+4=12），
        # 但 10 月的 6 次试用共现一次都不得计入自然流。
        second = self.app.execute('discovery.run', dict(
            id='d2', cutoff='2026-09-30', phases=PHASES, min_support=2))
        rule = next(rule for rule in second['rules'] if rule['rule_id'] == 'd2:A+B')
        self.assertEqual(rule['discovery']['a'], 12)
        # 促销流的 6 次共现恰好来自本次试用，而不是被当成新的自然证据
        self.assertEqual(rule['promotion']['a'], 6)
        self.assertEqual(rule['verdict'], 'association')


if __name__ == '__main__':
    unittest.main()
