"""Deterministically pick the 100 member-B pilot recipes and write the exposure ledger.

Task card section 3 requires a fixed composition of the pilot set: 40 routine, 20 sparse/boundary and
eight *complete* five-row interference families (four As/Pb plus four S/Pb), so that the pilot touches
every control level a formal family will have. The selection is reproducible from one seed and one
sorted input; nothing here depends on dictionary order or on the machine.

Why an exposure ledger: the delivered CLI splits train/validation/test purely by identical composed
percent vectors, and it has no idea about ``parent_family``. Any family whose members appear in this
pilot is therefore already developer-exposed, and the team must not later hand those families to C as
blind-test families. ``B_pilot_family_exposure.csv`` records that fact per family so the exclusion is
auditable instead of remembered.

Outputs: B_pilot_samples.json, B_pilot_family_exposure.csv, B_pilot_selection.json.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent            # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]

SEED = 2026101823                       # selection seed; NOT a generation seed
QUOTA = {'routine': 40, 'sparse_boundary': 20, 'interference': 40}
SPARSE_BLOCK_QUOTA = {'sparse_exact_zero': 7, 'sparse_low': 7,
                      'declared_maximum_spike': 3, 'boundary': 3}
INTERFERENCE_FAMILIES = {'As/Pb': 4, 'S/Pb': 4}
CONTROL_LEVELS = [(0, 0), (1, 0), (0, 1), (1, 1), (10, 1)]


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def main():
    samples = json.loads((B_DIR / 'B_samples.json').read_text(encoding='utf-8'))['samples']
    registry = list(csv.DictReader((B_DIR / 'B_formula_registry.csv').open(encoding='utf-8-sig')))
    family_of = {row['formula_id']: row['parent_family'] for row in registry}
    scenario_of = {row['formula_id']: row['scenario'] for row in registry}
    by_id = {sample['id']: sample for sample in samples}
    if set(by_id) != set(family_of):
        raise RuntimeError('registry and sample file disagree on the recipe id set')

    def draw(pool, count, key):
        """Hash-handle draw over a sorted id list, so the choice never depends on dict order."""
        if len(pool) < count:
            raise RuntimeError('block %s has only %d rows for a quota of %d' % (key, len(pool), count))
        ordered = sorted(pool)
        handles = sorted((sha256_text('%d|%s|%s' % (SEED, key, recipe_id)), recipe_id)
                         for recipe_id in ordered)
        return ordered, sorted(recipe_id for _, recipe_id in handles[:count])

    routine_pool = [s['id'] for s in samples
                    if s['provenance']['design_detail']['block'] == 'routine']
    ordered_routine, selected_routine = draw(routine_pool, QUOTA['routine'], 'routine')

    sparse_ids = []
    sparse_blocks = {}
    for block, count in SPARSE_BLOCK_QUOTA.items():
        pool = [s['id'] for s in samples if s['provenance']['design_detail']['block'] == block]
        _, chosen = draw(pool, count, block)
        sparse_blocks[block] = {'pool_size': len(pool), 'quota': count, 'chosen': chosen}
        sparse_ids += chosen

    pair_of_family = {}
    members_of_family = {}
    for sample in samples:
        detail = sample['provenance']['design_detail']
        if detail['block'] == 'interference_control':
            family = family_of[sample['id']]
            pair = '%s/%s' % tuple(detail['candidate_pair'])
            pair_of_family[family] = pair
            members_of_family.setdefault(family, []).append(sample['id'])
    incomplete = sorted(f for f, members in members_of_family.items() if len(members) != 5)
    control_mismatch = sorted(
        family for family, members in members_of_family.items()
        if sorted(tuple(by_id[m]['provenance']['design_detail']['control_multipliers'])
                  for m in members) != sorted(CONTROL_LEVELS))
    if incomplete or control_mismatch:
        raise RuntimeError('interference families are not clean 5-row control groups: '
                           'incomplete=%s control_mismatch=%s' % (incomplete, control_mismatch))

    selected_families = {}
    for pair, count in INTERFERENCE_FAMILIES.items():
        pool = sorted(f for f, p in pair_of_family.items() if p == pair)
        _, chosen = draw(pool, count, 'family:' + pair)
        # draw() sorts ids lexicographically; family ids sort correctly as strings of equal width
        selected_families[pair] = chosen

    interference_ids = sorted(m for families in selected_families.values() for family in families
                              for m in members_of_family[family])
    chosen_ids = sorted(set(selected_routine) | set(sparse_ids) | set(interference_ids))
    if len(chosen_ids) != sum(QUOTA.values()):
        raise RuntimeError('pilot set has %d ids, expected %d' % (len(chosen_ids),
                                                                  sum(QUOTA.values())))
    if any(recipe_id.startswith('A') for recipe_id in chosen_ids):
        raise RuntimeError('an A recipe leaked into the B pilot set')

    pilot = [by_id[recipe_id] for recipe_id in chosen_ids]
    pilot_text = json.dumps({'samples': pilot}, ensure_ascii=False, indent=2)
    (B_DIR / 'B_pilot_samples.json').write_text(pilot_text + '\n', encoding='utf-8', newline='\n')

    exposed_families = sorted({family_of[recipe_id] for recipe_id in chosen_ids})
    with (B_DIR / 'B_pilot_family_exposure.csv').open('w', newline='', encoding='utf-8-sig') as fh:
        writer = csv.writer(fh)
        writer.writerow(['parent_family', 'family_size_total', 'exposed_recipe_ids_in_pilot',
                         'exposed_count', 'scenario', 'selection_reason',
                         'blind_test_use_forbidden'])
        for family in exposed_families:
            members = [row['formula_id'] for row in registry if row['parent_family'] == family]
            exposed = [m for m in members if m in set(chosen_ids)]
            if family in selected_families.get('As/Pb', []) or \
               family in selected_families.get('S/Pb', []):
                reason = 'complete interference family (all five control levels)'
            elif scenario_of[exposed[0]] == 'routine':
                reason = 'routine draw'
            else:
                reason = 'sparse/boundary block draw (%s)' % \
                    by_id[exposed[0]]['provenance']['design_detail']['block']
            writer.writerow([family, len(members), ' '.join(exposed), len(exposed),
                             scenario_of[exposed[0]], reason, 'yes'])

    blocks = {}
    for recipe_id in chosen_ids:
        block = by_id[recipe_id]['provenance']['design_detail']['block']
        blocks[block] = blocks.get(block, 0) + 1
    fe = [by_id[r]['provenance']['design_detail'].get('Fe2O3T_target_percent')
          for r in chosen_ids]
    fe_used = [sum(v for k, v in by_id[r]['composition_percent'].items() if k == 'Fe')
               for r in chosen_ids]
    zero_counts = {element: sum(1 for r in chosen_ids
                                if by_id[r]['composition_percent'].get(element) == 0.0)
                   for element in ('Sb', 'W', 'Zr', 'Y')}
    low_counts = {element: sum(1 for r in chosen_ids
                               if 0.0 < (by_id[r]['composition_percent'].get(element) or 0.0) <= 0.1)
                  for element in ('Sb', 'W', 'Zr', 'Y')}

    record = {
        'stage': 'member B section 3 pilot recipe selection',
        'seed': SEED,
        'rule': {
            'routine': 'seeded handle draw (sha256("seed|routine|id")) over the sorted 900 routine ids',
            'sparse_boundary': 'independent seeded draw per construction block with the fixed quota '
                               + json.dumps(SPARSE_BLOCK_QUOTA),
            'interference': 'whole five-row families only; the four As/Pb and four S/Pb families come '
                            'from a seeded draw over the sorted family ids of each pair',
            'controls_verified': [[list(level) for level in CONTROL_LEVELS]]},
        'quota': QUOTA,
        'selected_count': len(chosen_ids),
        'scenario_counts': {scenario: sum(1 for r in chosen_ids if scenario_of[r] == scenario)
                            for scenario in ('routine', 'sparse_boundary', 'interference')},
        'block_counts': blocks,
        'sparse_block_detail': sparse_blocks,
        'interference_families': {pair: {family: sorted(members_of_family[family])
                                         for family in families}
                                  for pair, families in selected_families.items()},
        'distinct_families': len(exposed_families),
        'exposure': {
            'meaning': 'the delivered split logic separates train/validation/test only by exactly '
                       'identical composed percent vectors and ignores parent_family, so the siblings '
                       'of every recipe listed here will be silently available to whichever split '
                       'the CLI chooses. These families are developer-exposed.',
            'blind_test_forbidden': 'no parent_family listed in B_pilot_family_exposure.csv may be '
                                    'used as a blind-test family for member C, in the pilot or in any '
                                    'formal batch',
            'workflow_pilot_only': 'the 100 recipes below feed only the pilot batches; the pilot does '
                                   'not enter the formal 20,000 budget and is not training, '
                                   'validation or final-test data'},
        'spot_checks': {
            'fe2o3t_target_percent_present_in_selection': sum(1 for v in fe if v is not None),
            'iron_percent_min_max': [round(min(fe_used), 4), round(max(fe_used), 4)],
            'exact_zero_rows_for_sample_elements': zero_counts,
            'low_bin_rows_for_sample_elements': low_counts},
        'files': {
            'B_pilot_samples.json': hashlib.sha256(
                (B_DIR / 'B_pilot_samples.json').read_bytes()).hexdigest(),
            'source_B_samples.json': hashlib.sha256((B_DIR / 'B_samples.json').read_bytes()).hexdigest(),
            'source_B_formula_registry.csv': hashlib.sha256(
                (B_DIR / 'B_formula_registry.csv').read_bytes()).hexdigest()},
        'selected_ids': chosen_ids,
        'not_used': {'a_recipes': 'zero A-part recipes were read for this selection',
                    'generation_seeds': 'this seed selects recipes only; batch generation uses the '
                                         'seeds recorded in the pilot run script, which are not '
                                         'A\'s 2026101803/2026101804'}}
    (B_DIR / 'B_pilot_selection.json').write_text(json.dumps(record, ensure_ascii=False, indent=2),
                                                  encoding='utf-8')
    print(json.dumps({'selected': len(chosen_ids), 'scenarios': record['scenario_counts'],
                      'blocks': blocks, 'families': len(exposed_families),
                      'interference_families': {k: v for k, v in selected_families.items()},
                      'sha256_pilot_samples': record['files']['B_pilot_samples.json'][:16]},
                     ensure_ascii=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
