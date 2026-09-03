"""Run the official TSC simulator with the frozen UGAT + FARP action policy."""
import argparse, os, sys, time, csv, json
from pathlib import Path
from datetime import datetime
sys.path.insert(0, '/DaRL/UGAT_Docker')
sys.path.insert(0, '/workspace/final')
import task, trainer, dataset, agent
from agent.dqn import DQNAgent as OfficialDQNAgent
from common import interface
from common.registry import Registry
from common.utils import build_config
from utils.logger import setup_logging
from ugat_frap.ugat_farp_model import UGATWithFRAP
import torch
import trainer.tsc_trainer as tsc_trainer

def _safe_passing_lane_log(trajectory, lanes, fix_time=30):
    """Fix the upstream fixed 120-bin recorder for trajectories beyond 3600 s."""
    from copy import deepcopy
    lane_template = {lane: 0 for lane in lanes}
    max_interval = max((int((route[0][1] + route[0][2] - 1) // fix_time)
                        for route in trajectory.values() if route), default=119)
    record = {i: deepcopy(lane_template) for i in range(max(120, max_interval + 1))}
    for route in trajectory.values():
        if not route: continue
        road = route[0][0]
        interval = int((route[0][1] + route[0][2] - 1) // fix_time)
        record[interval].setdefault(road, 0)
        record[interval][road] += 1
    return record

tsc_trainer.log_passing_lane_actinon = _safe_passing_lane_log

_official_test = tsc_trainer.TSCTrainer.test
def _test_with_artifacts(self, drop_load=True):
    result = _official_test(self, drop_load=drop_load)
    metric = self.metric
    row = {
        'timestamp': datetime.now().isoformat(timespec='seconds'),
        'travel_time': float(metric.real_average_travel_time()),
        'throughput': float(metric.throughput()),
        'queue': float(metric.queue()),
        'delay': float(metric.delay()),
        'rewards': float(metric.rewards()),
    }
    out = Path('/workspace/final/logs'); out.mkdir(parents=True, exist_ok=True)
    csv_path = out / 'farp_simulation_metrics.csv'
    exists = csv_path.exists()
    with csv_path.open('a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(row));
        if not exists: w.writeheader()
        w.writerow(row)
    (out / 'farp_latest_metrics.json').write_text(json.dumps(row, indent=2), encoding='utf-8')
    try:
        import matplotlib.pyplot as plt
        rows = list(csv.DictReader(csv_path.open(encoding='utf-8')))
        x = list(range(1, len(rows) + 1))
        fig, axes = plt.subplots(2, 2, figsize=(10, 7))
        for ax, key, label in zip(axes.flat, ['travel_time','throughput','queue','delay'], ['Travel Time (s)','Throughput','Queue','Delay']):
            ax.plot(x, [float(r[key]) for r in rows], marker='o'); ax.set_xlabel('run'); ax.set_ylabel(label); ax.grid(alpha=.3)
        fig.suptitle('UGAT + FARP simulation metrics'); fig.tight_layout(); fig.savefig(out / 'farp_simulation_metrics.png', dpi=160); plt.close(fig)
    except Exception as exc:
        print(f'plot_warning={exc}')
    return result
tsc_trainer.TSCTrainer.test = _test_with_artifacts

@Registry.register_model('farp')
class FARPAgent(OfficialDQNAgent):
    def __init__(self, world, rank):
        super().__init__(world, rank)
        ckpt = '/workspace/final/official_ugat_best.pt'
        self.model = UGATWithFRAP(ckpt)
        state_path = '/workspace/final/logs/farp_resume.pt'
        if os.path.exists(state_path):
            state = torch.load(state_path, map_location='cpu', weights_only=True)
            self.model.frap.load_state_dict(state['frap'])
            self.model.fusion.data.copy_(state['fusion'])
            print('loaded_farp_adapter=' + state_path)
        self.target_model = self.model
        self.optimizer = torch.optim.Adam((p for p in self.model.parameters() if p.requires_grad), lr=1e-3)

    def load_model(self, e, customized_path=''):
        # Do not overwrite the official UGAT + FARP policy with a legacy DQN file.
        print('skip_legacy_dqn_checkpoint_load=true')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--thread_num', type=int, default=4); ap.add_argument('--seed', type=int, default=4444)
    ap.add_argument('--interface', default='libsumo', choices=['libsumo','traci'])
    ap.add_argument('--delay_type', default='real', choices=['apx','real'])
    ap.add_argument('--network', default='cityflow1x1'); ap.add_argument('--world', default='cityflow', choices=['cityflow','sumo'])
    ap.add_argument('--prefix', default='farp_eval')
    a = ap.parse_args()
    argv = ['run_farp_sim.py','-t','tsc','-a','farp','-w','sumo','-n',a.network,'-d','onfly',
            '--thread_num',str(a.thread_num),'--seed',str(a.seed),'--interface',a.interface,
            '--delay_type',a.delay_type,'--prefix',a.prefix]
    old = sys.argv; sys.argv = argv
    try:
        # Importing the official runner parses its command-line arguments.
        from run import Runner
        runner = Runner(argparse.Namespace(thread_num=a.thread_num, ngpu='-1', prefix=a.prefix,
            seed=a.seed, debug=False, interface=a.interface, delay_type=a.delay_type,
            task='tsc', agent='farp', world=a.world, network=a.network, dataset='onfly'))
        runner.run()
    finally: sys.argv = old
if __name__ == '__main__': main()
