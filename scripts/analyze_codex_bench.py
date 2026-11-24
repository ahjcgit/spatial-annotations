#!/usr/bin/env python3
"""Summarize preserved bench trials without inventing model/optical timings."""
import argparse
import csv
import hashlib
import html
import json
import os
import statistics
from pathlib import Path
from urllib.parse import quote


def phase_resources(samples):
    """Use only adjacent samples within a phase; do not assign boundary CPU to it."""
    rows = []
    for phase in sorted({sample['phase'] for sample in samples}):
        for process in ('device', 'host'):
            selected = [s for s in samples if s['phase'] == phase and process in s]
            if not selected:
                continue
            duration = cpu = 0.0
            for previous, current in zip(samples, samples[1:]):
                if previous['phase'] != phase or current['phase'] != phase:
                    continue
                if process not in previous or process not in current:
                    continue
                delta = current[process]['cpu_seconds'] - previous[process]['cpu_seconds']
                elapsed = (current['hostMonotonicNs'] - previous['hostMonotonicNs']) / 1e9
                if delta < 0 or elapsed <= 0:
                    continue
                duration += elapsed
                cpu += delta
            rows.append({'phase': phase, 'process': process, 'sample_count': len(selected),
                         'observed_interval_s': duration, 'cpu_seconds': cpu if duration else None,
                         'mean_cpu_percent_one_core': cpu / duration * 100 if duration else None,
                         'peak_rss_mib': max(s[process]['rss_bytes'] for s in selected) / 1048576})
    return rows


def web_report(roots, out, summary, rows):
    """Portable static report; raw evidence stays beside it in the checkout."""
    escape = html.escape
    cards = []
    for root in roots:
        for folder in sorted(root.glob('trial-*')):
            def link(name):
                return quote(os.path.relpath(folder / name, out), safe='/')
            result = json.loads((folder / 'result.json').read_text()) if (folder / 'result.json').exists() else None
            failure = json.loads((folder / 'failure.json').read_text()) if (folder / 'failure.json').exists() else None
            proposal = json.loads((folder / 'codex-proposal.json').read_text()) if (folder / 'codex-proposal.json').exists() else {}
            labels = proposal.get('labels', [])
            kind = 'failed' if failure else 'bottles' if labels else 'empty'
            overlays = []
            evidence = []
            for label in labels:
                l, t, r, b = label['box']
                color = '#40e0ed' if label['identity'] == 'A' else '#ffb866'
                overlays.append(f'<rect x="{l*.48}" y="{t*.64}" width="{(r-l)*.48}" height="{(b-t)*.64}" fill="none" stroke="{color}" stroke-width="3"/><text x="{l*.48+3}" y="{max(20,t*.64-6)}" fill="{color}" stroke="#102030" paint-order="stroke" stroke-width="3" font-size="20">{escape(label["identity"])}</text>')
                evidence.append(f'<li><b>{escape(label["identity"])} · {escape(label["label"])}</b>: {escape(label["evidence"])}{ " (uncertain)" if label["uncertain"] else ""}</li>')
            visual = ''
            if (folder / 'source.jpg').exists():
                visual = f'<figure><div class="frame"><img src="{link("source.jpg")}" alt="Camera snapshot for {escape(root.name)}/{escape(folder.name)}" loading="lazy"><svg viewBox="0 0 480 640" aria-label="Approximate Codex image-space proposals">{"".join(overlays)}</svg></div><figcaption>Captured image; boxes are proposals, not verified ground truth.</figcaption></figure>'
            if (folder / 'display.png').exists():
                visual += f'<figure><img src="{link("display.png")}" alt="Android surface screenshot, both eye halves" loading="lazy"><figcaption>Android surface; does not measure optical visibility.</figcaption></figure>'
            timing = ''
            if result:
                m = result['metrics']
                timing = f'<p>Review + orchestration <b>{m["codex_assisted_review_turnaround_ms"]/1000:.2f} s</b> · response to commit observed <b>{m["host_submit_to_commit_observed_ms"]:.1f} ms</b> · device apply to commit <b>{m["device_apply_to_frame_commit_ms"]:.1f} ms</b>.</p>'
                timing += '<p>Automatic expiry recorded: <b>' + ('yes' if result['device'].get('labelsClearedNs') else 'no; hold outcome unconfirmed') + '</b>.</p>'
            downloads = ' · '.join(f'<a href="{link(name)}">{name}</a>' for name in ('source.jpg', 'capture.json', 'codex-proposal.json', 'display.png', 'result.json', 'failure.json', 'resources.jsonl') if (folder/name).exists())
            trace = escape(json.dumps(result or failure, indent=2))
            cards.append(f'<article data-kind="{kind}"><h3>{escape(root.name)} / {escape(folder.name)} <span>{kind}</span></h3>{timing}<div class="visuals">{visual}</div><p>{escape(proposal.get("reasoning_summary", "No visual review completed."))}</p><ul>{"".join(evidence)}</ul><p class="downloads">{downloads}</p><details><summary>Raw clocks, resource summary and outcome</summary><pre>{trace}</pre></details></article>')
    feedback = ''.join(f'<li><b>{escape(f["run"])}</b>: {escape(f["reported"])}</li>' for f in summary['operator_feedback'])
    table_rows = ''.join(f'<tr><td>{escape(r["run"])} / {escape(r["trial"])}</td><td>{r["labels"]}</td><td>{r["host_capture_to_commit_observed_ms"]/1000:.2f}</td><td>{r["codex_assisted_review_turnaround_ms"]/1000:.2f}</td><td>{r["host_submit_to_commit_observed_ms"]:.1f}</td><td>{r["device_apply_to_frame_commit_ms"]:.1f}</td></tr>' for r in rows)
    document = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Codex → glasses · measured pilot</title>
<style>
:root{font:16px/1.55 system-ui,sans-serif;color:#e5eef5;background:#101923;color-scheme:dark}body{max-width:1200px;margin:auto;padding:28px}a{color:#73dfef}h1{font-size:clamp(2rem,5vw,3.5rem);line-height:1.1}h2{margin-top:2.5rem}p{max-width:90ch}.muted,figcaption{color:#afc0cf}article{background:#192735;border:1px solid #365066;padding:22px;margin:22px 0;border-radius:12px}h3{margin-top:0}h3 span{font-size:.9rem;font-weight:normal;color:#a5e1da;margin-left:12px}.visuals{display:grid;grid-template-columns:minmax(200px,360px) 1fr;gap:24px;align-items:center}figure{margin:0}img{display:block;width:100%;height:auto;border-radius:6px}.frame{position:relative}.frame svg{position:absolute;inset:0;width:100%;height:100%}figcaption{font-size:.9rem;margin-top:8px}pre{overflow:auto;max-height:420px;font-size:.875rem;background:#101923;padding:16px}summary{cursor:pointer;padding:10px 0}.table-wrap{overflow:auto}table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid #365066;padding:10px}th{font-size:.9rem}select{font:inherit;padding:8px;margin-left:10px}.downloads{overflow-wrap:anywhere;font-size:.9rem}[hidden]{display:none!important}@media(max-width:700px){body{padding:16px}.visuals{grid-template-columns:1fr}article{padding:15px}}
</style><main><p class="muted">RAYNEO X3 PRO · 19 NOVEMBER 2026 · REPRODUCIBLE PILOT</p><h1>Codex review to glasses</h1>'''
    document += f'<p><b>{summary["completed_trials"]} completed timing trials · {summary["failed_trials"]} retained failed attempts.</b> Each run records its A/B enrollment names in run-metadata.json. This is a small technical pilot, not an accuracy benchmark.</p>'
    document += '<p>Direct camera snapshot → SHA-256 bound Codex conversational review → structured labels via USB ADB → Android frame-commit acknowledgement. Host and device clocks are analyzed separately. The labels are a fixed list with snapshot side cues, not physically aligned boxes.</p><p><b>Isolated model inference, optical latency and remote compute were not measured.</b> Review time includes image tools and orchestration. No-bottle scenes are separate negative cases. Completed means a matching software commit, not confirmed readability or automatic expiry.</p><p><a href="trials.csv">Trial CSV</a> · <a href="phase-resources.csv">Resources by phase</a> · <a href="summary.json">Summary JSON</a> · <a href="../README.md">Methodology and limitations</a> · <a href="../manifest.json">Evidence hashes</a></p>'
    document += '<h2>Observed timing</h2><img src="timing.svg" alt="Stacked capture, Codex review, delivery timings and device apply-to-commit per trial"><div class="table-wrap"><table><thead><tr><th>Run / trial</th><th>Labels</th><th>End-to-end s</th><th>Review + tools s</th><th>Delivery ms</th><th>Device commit ms</th></tr></thead><tbody>' + table_rows + '</tbody></table></div>'
    document += '<h2>Wearer feedback</h2><ul>' + feedback + '</ul><h2>Frames and traces</h2><label>Show <select id="filter"><option value="all">All attempts</option><option value="bottles">Bottle labels</option><option value="empty">No-label cases</option><option value="failed">Failures</option></select></label>' + ''.join(cards)
    document += '</main><script>document.getElementById("filter").addEventListener("change",e=>{document.querySelectorAll("article[data-kind]").forEach(a=>a.hidden=e.target.value!=="all"&&a.dataset.kind!==e.target.value)})</script></html>'
    (out / 'index.html').write_text(document)


def analyze(roots, out):
    out.mkdir(parents=True,exist_ok=True)
    rows=[];failures=[];feedback=[];phase_rows=[]
    for root in roots:
        metadata=json.loads((root/'run-metadata.json').read_text())
        variant=metadata['display'].get('variant','small_text_10s')
        if (root/'operator-feedback.json').exists():
            feedback.append({'run':root.name,**json.loads((root/'operator-feedback.json').read_text())})
        for folder in sorted(root.glob('trial-*')):
            if (folder/'failure.json').exists():
                failures.append({'run':root.name,'trial':folder.name,**json.loads((folder/'failure.json').read_text())})
            if not (folder/'result.json').exists():continue
            result=json.loads((folder/'result.json').read_text())
            proposal=json.loads((folder/'codex-proposal.json').read_text())
            assert hashlib.sha256((folder/'source.jpg').read_bytes()).hexdigest()==proposal['sourceSha256'],folder
            assert result['requestId']==proposal['requestId']==result['device']['requestId'],folder
            assert result['device']['sourceSha256']==proposal['sourceSha256'],folder
            m=result['metrics']
            assert m['isolated_model_inference_ms'] is None and m['optical_display_latency_ms'] is None
            total=m['host_capture_to_image_ready_ms']+m['codex_assisted_review_turnaround_ms']+m['host_submit_to_commit_observed_ms']
            assert abs(total-m['host_capture_to_commit_observed_ms'])<.01, 'Host timing stages do not add up'
            condition='two_bottle_proposals' if len(proposal['labels'])==2 else 'no_label_proposal' if not proposal['labels'] else 'one_bottle_proposal'
            row={'run':root.name,'variant':variant,'trial':folder.name,'condition':condition,'labels':len(proposal['labels']),
                 'uncertain_labels':sum(x['uncertain'] for x in proposal['labels']),**m,
                 **result['transfer_bytes'],
                 'device_peak_rss_mib':result['resource_summary'].get('device',{}).get('peak_rss_mib'),
                 'host_peak_rss_mib':result['resource_summary'].get('host',{}).get('peak_rss_mib'),
                 'device_cpu_seconds':result['resource_summary'].get('device',{}).get('cpu_seconds_delta'),
                 'device_mean_cpu_percent_one_core':result['resource_summary'].get('device',{}).get('mean_cpu_percent_one_core'),
                 'host_cpu_seconds':result['resource_summary'].get('host',{}).get('cpu_seconds_delta'),
                 'host_child_cpu_seconds':result['resource_summary'].get('host',{}).get('child_cpu_seconds_delta'),
                 'device_auto_expiry_recorded':bool(result['device'].get('labelsClearedNs')),
                 'frame_commit_recorded':bool(result['device'].get('frameCommittedNs'))}
            rows.append(row)
            samples=[json.loads(line) for line in (folder/'resources.jsonl').read_text().splitlines() if line.strip()]
            phase_rows.extend({'run':root.name,'trial':folder.name,'variant':variant,'condition':condition,**r} for r in phase_resources(samples))
    numeric=[k for k,v in rows[0].items() if isinstance(v,(float,int)) and not isinstance(v,bool)] if rows else []
    groups={}
    for variant in sorted({r['variant'] for r in rows}):
        selected=[r for r in rows if r['variant']==variant]
        stats={}
        for metric in numeric:
            values=[r[metric] for r in selected if r[metric] is not None]
            if values:stats[metric]={'n':len(values),'median':statistics.median(values),'min':min(values),'max':max(values),'p95':None if len(values)<20 else statistics.quantiles(values,n=100,method='inclusive')[94]}
        groups[variant]={'completed_trials':len(selected),'two_label_trials':sum(r['labels']==2 for r in selected),'no_label_trials':sum(r['labels']==0 for r in selected),'metrics':stats}
    conditions={}
    for variant,condition in sorted({(r['variant'],r['condition']) for r in rows}):
        selected=[r for r in rows if r['variant']==variant and r['condition']==condition]
        stats={}
        for metric in numeric:
            values=[r[metric] for r in selected if r[metric] is not None]
            if values:stats[metric]={'n':len(values),'median':statistics.median(values),'min':min(values),'max':max(values)}
        conditions[variant+'/'+condition]={'completed_trials':len(selected),'metrics':stats}
    summary={'completed_trials':len(rows),'failed_trials':len(failures),'variants':groups,'failures':failures,'operator_feedback':feedback,
        'conditions':conditions,
        'isolated_model_inference_ms':None,'remote_model_compute':None,'optical_display_latency_ms':None,
        'interpretation':'Descriptive technical pilot. Codex-assisted turnaround includes image tools and orchestration. Device commit is not optical visibility. Variants and no-label cases are not independent randomized comparisons. No inference speed, general recognition accuracy or spatial alignment claim.',
        'p95_policy':'Withheld for fewer than 20 observations per variant; min/median/max are descriptive only.',
        'resource_scope':'Sampled app/Python process CPU and RSS, not whole-machine load, remote model memory, GPU energy or battery power. Display-hold intervals lower whole-trial average CPU. Initial capture may precede the first app sample.'}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    if phase_rows:
        with (out/'phase-resources.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(phase_rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(phase_rows)
    if rows:
        with (out/'trials.csv').open('w',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');writer.writeheader();writer.writerows(rows)
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        labels=[r['variant'].replace('_',' ')+' / '+r['trial']+(' (empty)' if r['labels']==0 else '') for r in rows]
        fig,axes=plt.subplots(1,2,figsize=(13,max(4,len(rows)*.7)),gridspec_kw={'width_ratios':[1.4,1]})
        stages=[('host_capture_to_image_ready_ms','Capture + transfer','#779bb7'),('codex_assisted_review_turnaround_ms','Codex-assisted turnaround','#38a79a'),('host_submit_to_commit_observed_ms','Result to commit observed','#e5a455')]
        left=[0.0]*len(rows)
        for key,label,color in stages:
            values=[r[key]/1000 for r in rows]
            axes[0].barh(labels,values,left=left,label=label,color=color);left=[a+b for a,b in zip(left,values)]
        axes[0].invert_yaxis();axes[0].set_xlabel('Host elapsed seconds (includes tools / orchestration)');axes[0].set_title('Observed capture-to-commit pipeline');axes[0].legend(loc='lower right',fontsize=8)
        axes[1].barh(labels,[r['device_apply_to_frame_commit_ms'] for r in rows],color='#417eaa');axes[1].invert_yaxis();axes[1].set_xlabel('Device elapsed milliseconds');axes[1].set_title('Apply to Android frame commit');axes[1].tick_params(axis='y',labelleft=False)
        fig.suptitle('Codex + RayNeo technical pilot — not isolated inference or optical latency',fontsize=12)
        fig.tight_layout();fig.savefig(out/'timing.png',dpi=160);fig.savefig(out/'timing.svg');plt.close(fig)
        svg=out/'timing.svg'
        svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    web_report(roots,out,summary,rows)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--runs',nargs='+',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();summary=analyze(args.runs,args.out)
    print(json.dumps({'completed_trials':summary['completed_trials'],'failed_trials':summary['failed_trials'],'variants':list(summary['variants'])}))
