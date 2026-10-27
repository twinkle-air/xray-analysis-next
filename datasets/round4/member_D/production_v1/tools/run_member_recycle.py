import concurrent.futures
import pathlib
import sys

TOOLS = pathlib.Path(__file__).resolve().parents[1] / 'datasets' / 'round4' / 'shared' / 'production_tools'
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
