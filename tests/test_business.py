import json
import unittest
from pathlib import Path
from product.app import Application


class BusinessBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.app=Application()
        self.app.replay(json.loads((Path(__file__).parent.parent/'data'/'demo.json').read_text()))

    def tearDown(self):
        self.app.store.close()
    def test_failed_multi_product_reservation_is_atomic(self):
        before=self.app.store.snapshot()
        with self.assertRaises(ValueError):
            self.app.execute('inventory.reserve',dict(items={'shirt':1,'scarf':1000}))
        self.assertEqual(self.app.store.snapshot(),before)

    def test_redemption_keeps_promotion_source(self):
        self.assertEqual(self.app.store.get('basket','b2')['promotion'],'o1')
        self.assertEqual(self.app.store.get('basket','b2')['cents'],13000)

    def test_bundle_returns_preserve_net_receipt(self):
        self.app.execute('aftersales.refund',dict(id='r2',basket='b2',product='shirt',count=1,at='2026-10-20'))
        self.app.execute('aftersales.refund',dict(id='r3',basket='b2',product='scarf',count=1,at='2026-10-20'))
        self.assertEqual(sum(item['cents'] for item in self.app.store.all('return')),13000)
