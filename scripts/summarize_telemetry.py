#!/usr/bin/env python3
"""Summarize actual JSONL or `adb logcat -v raw -s SpatialTelemetry:I` records, by environment/method."""
import argparse
import collections
import json
import math
import statistics
from pathlib import Path


def summarize(rows):
    groups=collections.defaultdict(list)
    for row in rows: groups[(row['environment'],row['identification_method'])].append(row)
    result=[]
    for (environment,method),samples in sorted(groups.items()):
        group={'environment':environment,'method':method,'samples':len(samples)}
        for key in ('recognition_success','backend_success','expectation_match'):
            values=[r[key] for r in samples if r.get(key) is not None]
            if values: group[key]={'samples':len(values),'passed':sum(values),'rate':sum(values)/len(values)}
        # Recognition success includes expected-negative images; positive-target rate is distinct.
        positive=[r for r in samples if r.get('expected_marker')]
        if positive: group['positive_target_success']={'samples':len(positive),'passed':sum(r['expectation_match'] for r in positive)}
        for key in ('recognition_latency_ms','backend_latency_ms','total_latency_ms','retrieval_to_ui_ms'):
            values=sorted(r[key] for r in samples if isinstance(r.get(key),(int,float)))
            if values:
                group[key]={'samples':len(values),'mean':statistics.mean(values),'median':statistics.median(values),
                            'p95':values[math.ceil(.95*len(values))-1] if len(values)>=20 else None}
        successful=sorted(r['total_latency_ms'] for r in samples if r.get('backend_success') is True and isinstance(r.get('total_latency_ms'),(int,float)))
        if successful: group['successful_total_latency_ms']={'samples':len(successful),'mean':statistics.mean(successful),'median':statistics.median(successful),'p95':successful[math.ceil(.95*len(successful))-1] if len(successful)>=20 else None}
        group['failures']=dict(collections.Counter(r['failure_category'] for r in samples if r.get('failure_category')))
        result.append(group)
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('files',nargs='+',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args(); rows=[];seen=set()
    for path in args.files:
        for line in path.read_text().splitlines():
            if '{' not in line: continue
            try: row=json.loads(line[line.index('{'):])
            except json.JSONDecodeError: continue
            if not all(k in row for k in ('test_id','environment','identification_method')): continue
            identity=(row['test_id'],row.get('timestamp'),row['environment'])
            if identity not in seen: rows.append(row);seen.add(identity)
    if not rows: raise SystemExit('No telemetry samples found; no measurements reported.')
    report=json.dumps(summarize(rows),indent=2)+'\n'
    if args.output: args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(report)
    print(report,end='')

if __name__=='__main__': main()
