"""Export measured trial summaries as static figures; no invented accuracy data."""
import json
import os
from pathlib import Path
import statistics


def plots(root):
    root = Path(root); output = root/'report'
    cache = root/'.matplotlib'; cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault('MPLCONFIGDIR', str(cache.resolve()))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    report = json.loads((output/'summary.json').read_text())
    rows = report['trials']
    for filename in ('detection.png', 'placement.png', 'timing.png'):
        (output/filename).unlink(missing_ok=True)
    def grouped_figure(metric, filename, ylabel, title, reviewed=True, offline=False):
        groups = {}
        for row in rows:
            if reviewed and (not row['fully_reviewed'] or not row['capture_complete']): continue
            if offline and row['model']=='live_nanodet': continue
            if row[metric] is None: continue
            key = (row['object_id'],row['distance_condition'],row['view_condition'],row['motion'])
            groups.setdefault(key, {}).setdefault(row['model'], []).append(row[metric])
        if not groups: return
        keys = sorted(groups); models = sorted({m for v in groups.values() for m in v})
        fig, ax = plt.subplots(figsize=(max(9,len(keys)*1.1),5.8),layout='constrained')
        for j,model in enumerate(models):
            x=[];y=[];lo=[];hi=[]
            for i,key in enumerate(keys):
                values = groups[key].get(model,[])
                if not values:continue
                mean=statistics.mean(values);position=i+(j-(len(models)-1)/2)*.22
                x.append(position);y.append(mean);lo.append(mean-min(values));hi.append(max(values)-mean)
                ax.annotate('n='+str(len(values)),(position,mean),xytext=(0,8),textcoords='offset points',ha='center',fontsize=7)
            ax.errorbar(x,y,yerr=[lo,hi],fmt='o',capsize=3,label=model)
        labels=['\n'.join(key) for key in keys]
        ax.set_xticks(range(len(keys)),labels,fontsize=8)
        ax.set_xlim(-.5, len(keys)-.5)
        ax.set_ylabel(ylabel);ax.set_title(title+'\nPoints = mean of trial summaries; bars = trial min–max; n = trials (not frames)',fontsize=11)
        ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
        if metric=='hit_rate_iou50': ax.set_ylim(-.05,1.15)
        else: ax.set_ylim(bottom=0)
        fig.savefig(output/filename,dpi=180);plt.close(fig)
    grouped_figure('hit_rate_iou50','detection.png','Fraction of visible frames detected (IoU ≥ 0.5)','Preliminary detection • approximate positions • one physical instance per object')
    grouped_figure('median_anchor_error_pct','placement.png','Median box-anchor error (% image diagonal)','Camera-image placement proxy • conditional on an available prediction')
    grouped_figure('median_model_call_ms','timing.png','Median model call (ms)','Recorded-image CPU replay • native 416 vs 640 input • no camera/network/display',reviewed=False,offline=True)
