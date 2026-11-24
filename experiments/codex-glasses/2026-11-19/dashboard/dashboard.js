'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const data = window.PILOT_DATA;
  if (!data) return;
  const titles = {'small-text':'Small text', 'large-text':'Large text', 'setup-diagnostics':'Setup', 'qualitative-baseline':'Image-only review'};
  const conditions = {two_labels:'two labels', no_labels:'no labels', no_review:'capture failed', baseline:'initial view', position_swap:'position swap', partial_occlusion:'partial occlusion', reappearance:'reappearance'};
  const stages = ['host_capture_to_image_ready_ms','codex_assisted_review_turnaround_ms','host_submit_to_commit_observed_ms'];
  const number = (v, places=2) => v == null ? 'Not measured' : v.toFixed(places);
  const seconds = v => v == null ? 'Not measured' : `${number(v/1000)} s`;
  const milliseconds = v => v == null ? 'Not measured' : `${number(v,1)} ms`;
  const trialName = t => `${titles[t.run]} / ${t.trial.replace('trial-', '')} · ${conditions[t.condition] || t.condition}`;
  function el(tag, text, className) { const node=document.createElement(tag); if(text!=null)node.textContent=text; if(className)node.className=className; return node; }
  function term(parent, title, text, note) { const row=el('div');row.append(el('dt',title));const value=el('dd',text);if(note)value.append(el('small',note));row.append(value);parent.append(row); }
  function anchor(text, url) { const a=el('a',text);a.href=url;return a; }
  const n=data.inventory, complete=data.trials.filter(t=>t.status==='completed');
  $('load-error').hidden=true;
  term($('inventory'),'Measured/setup attempts',`${n.completed+n.failed}`);
  term($('inventory'),'Completed frame commits',`${n.completed}`);
  term($('inventory'),'Retained failed attempts',`${n.failed}`);
  term($('inventory'),'Earlier image-only reviews',`${n.qualitative}`);
  $('trial-filter').options[0].textContent=`All ${data.trials.length} trial records`;
  $('integrity').textContent=data.integrity.ok ? `${data.integrity.archive_files} archive files + ${data.integrity.source_files} source hashes verified.` : 'Integrity check failed. Inspect the audit before presenting these results.';
  $('integrity').classList.add(data.integrity.ok?'good':'bad');
  $('delivery-finding').textContent=`${n.completed} matching frame commits: ${complete.filter(t=>t.labels.length).length} two-label scenes and ${complete.filter(t=>!t.labels.length).length} no-label scenes.`;
  $('timing-conclusion').textContent=`Review and tools account for ${number(data.review_fraction*100,1)}% of summed host elapsed time across ${n.completed} completed trials. The largest delay is before the response reaches the bench, not after it arrives.`;
  const ts=data.totals;
  for(const [title,key,fmt] of [['Capture → commit observed','host_capture_to_commit_observed_ms',seconds],['Review + tools','codex_assisted_review_turnaround_ms',seconds],['Response → commit observed','host_submit_to_commit_observed_ms',milliseconds],['Device apply → frame commit','device_apply_to_frame_commit_ms',milliseconds]]) {
    const s=ts[key];term($('timing-stats'),title,`${fmt(s.median)} median`,`${fmt(s.min)}–${fmt(s.max)} · n=${s.n}`);
  }
  function jump(id) { $('trial-filter').value='all';fillTrials(id);$('trials').scrollIntoView({behavior:'auto'});$('trial-select').focus({preventScroll:true}); }
  function chart() {
    $('timing-chart').replaceChildren();
    const maximum=Math.max(...complete.map(t=>t.metrics.host_capture_to_commit_observed_ms))*1.02;
    for(const t of complete.filter(t=>$('timing-filter').value==='all'||t.condition===$('timing-filter').value)) {
      const row=el('div',null,'timing-row'),header=el('header'),a=anchor(trialName(t),'#trials');
      a.onclick=e=>{e.preventDefault();jump(t.id);};header.append(a,el('span',seconds(t.metrics.host_capture_to_commit_observed_ms)));row.append(header);
      const bar=el('div',null,'bar');bar.setAttribute('role','img');bar.setAttribute('aria-label',stages.map((k,i)=>`${['Capture','Review','Delivery'][i]} ${seconds(t.metrics[k])}`).join(', '));
      stages.forEach((k,i)=>{const segment=el('span',null,['capture','review','delivery'][i]);segment.style.width=`${100*t.metrics[k]/maximum}%`;bar.append(segment);});
      row.append(bar,el('span',`${seconds(t.metrics[stages[0]])} capture · ${seconds(t.metrics[stages[1]])} review · ${milliseconds(t.metrics[stages[2]])} delivery`,'stage-values'));$('timing-chart').append(row);
    }
  }
  $('timing-filter').onchange=chart;chart();
  for(const g of data.groups) {
    const tr=el('tr');tr.append(el('th',`${titles[g.run]} / ${conditions[g.condition]}`),el('td',String(g.n)));
    for(const [key,divisor] of [['host_capture_to_commit_observed_ms',1000],['codex_assisted_review_turnaround_ms',1000],['host_submit_to_commit_observed_ms',1],['device_apply_to_frame_commit_ms',1]]) {
      const s=g.metrics[key];tr.append(el('td',`${number(s.median/divisor)} (${number(s.min/divisor)}–${number(s.max/divisor)})`));
    }
    $('groups').append(tr);
  }
  const rr=data.resource_ranges;
  $('resources').textContent=`Across completed trials: sampled app peak RSS ${number(rr.device.min,1)}–${number(rr.device.max,1)} MiB; sampled Python bench peak RSS ${number(rr.host.min,1)}–${number(rr.host.max,1)} MiB.`;
  $('resource-link').href=data.links.resource_csv;

  let visible=[];
  function fillTrials(preferred) {
    const value=$('trial-filter').value;
    visible=data.trials.filter(t=>value==='all'||t.status===value||(value==='no_labels'&&t.status==='completed'&&t.condition==='no_labels'));
    $('trial-select').replaceChildren(...visible.map(t=>new Option(trialName(t),t.id)));
    if(visible.some(t=>t.id===preferred))$('trial-select').value=preferred;
    showTrial();
  }
  function showTrial() {
    const t=visible.find(t=>t.id===$('trial-select').value);
    if(!t)return;
    const index=visible.indexOf(t);$('previous').disabled=index===0;$('next-trial').disabled=index===visible.length-1;
    $('trial-state').textContent=`${trialName(t)} — ${t.status==='completed'?'frame commit recorded':t.status==='failed'?'failed attempt retained':'review only; no delivery timing'}`;
    $('trial-state').className='trial-state '+(t.status==='failed'?'warn':'');
    $('trial-detail-title').textContent=t.status==='failed'?'Why this attempt did not complete':t.status==='review_only'?'What was proposed':'What was delivered';
    $('trial-explanation').textContent=t.failure ? t.failure.error : t.review || 'No visual review was recorded.';
    $('source-image').hidden=!t.source;$('source-image').alt=`Original camera snapshot: ${trialName(t)}`;$('source-missing').hidden=!!t.source;
    $('source-link').hidden=!t.source;$('boxes').replaceChildren();
    if(t.source){$('source-image').src=t.source;$('source-link').href=t.source;}else{$('source-image').removeAttribute('src');$('source-missing').textContent='No source image was saved before this failure.';}
    $('source-image').onerror=()=>{$('source-image').hidden=true;$('boxes').setAttribute('hidden','');$('source-missing').hidden=false;$('source-missing').textContent='Image unavailable. Check the adjacent archived trial folder, then reload.';};
    $('show-boxes').disabled=!t.source||!t.labels.length;
    const ns='http://www.w3.org/2000/svg';
    for(const l of t.labels){const color=l.uncertain?'#ffe18c':l.identity.startsWith('A')?'#73dfef':'#ffb866';const [x,y,r,b]=l.box;
      const rect=document.createElementNS(ns,'rect');for(const [k,v] of Object.entries({x,y,width:r-x,height:b-y,fill:'none',stroke:color,'stroke-width':6,'stroke-dasharray':l.uncertain?'14 8':'none'}))rect.setAttribute(k,v);
      const label=document.createElementNS(ns,'text');label.setAttribute('x',x+5);label.setAttribute('y',Math.max(42,y-10));label.setAttribute('fill',color);label.setAttribute('stroke','#101923');label.setAttribute('stroke-width','3');label.setAttribute('paint-order','stroke');label.setAttribute('font-size','42');label.textContent=l.identity+(l.uncertain?' ?':'');$('boxes').append(rect,label);
    }
    $('boxes').toggleAttribute('hidden',!$('show-boxes').checked||!t.source);
    $('trial-metrics').replaceChildren();
    if(t.status==='completed'){
      term($('trial-metrics'),'Capture → commit observed',seconds(t.metrics.host_capture_to_commit_observed_ms));
      term($('trial-metrics'),'Review + tools',seconds(t.metrics.codex_assisted_review_turnaround_ms));
      term($('trial-metrics'),'Response → commit observed',milliseconds(t.metrics.host_submit_to_commit_observed_ms));
      term($('trial-metrics'),'Snapshot age at apply',seconds(t.source_age_at_apply_ms));
    }else if(t.metrics.codex_assisted_review_turnaround_ms!=null){term($('trial-metrics'),'Elapsed review/orchestration before rejection',seconds(t.metrics.codex_assisted_review_turnaround_ms));}
    if(t.status==='review_only')term($('trial-metrics'),'Glasses delivery / request timing','Not measured');
    $('labels').replaceChildren();
    if(!t.labels.length)$('labels').append(el('li',t.condition==='no_labels'?'The response proposed no bottle labels.': 'No object proposal is available.'));
    for(const l of t.labels){const li=el('li');li.append(el('strong',`${l.label}${l.uncertain?' — uncertain proposal':''}`),el('span',l.evidence));$('labels').append(li);}
    $('display-figure').hidden=!t.display;$('display-missing').hidden=!!t.display;
    if(t.display){$('display-image').src=t.display;$('display-link').href=t.display;}else{$('display-image').removeAttribute('src');$('display-missing').textContent=t.status==='review_only'?'No device screenshot: these earlier reviews did not deliver labels to the glasses.':'No device screenshot was saved for this failed attempt.';}
    $('expiry').textContent=t.status==='completed'?(t.expiry_observed?'Automatic expiry acknowledgement recorded.':'Expiry acknowledgement not observed; final hold outcome is unresolved.'):t.retries.length?'This review includes a retained camera-stall capture retry.':'';
    $('expiry').className='note '+(t.status==='completed'&&!t.expiry_observed?'warn':'');
    $('trial-files').replaceChildren(...t.files.map(f=>{const li=el('li');li.append(anchor(f.name,f.url));return li;}));
  }
  $('trial-filter').onchange=()=>fillTrials($('trial-select').value);$('trial-select').onchange=showTrial;
  $('show-boxes').onchange=()=>{$('boxes').toggleAttribute('hidden',!$('show-boxes').checked);};
  for(const [id,delta] of [['previous',-1],['next-trial',1]])$(id).onclick=()=>{const index=visible.findIndex(t=>t.id===$('trial-select').value);const next=visible[index+delta];if(next){$('trial-select').value=next.id;showTrial();}};
  const requested=new URLSearchParams(location.search).get('trial');fillTrials(requested||'large-text/trial-04');
  for(const f of data.feedback){const block=el('blockquote');block.append(el('h4',titles[f.run]),el('p',`“${f.reported}”`),el('cite',f.scope+' · '));block.append(anchor('Source feedback',f.url));$('feedback').append(block);}
  const failureNotes={'setup-diagnostics/trial-01':'Startup/PID lookup failure before image capture. Not a completed latency sample.','setup-diagnostics/trial-02':'Activity lifecycle invalidated the pending capture. Subsequent delivery uses a broadcast.','large-text/trial-03':'Snapshot rejected after a long review/orchestration interruption. This exercises the age guard; it is not a slow-model benchmark.'};
  for(const t of data.trials.filter(t=>t.status==='failed')){const tr=el('tr'),th=el('th'),a=anchor(t.id,'#trials');a.onclick=e=>{e.preventDefault();jump(t.id);};th.append(a);tr.append(th,el('td',t.failure.error),el('td',failureNotes[t.id]||'Inspect the raw failure trace.'));$('failures').append(tr);}
  $('gap-intro').textContent=`The ${data.integrity.archive_files}-file manifest ${data.integrity.ok?'is complete and hash-verified':'needs integrity review'}. Some earlier experiments and reproduction files mentioned in the guides were not included. These are different from measurements this pilot never made.`;
  $('audit-count').textContent=`${data.integrity.checks.filter(c=>c.passed).length} / ${data.integrity.checks.length} checks passed: file hashes, image/request association, raw-clock recomputation, inventory and CSV agreement.`;
  for(const c of data.integrity.checks.filter(c=>!c.passed))$('audit-errors').append(el('li',`${c.name}: ${c.detail}`,'bad'));
  for(const r of data.relocated_references){const li=el('li');li.append(el('code',r.original),' → ',anchor(r.status,r.archived));$('relocated').append(li);}
  for(const [name,url] of [['Audited JSON','analysis.json'],['Trial CSV (includes failures)','trials.csv'],['Original report',data.links.original_report],['Archive manifest',data.links.manifest],['Methodology',data.links.methodology],['Archived validation summary',data.links.validation]])$('downloads').append(anchor(name,url));
})();
