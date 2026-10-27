"""C 部分：补齐 P5_dataset_v2 的 reproducibility 工件并重新密封 integrity.json。

背景：v2 批次由 `generate_v2_batch.py` 分批续跑生成，密封时只写了
environment.json，缺 recipe.json / requirements-lock.txt / generator 源码快照 /
README_dataset.md / inputs/original_*，导致 `app.py audit` 直接报缺文件。

做法：只用生成器自己的语义补齐，不动 2000 条谱、manifest、truth、configs、
inputs/samples.json 的任何字节。
  - generator 快照：从 v1 快照复制同一份生成器源码（不含 v1 自我收录的
    P5_dataset/* 那几个文件），保证 core.py SHA-256 仍等于 v2 manifest 里的
    physics_core_sha256；
  - recipe.json：字段全部取自 v2 manifest（seed 2026110205 / split_seed 20261102 /
    replicates 2 / closure / legacy_al / targets / inputs），audit 会用它重跑
    make_plan 并比对记录数与目标元素；
  - requirements-lock.txt：用生成所用的解释器 importlib.metadata 现场枚举；
  - inputs/original_samples.json、original_profile.json：本次实际使用的
    v2 主表与 P5 条件配置的副本；
  - README_dataset.md：dataset.dataset_readme(manifest)；
  - 最后 dataset.seal(out) 重算 integrity.json（自排除 integrity.json 本身）。
"""
from __future__ import annotations
import hashlib
import json
import shutil
import sys
from pathlib import Path

FP = Path('C:/Users/TianT/Desktop/兴智杯AI/fp-spectrum-generator-competition-v0.2.1/fp_competition')
OUT = FP / 'P5_dataset_v2'
V1_SNAP = FP / 'P5_dataset' / 'reproducibility' / 'generator' / 'fp_competition'
SNAP = OUT / 'reproducibility' / 'generator' / 'fp_competition'
MASTER = Path('C:/Users/TianT/Desktop/兴智杯AI/C_part/v2/master_samples_v2.json')
PROFILE = FP / 'profiles' / 'P5.json'
LOG = Path('C:/Users/TianT/Desktop/兴智杯AI/C_part/v2_finalize.log')

sys.path.insert(0, str(FP.parent))
from fp_competition import dataset as ds      # noqa: E402


def sha256(p):
    h = hashlib.sha256()
    with Path(p).open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    lines = []
    manifest = json.loads((OUT / 'manifest.json').read_text(encoding='utf-8'))
    lines.append(f"manifest status={manifest['status']} records={len(manifest['records'])} "
                 f"seed={manifest['seed']} split_seed={manifest['split_seed']}")

    # 1) 生成器源码快照（沿用 v1 同一份，排除 v1 自我收录的 P5_dataset/* 文件）
    copied, skipped = 0, []
    for src in sorted(V1_SNAP.rglob('*')):
        if not src.is_file():
            continue
        rel = src.relative_to(V1_SNAP)
        if rel.parts[0] == 'P5_dataset':
            skipped.append(rel.as_posix())
            continue
        dst = SNAP / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        copied += 1
    core_digest = sha256(SNAP / 'core.py')
    lines.append(f'snapshot files copied={copied}, excluded v1 self-inclusions={len(skipped)}')
    lines.append(f"core.py sha256={core_digest} matches manifest="
                 f"{core_digest == manifest['physics_core_sha256']}")
    assert core_digest == manifest['physics_core_sha256'], 'generator snapshot core.py mismatch'

    # 2) 依赖锁定（与 v1 同法：当前解释器的 importlib.metadata 枚举）
    from importlib import metadata as md
    installed = sorted(f"{d.metadata['Name']}=={d.version}" for d in md.distributions()
                       if d.metadata['Name'])
    (OUT / 'reproducibility' / 'requirements-lock.txt').write_text(
        '\n'.join(installed) + '\n', encoding='utf-8')
    lines.append(f'requirements-lock.txt entries={len(installed)}')

    # 3) recipe.json —— 字段取自 manifest，audit 用它重跑 make_plan
    recipe = {'software_version': manifest['software_version'],
              'seed': manifest['seed'],
              'split_seed': manifest['split_seed'],
              'replicates': manifest['replicates'],
              'closure': manifest['closure'],
              'legacy_al': manifest['legacy_al'],
              'targets': manifest['target_elements'],
              'inputs': manifest['inputs']}
    ds.write_json(OUT / 'reproducibility' / 'recipe.json', recipe)
    lines.append('recipe.json ' + json.dumps(recipe, ensure_ascii=False, sort_keys=True)[:260])

    # 4) 原始输入副本
    shutil.copyfile(MASTER, OUT / 'inputs' / 'original_samples.json')
    shutil.copyfile(PROFILE, OUT / 'inputs' / 'original_profile.json')
    lines.append(f"original_samples sha256={sha256(MASTER)[:16]}… "
                 f"original_profile sha256={sha256(PROFILE)[:16]}…")

    # 5) 数据集自述
    (OUT / 'README_dataset.md').write_text(ds.dataset_readme(manifest), encoding='utf-8')

    # 6) 重算 integrity.json
    ds.seal(OUT)
    index = json.loads((OUT / 'integrity.json').read_text(encoding='utf-8'))
    lines.append(f"integrity files={len(index['files'])} algorithm={index['algorithm']}")

    # 自检：audit 会用到的三项前置一致性
    samples = json.loads((OUT / 'inputs' / 'samples.json').read_text(encoding='utf-8'))['samples']
    lines.append('semantic_hash matches manifest='
                 f"{ds.semantic_hash(samples) == manifest['source_samples_semantic_sha256']}")
    profile = ds.Profile.from_dict(json.loads((OUT / 'configs' / 'profile.json').read_text(encoding='utf-8')))
    jitter = json.loads((OUT / 'configs' / 'jitter.json').read_text(encoding='utf-8'))
    jobs, planned_targets, _ = ds.make_plan(samples, profile, recipe['replicates'], recipe['seed'],
                                            jitter, recipe['closure'], recipe['legacy_al'],
                                            recipe['targets'], recipe['split_seed'])
    lines.append(f'make_plan jobs={len(jobs)} records={len(manifest["records"])} '
                 f'targets_match={planned_targets == manifest["target_elements"]}')
    assert len(jobs) == len(manifest['records']) and planned_targets == manifest['target_elements']

    LOG.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
