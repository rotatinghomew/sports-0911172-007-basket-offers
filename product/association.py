"""关联发现、统计检验与持出验证。

只使用标准库。发现样本与验证样本按可观察日期切分，参与发现的购买不参与
验证；检验结论分三类：

- association：自然流中通过显著性、提升度与支持度门槛，且在持出样本和
  客群/赛程阶段分层中方向稳定；
- promotion_induced：自然流证据不足，但促销流共现明显（含老捆绑、赠品
  活动），共现更可能由促销诱导，不能当作自然偏好；
- undetermined：两边都不足以判断。

稀少商品对（共现低于最小支持计数）直接排除，不会因为单个偶然篮子上榜。
本模块只描述历史关联，不产生“搭售会增收”的因果结论。
"""

from collections import Counter
from itertools import combinations
from math import comb
from .netbaskets import build_purchases
from .store import require


def fisher_exact(a, b, c, d):
    """2x2 表的 Fisher 双侧精确检验与比值比（Haldane-Anscombe 修正）。

    表布局：同时含 a、只含 A 为 b、只含 B 为 c、都不含为 d。
    """
    n = a + b + c + d
    row1, col1 = a + b, a + c
    lo = max(0, row1 + col1 - n)
    hi = min(row1, col1)

    def table_prob(x):
        return comb(row1, x) * comb(n - row1, col1 - x) / comb(n, col1)

    observed = table_prob(a)
    p_value = sum(table_prob(x) for x in range(lo, hi + 1)
                  if table_prob(x) <= observed + 1e-15)
    odds_ratio = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
    return min(1.0, p_value), odds_ratio


def benjamini_hochberg(p_values):
    """返回与输入等长的 BH FDR 调整 p 值。"""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [1.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        index = order[rank - 1]
        running = min(running, p_values[index] * m / rank)
        adjusted[index] = running
    return adjusted


def _pair_metrics(itemsets, pair):
    """在一组购买项集上计算商品对的 2x2 表与关联指标。"""
    x, y = pair
    a = b = c = d = 0
    for items in itemsets:
        has_x = x in items
        has_y = y in items
        if has_x and has_y:
            a += 1
        elif has_x:
            b += 1
        elif has_y:
            c += 1
        else:
            d += 1
    n = a + b + c + d
    support = a / n if n else 0.0
    confidence_xy = a / (a + b) if a + b else 0.0
    confidence_yx = a / (a + c) if a + c else 0.0
    lift = (a * n) / ((a + b) * (a + c)) if (a + b) and (a + c) else 0.0
    return {'pair': pair, 'n': n, 'a': a, 'b': b, 'c': c, 'd': d,
            'support': support, 'confidence_xy': confidence_xy,
            'confidence_yx': confidence_yx, 'lift': lift}


def _distinct_dates(rows):
    return sorted({row['at'] for row in rows})


def _default_cutoff(natural):
    dates = _distinct_dates(natural)
    require(len(dates) >= 2, '自然购买覆盖日期不足，无法切分发现与验证样本')
    return dates[max(1, (len(dates) - 1) * 2 // 3)]


def _segment_map(natural, segments):
    counts = Counter(row['persons'][0] for row in natural if row['persons'])
    repeat = {person for person, count in counts.items() if count > 1}
    mapping = {}
    for row in natural:
        person = row['persons'][0] if row['persons'] else None
        if segments == 'repeat':
            mapping[row['purchase']] = 'repeat' if person in repeat else 'single'
        else:
            mapping[row['purchase']] = segments.get(person, 'other')
    return mapping


class Discovery:
    def __init__(self, store):
        self.store = store

    def run(self, id, cutoff=None, phases=None, segments=None,
            min_support=5, min_lift=1.2, alpha=0.05,
            min_promotion_support=3, min_promotion_lift=1.5,
            min_stratum_n=5):
        """执行一次关联发现并持久化结论。

        cutoff 之前（含）为发现样本，之后为持出验证样本。phases 为
        {阶段名: 结束日期(含)} 的有序赛程阶段定义；segments 为
        {客群名: [person,...]}，缺省按购买次数划分回头客/单次客。
        """
        require(isinstance(min_support, int) and min_support >= 2, '最小支持计数须为不小于2的整数')
        require(alpha > 0, '显著性水平无效')
        purchases, basket_summary = build_purchases(self.store)
        natural = [row for row in purchases if row['stream'] == 'natural']
        promoted = [row for row in purchases if row['stream'] == 'promotion']
        cutoff = cutoff or _default_cutoff(natural)
        train = [row for row in natural if row['at'] <= cutoff]
        holdout = [row for row in natural if row['at'] > cutoff]
        require(train and holdout, '发现或验证样本为空')

        catalog = sorted({sku for row in train for sku in row['items']}
                         | {sku for row in promoted for sku in row['items']})
        train_itemsets = [set(row['items']) for row in train]
        holdout_itemsets = [set(row['items']) for row in holdout]
        promo_itemsets = [set(row['items']) for row in promoted]

        candidates = []
        for pair in combinations(catalog, 2):
            metrics = _pair_metrics(train_itemsets, pair)
            promo_seed = _pair_metrics(promo_itemsets, pair)
            # 自然流达到支持门槛，或仅在促销流反复共现（促销诱导候选），才进入评估
            if metrics['a'] < min_support and not (
                    promo_seed['a'] >= min_promotion_support
                    and promo_seed['lift'] >= min_promotion_lift):
                continue
            candidates.append(metrics)
        require(candidates, '没有商品对达到最小支持计数，无法发现关联')

        p_values = []
        for metrics in candidates:
            p_value, odds_ratio = fisher_exact(
                metrics['a'], metrics['b'], metrics['c'], metrics['d'])
            metrics['p_value'] = p_value
            metrics['odds_ratio'] = odds_ratio
            p_values.append(p_value)
        for metrics, adjusted in zip(candidates, benjamini_hochberg(p_values)):
            metrics['fdr_p_value'] = adjusted

        phase_bounds = self._phase_bounds(phases, natural)
        segment_map = _segment_map(natural, segments or 'repeat')
        rules = []
        for metrics in candidates:
            pair = metrics['pair']
            holdout_metrics = _pair_metrics(holdout_itemsets, pair)
            promo_metrics = _pair_metrics(promo_itemsets, pair)
            strata = self._strata_metrics(train, pair, phase_bounds, segment_map)
            verdict, reasons = self._classify(
                metrics, holdout_metrics, promo_metrics, strata,
                min_lift, alpha, min_promotion_support, min_promotion_lift,
                min_stratum_n)
            rule = {
                'rule_id': f'{id}:{pair[0]}+{pair[1]}',
                'items': list(pair),
                'verdict': verdict,
                'candidate_source': 'natural' if metrics['a'] >= min_support else 'promotion',
                'reasons': reasons,
                'discovery': self._public_metrics(metrics),
                'holdout': self._public_metrics(holdout_metrics),
                'promotion': self._public_metrics(promo_metrics),
                'strata': strata,
            }
            rules.append(rule)

        ranked = sorted(rules, key=lambda rule: (
            {'association': 0, 'promotion_induced': 1, 'undetermined': 2}[rule['verdict']],
            -rule['discovery']['lift'], -rule['discovery']['a']))
        payload = {
            'cutoff': cutoff,
            'parameters': {
                'min_support': min_support, 'min_lift': min_lift, 'alpha': alpha,
                'min_promotion_support': min_promotion_support,
                'min_promotion_lift': min_promotion_lift,
                'min_stratum_n': min_stratum_n,
                'segments': 'repeat' if not segments else 'custom',
                'phases': list(phase_bounds),
            },
            'basket_summary': basket_summary,
            'sample_sizes': {
                'train_purchases': len(train),
                'holdout_purchases': len(holdout),
                'promotion_purchases': len(promoted),
                'candidate_pairs': len(candidates),
                'tested_pairs': len(catalog) * (len(catalog) - 1) // 2,
            },
            'rules': ranked,
        }
        return self.store.put('discovery', id, payload, create=True)

    def _phase_bounds(self, phases, natural):
        if phases:
            return list(phases.items())
        dates = _distinct_dates(natural)
        if len(dates) < 2:
            return []
        middle = dates[len(dates) // 2]
        return [('early', middle), ('late', dates[-1])]

    def _strata_metrics(self, train, pair, phase_bounds, segment_map):
        result = {'segments': {}, 'phases': {}}
        by_segment = {}
        by_phase = {}
        for row in train:
            segment = segment_map.get(row['purchase'], 'other')
            by_segment.setdefault(segment, []).append(set(row['items']))
            phase = 'unphased'
            for name, end in phase_bounds:
                if row['at'] <= end:
                    phase = name
                    break
            by_phase.setdefault(phase, []).append(set(row['items']))
        for name, rows in by_segment.items():
            result['segments'][name] = self._public_metrics(_pair_metrics(rows, pair))
        for name, rows in by_phase.items():
            result['phases'][name] = self._public_metrics(_pair_metrics(rows, pair))
        return result

    def _classify(self, metrics, holdout, promo, strata,
                  min_lift, alpha, min_promo_support, min_promo_lift,
                  min_stratum_n):
        reasons = []
        natural_ok = (
            metrics['fdr_p_value'] <= alpha
            and metrics['lift'] >= min_lift
            and holdout['a'] > 0 and holdout['lift'] >= 1.0)
        if not natural_ok:
            if metrics['fdr_p_value'] > alpha:
                reasons.append('discovery_not_significant')
            if metrics['lift'] < min_lift:
                reasons.append('discovery_lift_below_threshold')
            if holdout['a'] == 0:
                reasons.append('holdout_no_cooccurrence')
            elif holdout['lift'] < 1.0:
                reasons.append('holdout_lift_below_one')

        stability = self._stability(strata, min_stratum_n)
        unstable = [name for name, value in stability.items()
                    if value['status'] == 'unstable']
        weak = [name for name, value in stability.items()
                if value['status'] == 'inconclusive']
        if unstable:
            natural_ok = False
            reasons.extend(f'stratum_{name}_unstable' for name in unstable)
        if weak:
            reasons.extend(f'stratum_{name}_thin' for name in weak)

        promo_ok = (promo['a'] >= min_promo_support and promo['lift'] >= min_promo_lift)
        if natural_ok:
            if promo_ok:
                reasons.append('natural_evidence_with_promotion_present')
            return 'association', reasons or ['natural_evidence_stable']
        if promo_ok:
            reasons.append('promotion_cooccurrence_dominates')
            return 'promotion_induced', reasons
        reasons.append('insufficient_evidence_in_either_stream')
        return 'undetermined', reasons

    def _stability(self, strata, min_stratum_n):
        """样本充足且方向一致才算稳定；层内样本不足记 inconclusive。"""
        result = {}
        for group in ('segments', 'phases'):
            for name, metrics in strata[group].items():
                key = f'{group}.{name}'
                if metrics['n'] < min_stratum_n:
                    result[key] = {'status': 'inconclusive'}
                elif metrics['a'] > 0 and metrics['lift'] >= 1.0:
                    result[key] = {'status': 'stable'}
                else:
                    result[key] = {'status': 'unstable'}
        return result

    @staticmethod
    def _public_metrics(metrics):
        return {key: metrics[key] for key in
                ('n', 'a', 'b', 'c', 'd', 'support', 'confidence_xy',
                 'confidence_yx', 'lift', 'p_value', 'odds_ratio', 'fdr_p_value')
                if key in metrics}
