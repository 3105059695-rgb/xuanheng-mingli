#!/usr/bin/env python3
"""并列两人已核生辰，逐节列年/月关系候选；不计算婚配分或婚期。"""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

import bazi

PILLARS = ('year', 'month', 'day', 'time')
OBJECTS = {'wealth': ('正财', '偏财'), 'officer-killing': ('正官', '七杀'), 'unassigned': ()}
HE = {frozenset(pair) for pair in ('子丑', '寅亥', '卯戌', '辰酉', '巳申', '午未')}
CHONG = {frozenset(pair) for pair in ('子午', '丑未', '寅申', '卯酉', '辰戌', '巳亥')}
STEM_HE = {frozenset(pair) for pair in ('甲己', '乙庚', '丙辛', '丁壬', '戊癸')}


def pair_candidates(a, b, kind='branch'):
    if a == b:
        return ['同字']
    pair = frozenset((a, b))
    if kind == 'stem':
        return ['天干五合配对'] if pair in STEM_HE else []
    return (['六合配对'] if pair in HE else []) + (['六冲配对'] if pair in CHONG else [])


def relative(day_stem, stem):
    from lunar_python.util import LunarUtil
    return LunarUtil.SHI_SHEN[day_stem + stem]


def validate_person(person):
    if not isinstance(person, dict) or not isinstance(person.get('id'), str) or not person['id'].strip():
        raise ValueError('每人须有非空 id。')
    model = person.get('object_star_model')
    if model not in OBJECTS:
        raise ValueError('每人明确 object_star_model=wealth/officer-killing/unassigned；不从 gender 推断。')
    if person.get('uncertainty_minutes') is None:
        raise ValueError('自动双盘审查需要已评估的 uncertainty_minutes；时辰未知请按专题的候选盘流程处理。')
    kwargs = {key: person[key] for key in ('solar', 'time_basis', 'day_boundary', 'uncertainty_minutes')}
    kwargs.update({key: person[key] for key in ('gender', 'yun_sect') if key in person})
    data = bazi.calculate(**kwargs, details=True)
    moment = bazi.parse_solar(person['solar'])
    delta = person['uncertainty_minutes']
    # bazi's event scan covers every intervening hour/term boundary, not just endpoints.
    crossing = [e for e in data['boundary_review']['events']
                if e['affects'] and abs((datetime.fromisoformat(e['time']) - moment).total_seconds()) <= delta * 60]
    if delta > 0 and crossing:
        raise ValueError(person['id'] + ' 的输入误差跨柱界；请分别核定候选盘，不能自动合成唯一双盘。')
    variants = []
    for offset in ((-delta, delta) if delta else ()):
        candidate = moment + timedelta(minutes=offset)
        candidate_args = {**kwargs, 'solar': candidate.isoformat(), 'uncertainty_minutes': 0}
        candidate_data = bazi.calculate(**candidate_args, details=False)
        if candidate_data['chart']['pillars'] != data['chart']['pillars']:
            raise ValueError(person['id'] + ' 的误差两端命盘不同，须分别审查。')
        variants.append({'offset_minutes': offset, 'solar': candidate.isoformat(),
                         'pillars': candidate_data['chart']['pillars'], 'yun': candidate_data.get('yun')})
    hits = []
    for pos in PILLARS:
        pillar = data['chart']['pillars'][pos]
        details = data['chart']['details'][pos]
        if details['stem_relation'] in OBJECTS[model]:
            hits.append({'position': pos, 'layer': '明透', 'stem': pillar[0], 'relation': details['stem_relation']})
        for row in details['hidden_stems']:
            if row['relation'] in OBJECTS[model]:
                hits.append({'position': pos, 'layer': '支藏', **row})
    return {'id': person['id'], 'object_star_model': model, 'calculation': data, 'birth_time_variants': variants,
            'relationship_palace': {'position': 'day', 'branch': data['chart']['pillars']['day'][1],
                                    'hidden_stems': data['chart']['details']['day']['hidden_stems']},
            'object_star_occurrences': hits}


def jie_segments(start, end, Solar):
    events = {}
    # A January probe supplies that civil year's 12 Chinese-name jie entries.
    for year in range(start.year, end.year + 1):
        table = Solar.fromYmdHms(year, 1, 1, 0, 0, 0).getLunar().getJieQiTable()
        for name, solar in table.items():
            if name not in bazi.JIE:
                continue
            stamp = datetime.fromisoformat(solar.toYmdHms()).replace(tzinfo=start.tzinfo)
            if start < stamp < end:
                events[stamp] = name
    points = [start] + sorted(events) + [end]
    return [(a, z, events.get(a, '期限开始')) for a, z in zip(points, points[1:])]


def incoming(pillar, natal, model):
    stem, branch = pillar
    dm = natal['pillars']['day'][0]
    relation = relative(dm, stem)
    matches = []
    for pos in PILLARS:
        natal_stem, natal_branch = natal['pillars'][pos]
        for kind in pair_candidates(branch, natal_branch):
            matches.append({'natal_position': pos, 'incoming_symbol': branch, 'natal_symbol': natal_branch, 'candidate': kind})
        for kind in pair_candidates(stem, natal_stem, 'stem'):
            matches.append({'natal_position': pos, 'incoming_symbol': stem, 'natal_symbol': natal_stem, 'candidate': kind})
    from lunar_python.util import LunarUtil
    hidden = [{'stem': s, 'relation': relative(dm, s), 'is_object_symbol': relative(dm, s) in OBJECTS[model]}
              for s in LunarUtil.ZHI_HIDE_GAN[branch]]
    return {'ganzhi': pillar, 'stem_relation': relation, 'stem_is_object_symbol': relation in OBJECTS[model],
            'hidden_stems': hidden, 'pair_candidates': matches}


def one_yun_review(yun, start, end):
    if yun is None:
        return {'status': 'not_supplied', 'candidates': [], 'note': '未提供排运参数；不能完成运年层的婚恋窗口取舍。'}
    first = datetime.fromisoformat(yun['start_solar'])
    if end <= first:
        return {'status': 'pre_start', 'candidates': [], 'note': '整段在首次起运前。'}
    rows = yun['dayun']
    last_year = (end - timedelta(microseconds=1)).year
    selected = {}
    boundary_years = []
    for year in range(start.year, last_year + 1):
        for i, row in enumerate(rows):
            if row['start_year_label'] <= year <= row['end_year_label']:
                selected[row['index']] = row
                if year == row['start_year_label'] and i > 0:
                    selected[rows[i-1]['index']] = rows[i-1]
                    boundary_years.append(year)
    uncertain_first = start < first < end
    missing = not selected or last_year > rows[-1]['end_year_label']
    return {'status': 'unresolved_boundary' if boundary_years or uncertain_first or missing else 'label_interior',
            'candidates': [selected[k] for k in sorted(selected)], 'later_boundary_years': sorted(set(boundary_years)),
            'first_start_in_period': first.isoformat() if uncertain_first else None,
            'note': '十年表只用于圈定候选；交运年份不能据年份标签确定交运日。候选多于一运时须两路审核或外部核定后再缩窗。'}


def yun_review(person, start, end):
    center = person['calculation'].get('yun')
    samples = [{'birth_solar': person['calculation']['input']['normalized_solar'], 'offset_minutes': 0,
                'review': one_yun_review(center, start, end)}]
    for variant in person['birth_time_variants']:
        samples.append({'birth_solar': variant['solar'], 'offset_minutes': variant['offset_minutes'],
                        'review': one_yun_review(variant['yun'], start, end)})
    candidate_rows = {}
    for sample in samples:
        for row in sample['review']['candidates']:
            candidate_rows[(row['ganzhi'], row['start_year_label'], row['end_year_label'])] = row
    statuses = {s['review']['status'] for s in samples}
    signatures = {tuple((r['ganzhi'], r['start_year_label'], r['end_year_label'])
                        for r in s['review']['candidates']) for s in samples}
    unresolved = 'unresolved_boundary' in statuses or len(statuses) > 1 or len(signatures) > 1
    return {'status': 'unresolved_boundary' if unresolved else samples[0]['review']['status'],
            'candidates': sorted(candidate_rows.values(), key=lambda r: (r['start_year_label'], r['ganzhi'])),
            'birth_time_samples': samples,
            'note': '中心及出生误差两端均重排起运并合并候选。label_interior 仅表示全部这些候选的年份标签内部一致；不表示独立核验过交运时刻。'}


def review(case):
    if not isinstance(case, dict):
        raise ValueError('输入须为 JSON 对象。')
    period = case.get('period', {})
    for field in ('start', 'end', 'success_standard'):
        if not isinstance(period.get(field), str) or not period[field].strip():
            raise ValueError('period 须包含明确 start、end 与 success_standard。')
    start, end = bazi.parse_solar(period['start']), bazi.parse_solar(period['end'])
    if not start < end or end - start > timedelta(days=732):
        raise ValueError('期限须先后有序且不超过732日；更长期限分期复核。')
    raw_people = case.get('persons')
    if not isinstance(raw_people, list) or len(raw_people) != 2:
        raise ValueError('本工具只接受两人的独立资料。')
    Solar = bazi.load_library()
    people = [validate_person(p) for p in raw_people]
    if people[0]['id'] == people[1]['id']:
        raise ValueError('两人的 id 须不同。')
    if any(bazi.parse_solar(p['solar']) >= start for p in raw_people):
        raise ValueError('审查期限须晚于两人的出生时刻。')
    a, b = [p['calculation']['chart'] for p in people]
    cross = {'kind': '现代并列观察；不是古籍合婚断法',
             'day_stems': [{'observer': people[0]['id'], 'other': people[1]['id'], 'relation': relative(a['pillars']['day'][0], b['pillars']['day'][0])},
                           {'observer': people[1]['id'], 'other': people[0]['id'], 'relation': relative(b['pillars']['day'][0], a['pillars']['day'][0])}],
             'day_branch_pair': {'symbols': [a['pillars']['day'][1], b['pillars']['day'][1]],
                                 'candidates': pair_candidates(a['pillars']['day'][1], b['pillars']['day'][1])},
             'meaning': '这是跨盘符号比较，不把对方日干当本人对象星，不把两盘合成一局或互补喜用。'}
    windows = []
    for left, right, event in jie_segments(start, end, Solar):
        lunar = Solar.fromYmdHms(left.year, left.month, left.day, left.hour, left.minute, left.second).getLunar()
        year, month = lunar.getYearInGanZhiExact(), lunar.getMonthInGanZhiExact()
        windows.append({'start_inclusive': left.isoformat(), 'end_exclusive': right.isoformat(), 'start_event': event,
                        'year_ganzhi': year, 'month_ganzhi': month,
                        'persons': [{'id': person['id'],
                                     'year': incoming(year, person['calculation']['chart'], person['object_star_model']),
                                     'month': incoming(month, person['calculation']['chart'], person['object_star_model']),
                                     'yun_review': yun_review(person, left, right)} for person in people]})
    return {'status': 'candidates_require_doctrine_review', 'engine': {'script_version': '1.0.0', 'library_version': bazi.LIBRARY_VERSION},
            'input_record': case, 'interval_convention': '[start,end)：截止时刻本身不纳入；现实成功标准如需含截止秒，先写明并相应设置 end。',
            'persons': people, 'cross_chart_observation': cross, 'period_segments': windows,
            'coverage': {'jie_year_month': '完整覆盖输入期限，保留没有宫星配对的月份；太阳节时为库计算值，未外部秒级核验。',
                         'natal_strength_and_rule_effectiveness': '须按本专题和八字内核逐人审核',
                         'yun_boundaries': '候选年审查；非各十年交运精确时刻',
                         'daily_election': '未计算逐日择吉；年/月结构变化不能推出结婚日。'},
            'not_inferred': ['适配分数', '感情忠诚', '伴侣数量', '结婚或离婚事件', '双方现实意愿', '对方补本人喜用']}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='双人资料与明确期限的 JSON 文件；格式见 references/relationships.md')
    args = parser.parse_args(argv)
    try:
        result = review(json.loads(Path(args.input).read_text(encoding='utf-8')))
    except Exception as exc:
        print(json.dumps({'status': 'error', 'error_type': type(exc).__name__, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    return 0


if __name__ == '__main__':
    from _cli import configure_output
    configure_output()
    sys.exit(main())
