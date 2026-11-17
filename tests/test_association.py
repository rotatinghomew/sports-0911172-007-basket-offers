import unittest
from product.app import Application
from product.association import fisher_exact, benjamini_hochberg
from tests.fixtures import build_natural_evidence, CUTOFF, PHASES


class StatisticsTests(unittest.TestCase):
    def test_fisher_exact_known_table(self):
        # 完全确定关联的 2x2 表：p 值应极小
        p_value, odds_ratio = fisher_exact(10, 0, 0, 10)
        self.assertLess(p_value, 1e-4)
        self.assertGreater(odds_ratio, 1.0)
        # 独立表：双侧 p 值接近 1
        p_value, _ = fisher_exact(5, 5, 5, 5)
        self.assertGreater(p_value, 0.9)

    def test_benjamini_hochberg_monotone(self):
        adjusted = benjamini_hochberg([0.01, 0.02, 0.5, 0.9])
        self.assertEqual(len(adjusted), 4)
        for value in adjusted:
            self.assertGreaterEqual(value, 0.0)
            self.assertLessEqual(value, 1.0)
        self.assertLessEqual(adjusted[0], adjusted[2])


class AssociationDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.app = Application()
        build_natural_evidence(self.app)

    def tearDown(self):
        self.app.store.close()

    def discover(self, **overrides):
        arguments = dict(id='d1', cutoff=CUTOFF, phases=PHASES, min_support=2)
        arguments.update(overrides)
        return self.app.execute('discovery.run', arguments)

    def rules_by_id(self, result):
        return {rule['rule_id']: rule for rule in result['rules']}

    def test_three_way_verdicts(self):
        result = self.discover()
        rules = self.rules_by_id(result)
        self.assertEqual(rules['d1:A+B']['verdict'], 'association')
        self.assertEqual(rules['d1:C+D']['verdict'], 'promotion_induced')
        self.assertEqual(rules['d1:C+D']['candidate_source'], 'promotion')
        self.assertNotIn('d1:A+Z', rules)
        self.assertTrue(all('Z' not in rule['rule_id'] for rule in result['rules']))

    def test_holdout_is_distinct_from_discovery(self):
        result = self.discover()
        sizes = result['sample_sizes']
        self.assertGreater(sizes['holdout_purchases'], 0)
        rule = self.rules_by_id(result)['d1:A+B']
        # 持出窗口 2026-09 的 4 次共现只出现在 holdout，不进 discovery
        self.assertEqual(rule['discovery']['a'], 8)
        self.assertEqual(rule['holdout']['a'], 4)
        self.assertGreaterEqual(rule['holdout']['lift'], 1.0)

    def test_strata_cover_segments_and_phases(self):
        result = self.discover()
        rule = self.rules_by_id(result)['d1:A+B']
        self.assertIn('early', rule['strata']['phases'])
        self.assertIn('late', rule['strata']['phases'])
        for phase in rule['strata']['phases'].values():
            self.assertGreaterEqual(phase['lift'], 1.0)
            self.assertGreater(phase['a'], 0)

    def test_promotion_induced_pair_has_no_natural_evidence(self):
        result = self.discover()
        rule = self.rules_by_id(result)['d1:C+D']
        self.assertEqual(rule['discovery']['a'], 0)
        self.assertEqual(rule['holdout']['a'], 0)
        self.assertGreaterEqual(rule['promotion']['a'], 8)
        self.assertIn('promotion_cooccurrence_dominates', rule['reasons'])

    def test_min_support_filters_rare_pairs(self):
        # 自然门槛高于 A+B 共现数（8）后，自然关联不得靠低样本上榜
        result = self.discover(min_support=9)
        rules = self.rules_by_id(result)
        self.assertNotIn('d1:A+B', rules)
        # 只剩达到促销门槛的促销诱导候选，稀少对 Z 仍然排除
        self.assertIn('d1:C+D', rules)
        self.assertTrue(all('Z' not in rule['rule_id'] for rule in result['rules']))
        # 促销门槛高于 C+D 的促销共现数（8）后，没有任何候选可进入评估
        with self.assertRaises(ValueError):
            self.discover(min_support=9, min_promotion_support=9)

    def test_duplicate_discovery_id_rejected(self):
        self.discover()
        with self.assertRaises(ValueError):
            self.discover()

    def test_invalid_parameters_rejected(self):
        with self.assertRaises(ValueError):
            self.discover(min_support=1)
        with self.assertRaises(ValueError):
            self.discover(alpha=0)


if __name__ == '__main__':
    unittest.main()
