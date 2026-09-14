from datetime import datetime
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import relationship_review as rr


def fixture():
    return {'case_id': 'synthetic-test', 'fictional': True,
            'period': {'start': '2026-09-15T00:00:00+08:00', 'end': '2027-09-15T00:00:00+08:00',
                       'success_standard': '双方自愿完成登记'},
            'persons': [dict(id='A', solar='1990-09-18T06:30:00+08:00', time_basis='utc8-standard',
                             day_boundary='00', uncertainty_minutes=10, object_star_model='wealth', gender='male', yun_sect=2),
                        dict(id='B', solar='1992-04-20T10:15:00+08:00', time_basis='utc8-standard',
                             day_boundary='00', uncertainty_minutes=10, object_star_model='officer-killing', gender='female', yun_sect=2)]}


class ReviewTests(unittest.TestCase):
    def test_known_independent_pillars_and_direction(self):
        r = rr.review(fixture())
        a, b = r['persons']
        self.assertEqual(list(a['calculation']['chart']['pillars'].values()), ['庚午', '乙酉', '丙戌', '辛卯'])
        self.assertEqual(list(b['calculation']['chart']['pillars'].values()), ['壬申', '甲辰', '丙寅', '癸巳'])
        self.assertEqual(a['calculation']['yun']['direction'], 'forward')
        self.assertEqual(b['calculation']['yun']['direction'], 'reverse')
        self.assertEqual({x['relation'] for x in a['object_star_occurrences']}, {'正财', '偏财'})
        self.assertEqual({x['relation'] for x in b['object_star_occurrences']}, {'正官', '七杀'})

    def test_interval_coverage_no_gaps_or_middle_qi(self):
        c = fixture(); r = rr.review(c); windows = r['period_segments']
        self.assertEqual(windows[0]['start_inclusive'], c['period']['start'])
        self.assertEqual(windows[-1]['end_exclusive'], c['period']['end'])
        for i, w in enumerate(windows):
            self.assertLess(w['start_inclusive'], w['end_exclusive'])
            if i:
                self.assertEqual(windows[i-1]['end_exclusive'], w['start_inclusive'])
                self.assertIn(w['start_event'], rr.bazi.JIE)
        self.assertEqual(len(windows), 13)

    def test_lichun_switches_year_and_month_at_inclusive_boundary(self):
        c = fixture(); c['period'].update(start='2027-02-04T09:46:17+08:00', end='2027-02-04T09:46:19+08:00')
        w = rr.review(c)['period_segments']
        self.assertEqual([(x['year_ganzhi'], x['month_ganzhi']) for x in w], [('丙午', '辛丑'), ('丁未', '壬寅')])
        self.assertEqual(w[1]['start_inclusive'], '2027-02-04T09:46:18+08:00')

    def test_term_at_exclusive_end_not_added(self):
        c = fixture(); c['period'].update(start='2027-02-04T09:46:17+08:00', end='2027-02-04T09:46:18+08:00')
        self.assertEqual(len(rr.review(c)['period_segments']), 1)

    def test_natal_error_endpoints_recompute_yun(self):
        a = rr.review(fixture())['persons'][0]
        variants = a['birth_time_variants']
        self.assertEqual([x['offset_minutes'] for x in variants], [-10, 10])
        self.assertNotEqual(variants[0]['yun']['start_solar'], variants[1]['yun']['start_solar'])
        self.assertEqual(variants[0]['pillars'], variants[1]['pillars'])

    def test_birth_error_can_change_yun_label_year(self):
        c = fixture(); c['persons'][0]['solar'] = '1990-02-22T14:20:00+08:00'
        c['period'].update(start='2023-08-01T00:00:00+08:00', end='2023-08-02T00:00:00+08:00')
        r = rr.review(c)
        variants = r['persons'][0]['birth_time_variants']
        self.assertEqual([v['yun']['start_solar'] for v in variants], ['1994-01-02T08:10:00+08:00', '1993-12-31T16:30:00+08:00'])
        y = r['period_segments'][0]['persons'][0]['yun_review']
        self.assertEqual(y['status'], 'unresolved_boundary')
        self.assertEqual({row['ganzhi'] for row in y['candidates']}, {'辛巳', '壬午'})

    def test_transition_year_keeps_old_and_new_yun(self):
        r = rr.review(fixture())
        w = next(w for w in r['period_segments'] if w['start_event'] == '立春')
        a, b = w['persons']
        self.assertEqual(a['yun_review']['status'], 'unresolved_boundary')
        self.assertEqual({d['ganzhi'] for d in a['yun_review']['candidates']}, {'戊子', '己丑'})
        self.assertEqual({d['ganzhi'] for d in b['yun_review']['candidates']}, {'辛丑', '庚子'})

    def test_unknown_time_and_real_boundary_require_candidates(self):
        for change in ({'uncertainty_minutes': None}, {'solar': '1990-09-18T22:55:00+08:00', 'day_boundary': '23'},
                       {'solar': '1990-09-18T23:55:00+08:00', 'day_boundary': '00'},
                       {'solar': '1990-09-18T06:55:00+08:00'}):
            c = fixture(); c['persons'][0].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                rr.review(c)

    def test_explicit_late_zi_day_boundary_keeps_its_own_relations(self):
        results = []
        for boundary in ('00', '23'):
            c = fixture(); c['persons'][0].update(solar='1990-09-18T23:30:00+08:00', day_boundary=boundary)
            a = rr.review(c)['persons'][0]
            self.assertEqual(a['calculation']['conventions']['day_boundary'], boundary)
            self.assertIn('day', a['calculation']['other_day_boundary']['different_pillars'])
            results.append(a)
        self.assertNotEqual(results[0]['calculation']['chart']['pillars']['day'], results[1]['calculation']['chart']['pillars']['day'])
        self.assertNotEqual(results[0]['object_star_occurrences'], results[1]['object_star_occurrences'])

    def test_object_mapping_is_independent_of_yun_gender(self):
        c = fixture(); c['persons'][0]['object_star_model'] = 'unassigned'
        r = rr.review(c)
        self.assertEqual(r['persons'][0]['object_star_occurrences'], [])
        self.assertEqual(r['persons'][0]['calculation']['yun']['direction'], 'forward')

    def test_missing_yun_not_silently_filled(self):
        c = fixture(); del c['persons'][0]['gender']; del c['persons'][0]['yun_sect']
        self.assertEqual(rr.review(c)['period_segments'][0]['persons'][0]['yun_review']['status'], 'not_supplied')

    def test_reject_invalid_period_and_duplicate_ids(self):
        for change in ({'end': '2026-09-14T00:00:00+08:00'}, {'start': '2026-09-15T00:00:00-04:00'},
                       {'end': '2030-09-15T00:00:00+08:00'}, {'success_standard': ''}):
            c = fixture(); c['period'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                rr.review(c)
        c = fixture(); c['persons'][1]['id'] = 'A'
        with self.assertRaises(ValueError): rr.review(c)

    def test_symbol_pairs_do_not_give_event_or_score(self):
        self.assertEqual(rr.pair_candidates('子', '丑'), ['六合配对'])
        self.assertEqual(rr.pair_candidates('子', '午'), ['六冲配对'])
        self.assertEqual(rr.pair_candidates('亥', '亥'), ['同字'])
        r = rr.review(fixture())
        self.assertNotIn('score', r)
        self.assertNotIn('marriage_date', r)
        self.assertEqual(r['status'], 'candidates_require_doctrine_review')


if __name__ == '__main__':
    unittest.main()
