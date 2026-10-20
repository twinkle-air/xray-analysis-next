"""Section 4 readiness check for milestone M1, without pretending M1 is closed.

M1 in the team plan is a separate milestone: A hands over 100 recipes, B generates 3 spectra per
recipe (300 new spectra), C reviews as lead and A reviews as second reader. The task card forbids
substituting A's existing P1/P2 pilots or B's own 400 section-3 pilot spectra for M1, and forbids
guessing P3/P4 as the M1 condition when A has not frozen one.

So this script does not generate a single spectrum. It proves the parts that are actually in B's
hands and are checkable offline:

* A's 100-recipe file exists, parses, and is accepted by the delivered planner
  ``dataset.make_plan`` with ``--replicates 3``;
* the planner then produces exactly 300 jobs, 100 exact-composition families and per-job seeds,
  which is what a real M1 run would seal;
* the plan is independent of the condition, so the missing input is A's frozen M1 profile, not
  pipeline readiness. The profile is still passed in because the delivered planner validates it.

Everything it writes is labelled pending, with the exact command to run once A freezes the
condition.
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent                    # datasets/B-part/work
B_DIR = HERE.parent
ROOT = B_DIR.parents[1]
GEN = ROOT / 'fp-spectrum-generator-competition-v0.2.1' / 'fp_competition'
sys.path.insert(0, str(GEN.parent))
from fp_competition.core import TARGET_ELEMENTS, Profile                   # noqa: E402
from fp_competition.dataset import make_plan, semantic_hash                 # noqa: E402

A_DIR = ROOT / 'datasets' / 'A-part-20261018'
A_SAMPLES = A_DIR / 'A_pilot_samples.json'
REPLICATES = 3
# M1 would need its own generation seed: not A's pilot seeds, not B's section 3 pilot seeds, and
# not the documented formal seeds 2026101803/2026101804.
RESERVED_SEEDS = {2026101801: 'A pilot_P1', 2026101802: 'A pilot_P2', 2026101803: 'documented formal',
                  2026101804: 'documented formal', 2026101825: 'B pilot_P3 (this task)',
                  2026101826: 'B pilot_P4 (this task)', 2026101823: 'B pilot recipe selection'}
PROPOSED_SEED = 2026101827


def sha256_bytes(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    document = json.loads(A_SAMPLES.read_text(encoding='utf-8'))
    samples = document['samples']          # the delivered CLI plans the list, not the wrapper
    ids = [s['id'] for s in samples]
    plan_out = {}
    for tag in ('P1', 'P2'):
        profile = Profile.from_dict(json.loads((A_DIR / ('%s.json' % tag)).read_text(encoding='utf-8')))
        # generate_dataset() normalizes jitter=None to {} before planning, so mirror that here
        jobs, targets, split_seed = make_plan(samples, profile, REPLICATES, PROPOSED_SEED, {},
                                              'strict', 'reject', list(TARGET_ELEMENTS), 20261018)
        plan_out[tag] = {
            'profile_sha256': sha256_bytes(A_DIR / ('%s.json' % tag)),
            'jobs': len(jobs),
            'families': len({j[4] for j in jobs}),
            'distinct_seeds': len({j[3] for j in jobs}),
            'seed_range': [min(j[3] for j in jobs), max(j[3] for j in jobs)],
            'split_counts': dict(Counter(j[5] for j in jobs)),
            'repeats_per_recipe': dict(Counter(j[1] for j in jobs)),
            'targets': len(targets), 'split_seed': split_seed,
            'profile_validated_by_delivered_planner': True}
    record = {
        'owner': 'B', 'stage': 'member B section 4, milestone M1 status',
        'status': 'M1_pending_profile',
        'what_M1_is': 'A supplies 100 recipes, B generates 3 spectra per recipe (300 new spectra), '
                      'C reviews as lead and A reviews as second reader. It is a different task from '
                      'the 100-recipe B section 3 pilot and from A own P1/P2 pilots.',
        'evidence_searched_on_disk': {
            'A_directory': str(A_DIR.relative_to(ROOT).as_posix()),
            'A_files_read': ['README.md', 'reference_production_plan.md', 'production_record.json',
                             'A_acceptance_summary.json', 'A_pilot_samples.json'],
            'A_pilot_samples_recipes': len(ids),
            'A_pilot_samples_semantic_sha256': semantic_hash(samples),
            'A_pilot_samples_sha256': sha256_bytes(A_SAMPLES),
            'A_sample_ids': ids[:3] + ['...'] + ids[-3:],
            'milestone_table_in_A_plan': 'reference_production_plan.md section 5 row M1 defines the '
                                         'work split and the 300-spectrum size, but names no profile, '
                                         'seed or output directory for M1',
            'A_production_record_statement': 'production_record.json marks A own P1/P2 pilots as '
                                             'workflow_pilot_only with '
                                             'independent_person_review=pending',
            'B_side_M1_batch_on_disk': None,
            'searched': [str(B_DIR.relative_to(ROOT).as_posix()) + ' (no m1/ directory, no '
                         'M1_300 dataset, no M1 report)']},
        'why_pending': 'No A-frozen M1 condition and no C lead-review record exist in this '
                       'workspace, so B cannot execute M1 or claim it closed. The task card forbids '
                       'guessing P3/P4 as the M1 condition, and A P1/P2 pilots plus B 400 section 3 '
                       'pilot spectra cannot substitute for it.',
        'not_guessed': {'P3_candidate.json used as M1 condition': False,
                        'P4_candidate.json used as M1 condition': False,
                        'A P1/P2 pilot spectra counted as M1': False,
                        'B section 3 pilot spectra counted as M1': False},
        'readiness_proved_by_this_script': {
            'method': 'the delivered dataset.make_plan() was called with the A 100-recipe file and '
                      '--replicates 3, exactly as a real M1 batch would, but no simulate() call and '
                      'no output directory was created',
            'plans': plan_out,
            'plan_is_condition_independent': 'jobs, families, seeds and splits are identical under '
                                             'P1 and P2 because the planner only hashes compositions '
                                             'and draws seeds; the condition choice does not affect '
                                             'whether B is ready, only what the batch would measure',
            'environment': str((B_DIR / 'B_environment.json').relative_to(ROOT).as_posix()),
            'isolated_python': json.loads((B_DIR / 'B_environment.json')
                                          .read_text(encoding='utf-8'))['python']['version']},
        'reserved_seeds_documented': RESERVED_SEEDS,
        'proposed_when_frozen': {
            'samples_file': str(A_SAMPLES.relative_to(ROOT).as_posix()),
            'replicates': REPLICATES,
            'seed': PROPOSED_SEED,
            'seed_note': 'proposed, must be confirmed by A; it collides with none of the reserved '
                         'seeds listed above',
            'split_seed': 20261018,
            'closure': 'strict', 'legacy_al': 'reject',
            'jitter': 'not passed at all; the planner then sees an empty jitter dict',
            'profile': 'TBD by A (this is the missing input)',
            'output_directory': 'datasets/B-part/M1_<condition>_v1 (fresh, never overwritten)',
            'command_template': 'cd fp-spectrum-generator-competition-v0.2.1/fp_competition && '
                                'python -B app.py batch --samples <abs A_pilot_samples.json> '
                                '--profile <abs A-frozen M1 profile> --out <abs fresh dir> '
                                '--seed %d --replicates 3 --split-seed 20261018 --closure strict '
                                '--legacy-al reject --targets %s'
                                % (PROPOSED_SEED, ' '.join(TARGET_ELEMENTS)),
            'then': 'audit (outside the sealed dir) -> full replay with the in-batch sealed app.py, '
                    'no --limit -> pack, external ZIP SHA256 and CRC check -> hand to C as lead '
                    'reviewer and A as second reviewer',
            'separate_counting': 'M1 300 spectra are named and counted apart from the B section 3 '
                                 '400 pilot spectra; neither enters the formal 20,000/50,000 budget'},
        'blockers': [
            {'item': 'A frozen M1 condition (profile file + hash)', 'owner': 'A',
             'status': 'missing in this workspace'},
            {'item': 'C lead review assignment for M1', 'owner': 'C', 'status': 'not started'},
            {'item': 'confirmation that A 100-recipe pilot file is the M1 input, or a newer A file',
             'owner': 'A', 'status': 'assumed, must be confirmed'}],
        'hashes_of_inputs_used_by_this_script': {
            'A_pilot_samples.json': sha256_bytes(A_SAMPLES),
            'A_P1.json': sha256_bytes(A_DIR / 'P1.json'),
            'A_P2.json': sha256_bytes(A_DIR / 'P2.json'),
            'local_generator_core.py': sha256_bytes(GEN / 'core.py'),
            'local_generator_dataset.py': sha256_bytes(GEN / 'dataset.py')},
        'self_check_note': 'this is a B-side readiness record produced by one operator; it is not '
                           'the C lead review or the A cross review that M1 requires'}
    out = B_DIR / 'B_M1_status.json'
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': record['status'],
                      'P1_plan': {k: plan_out['P1'][k] for k in ('jobs', 'families',
                                                                 'distinct_seeds', 'split_counts')},
                      'P2_jobs': plan_out['P2']['jobs'],
                      'identical_plans': plan_out['P1']['jobs'] == plan_out['P2']['jobs']},
                     ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
