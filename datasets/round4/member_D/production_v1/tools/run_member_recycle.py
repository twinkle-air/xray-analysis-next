import concurrent.futures
import os
import pathlib
import sys


def production_tools():
    """Locate the frozen production tools relative to the real repository root.

    Resolving from parents[1] only worked while this file sat in work/; from the
    delivered production_v1/tools/ location it produced a path inside member_D.
    """
    env = os.environ.get('XRAY_PRODUCTION_TOOLS')
    if env:
        tools = pathlib.Path(env)
        if (tools / 'run_member.py').is_file():
            return tools.resolve()
        raise SystemExit(f'XRAY_PRODUCTION_TOOLS={env} has no run_member.py')

    here = pathlib.Path(__file__).resolve()
    search = [pathlib.Path.cwd(), here.parent] + list(here.parents)
    root = os.environ.get('XRAY_REPO_ROOT')
    if root:
        search.insert(0, pathlib.Path(root))

    for candidate in search:
        tools = candidate / 'datasets' / 'round4' / 'shared' / 'production_tools'
        if (tools / 'run_member.py').is_file():
            return tools.resolve()
    raise SystemExit(
        f'cannot find datasets/round4/shared/production_tools from {here}; '
        'run this wrapper inside the repository checkout, or set XRAY_REPO_ROOT / XRAY_PRODUCTION_TOOLS')


TOOLS = production_tools()
sys.path.insert(0, str(TOOLS))

_BasePool = concurrent.futures.ProcessPoolExecutor


class RecyclingPool(_BasePool):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_tasks_per_child', 2)
        super().__init__(*args, **kwargs)

    def _adjust_process_count(self):
        # Base only replaces one worker on exit, which lets fast resume tasks
        # collapse concurrency to a single worker; keep the pool at full size.
        while len(self._processes) < self._max_workers:
            self._spawn_process()


concurrent.futures.ProcessPoolExecutor = RecyclingPool

import run_member  # noqa: E402

if __name__ == '__main__':
    run_member.main()
