import unittest
from product.app import Application
from product.netbaskets import build_purchases


class NetBasketTests(unittest.TestCase):
    def setUp(self):
        self.app = Application()

    def tearDown(self):
        self.app.store.close()

    def close(self, **kwargs):
        self.app.execute('baskets.close', kwargs)

    def test_split_tickets_count_as_one_purchase(self):
        self.app.execute('inventory.stock', dict(id='A', count=10, cost=1, price=10))
        self.app.execute('inventory.stock', dict(id='B', count=10, cost=1, price=10))
        self.close(id='t1', purchase='p1', person='u', at='2026-07-01', items={'A': 1})
        self.close(id='t2', purchase='p1', person='u', at='2026-07-01', items={'B': 1})
        purchases, summary = build_purchases(self.app.store)
        self.assertEqual(len(purchases), 1)
        self.assertEqual(purchases[0]['items'], ['A', 'B'])
        self.assertEqual(summary['tickets'], 2)
        self.assertEqual(summary['purchases'], 1)

    def test_gifts_are_removed_from_natural_basket(self):
        self.app.execute('inventory.stock', dict(id='A', count=10, cost=1, price=10))
        self.app.execute('inventory.stock', dict(id='G', count=10, cost=1, price=10))
        self.close(id='t1', purchase='p1', person='u', at='2026-07-01',
                   items={'A': 1, 'G': 1}, gifts=['G'])
        purchases, summary = build_purchases(self.app.store)
        self.assertEqual(purchases[0]['items'], ['A'])
        self.assertEqual(summary['gift_lines_dropped'], 1)

    def test_refunded_lines_drop_out_and_promotion_routed_separately(self):
        self.app.execute('inventory.stock', dict(id='A', count=10, cost=1, price=10))
        self.app.execute('inventory.stock', dict(id='B', count=10, cost=1, price=10))
        self.close(id='t1', purchase='p1', person='u', at='2026-07-01', items={'A': 1, 'B': 1})
        self.app.execute('aftersales.refund', dict(
            id='r1', basket='t1', product='B', count=1, at='2026-07-02'))
        self.close(id='t2', purchase='p2', person='u', at='2026-07-01',
                   items={'A': 1, 'B': 1}, promotion='gift-day')
        purchases, summary = build_purchases(self.app.store)
        streams = {row['purchase']: row for row in purchases}
        self.assertEqual(streams['p1']['items'], ['A'])
        self.assertEqual(streams['p1']['stream'], 'natural')
        self.assertEqual(streams['p2']['stream'], 'promotion')
        self.assertEqual(summary['returned_lines_dropped'], 1)
        self.assertEqual(summary['natural_purchases'], 1)
        self.assertEqual(summary['promotion_purchases'], 1)

    def test_all_gift_purchase_still_counts_in_population(self):
        self.app.execute('inventory.stock', dict(id='G', count=10, cost=1, price=10))
        self.close(id='t1', purchase='p1', person='u', at='2026-07-01',
                   items={'G': 1}, gifts=['G'])
        purchases, summary = build_purchases(self.app.store)
        self.assertEqual(purchases[0]['items'], [])
        self.assertEqual(summary['empty_natural_purchases'], 1)
        self.assertEqual(summary['natural_purchases'], 1)


if __name__ == '__main__':
    unittest.main()
