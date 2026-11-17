'use strict';
const $ = id => document.getElementById(id);
let token = null, authGeneration = 0, noteController;
let study, index = 0, generation = 0, controller, timer, packet, picture;
const colors = {correct:'#77e2bc', incorrect:'#ff9d93', unknown:'#ffd36a', matched:'#7bd5ee'};
function fail(error) { $('error').hidden = false; $('error').textContent = `${error.message}. Select another run or reload to retry.`; stop(); }
async function api(url, signal) { const response = await fetch(url,{signal}); if (!response.ok) throw Error(`Could not load study data (${response.status})`); return response.json(); }
function stop() { clearTimeout(timer); timer = null; $('play').textContent = 'Play'; }
function overlap(a,b) { const area = Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1])); return area/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-area); }
function judgment(row) { if (!row.object_id) return 'unknown'; if (!packet.ground_truth) return 'matched'; const gt = packet.ground_truth.filter(g=>overlap(g.bbox,row.bbox)>=.5).sort((a,b)=>overlap(b.bbox,row.bbox)-overlap(a.bbox,row.bbox))[0]; return gt?.object_id===row.object_id?'correct':'incorrect'; }
function line(parent,text,className) { const el=document.createElement('span'); el.textContent=text; if(className) el.className=className; parent.append(el); return el; }
function render() {
  const canvas=$('frame'), ctx=canvas.getContext('2d'); const width=picture.naturalWidth,height=picture.naturalHeight,cssWidth=canvas.getBoundingClientRect().width;const backing=Math.max(1,cssWidth*window.devicePixelRatio/width);canvas.width=Math.round(width*backing);canvas.height=Math.round(height*backing);ctx.setTransform(backing,0,0,backing,0,0);ctx.drawImage(picture,0,0);
  const scale=width/cssWidth; ctx.font=`${12*scale}px system-ui`; ctx.lineWidth=2*scale;
  for (const gt of packet.ground_truth||[]) { ctx.strokeStyle='#b2c7ff'; ctx.setLineDash([5*scale,4*scale]); const b=gt.bbox; ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]); }
  ctx.setLineDash([]); $('tracks').replaceChildren(); $('empty').textContent=packet.selected?'No detections in this frame.':'No observations selected in this frame.'; $('empty').hidden=packet.predictions.length>0;
  for (const row of packet.predictions) {
    const state=judgment(row), b=row.bbox; ctx.strokeStyle=colors[state]; ctx.strokeRect(b[0],b[1],b[2]-b[0],b[3]-b[1]);
    ctx.fillStyle=colors[state];ctx.fillText(`T${row.track_id}`,b[0]+2,Math.max(12*scale,b[1]-3));
    const tr=document.createElement('tr'); const track=document.createElement('td'), identity=document.createElement('td'), status=document.createElement('td');track.textContent=`T${row.track_id} / g${row.generation}`;
    line(identity,row.object_name||'Unknown','identity'); if(row.object_id)line(identity,row.object_id,'uuid');
    if(row.proposed_object_id&&!row.object_id)line(identity,`Proposed, not accepted: ${row.proposed_object_id}`,'uuid');
    if(row.annotation_label)line(identity,row.annotation_label,'identity');
    line(status,`${packet.ground_truth&&state!==row.identity_state?state+' · ':''}${row.identity_state}`,state);line(status,(row.match_source||row.reason||'No accepted match').replaceAll('_',' '),'identity');
    tr.append(track,identity,status);$('tracks').append(tr);
  }
  if(packet.ground_truth) { for(const gt of packet.ground_truth) { const tr=document.createElement('tr');const a=document.createElement('td'),b=document.createElement('td'),c=document.createElement('td');a.textContent='GT';b.textContent=gt.object_id||'Unregistered';c.textContent=gt.instance_id;tr.append(a,b,c);$('tracks').append(tr); } }
  $('events').replaceChildren();$('events-empty').hidden=packet.events.length>0;
  for(const event of packet.events.slice(-8)) { const li=document.createElement('li');li.textContent=`${event.provider} · ${event.failure_category||event.outcome} · ${event.latency_ms.toFixed(1)} ms · tracks ${event.observations.map(o=>o.track_id).join(', ')}`;$('events').append(li); }
  const sequence=study.sequences[Number($('sequence').value)];$('position').textContent=`Frame ${index+1} / ${sequence.frames} · ${packet.timestamp_s.toFixed(2)} s`;
  $('frame-status').textContent=packet.selected?`Replay processing: ${packet.replay_processing_ms.toFixed(1)} ms`:'Not selected for this predefined-probe pass.';
  $('previous').disabled=index===0;$('next').disabled=index===sequence.frames-1;$('scrubber').value=index;$('scrubber').max=sequence.frames-1;
}
async function show() {
  if(!study?.runs.length)return;
  clearNotes();packet=null;picture=null;$('tracks').replaceChildren();$('empty').hidden=false;$('empty').textContent='Loading associations…';$('frame').getContext('2d').clearRect(0,0,$('frame').width,$('frame').height);$('position').textContent=`Loading frame ${index+1}…`;const current=++generation;controller?.abort();controller=new AbortController();$('error').hidden=true;$('frame-status').textContent='Loading frame…';
  try { const next=await api(`/api/frame/${$('sequence').value}/${index}?run=${encodeURIComponent($('run').value)}&evaluation=${$('evaluation').checked}`,controller.signal);
    const img=new Image();img.src=next.image_url;await img.decode();if(current!==generation)return;packet=next;picture=img;render();loadNotes();
  } catch(error) { if(error.name!=='AbortError'&&current===generation)fail(error); }
}
async function tick() { await show();if(!timer)return; const sequence=study.sequences[Number($('sequence').value)];if(index>=sequence.frames-1){stop();return;}timer=setTimeout(()=>{index++;tick();},Math.max(40,(packet.next_delta_s||.5)*1000)); }
$('play').onclick=()=>{if(timer){stop();return;}timer=true;$('play').textContent='Pause';tick();};
$('previous').onclick=()=>{stop();index=Math.max(0,index-1);show();};$('next').onclick=()=>{stop();index=Math.min(study.sequences[Number($('sequence').value)].frames-1,index+1);show();};
$('sequence').onchange=()=>{stop();index=0;show();};$('run').onchange=()=>{stop();show();};$('evaluation').onchange=show;
$('scrubber').oninput=()=>{stop();index=Number($('scrubber').value);show();};
async function init() { try { study=await api('/api/study');$('evidence').textContent=study.evidence_kind==='deterministic_fixture'?'Synthetic software fixture — not a laptop or VLM accuracy benchmark.':'Recorded-image evaluation — inspect per-recording outcomes before aggregating frames.';
  $('annotation-panel').hidden=!study.annotations_enabled;
  if(!study.runs.length){$('frame-status').textContent='No compatible results. Run identity_suite.py suite for this dataset, then reload.';return;}
  for(const s of study.sequences)$('sequence').add(new Option(`${s.id} · ${s.condition}`,s.index));
  for(const r of study.runs)$('run').add(new Option(`${r.method} · Pass ${r.pass} · ${r.protocol} · trial ${r.trial} · ${r.provider_kind}`,r.id));
  for(const id of ['sequence','run','play','scrubber'])$(id).disabled=false;await show();
} catch(error){fail(error);} }
function clearNotes(){noteController?.abort();$('notes').replaceChildren();}
function signout(){authGeneration++;token=null;clearNotes();$('signout').disabled=true;$('refresh-notes').disabled=true;$('session').textContent='Signed out.';}
$('signout').onclick=signout;
$('login').onsubmit=async event=>{event.preventDefault();signout();const epoch=authGeneration;$('session').textContent='Signing in…';
  const credentials={username:$('username').value,password:$('password').value};$('password').value='';
  try{const response=await fetch('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(credentials)});
    if(epoch!==authGeneration)return;if(!response.ok)throw Error('Sign-in failed. Check credentials and backend connection.');
    const value=await response.json();if(epoch!==authGeneration)return;token=value.access_token;$('session').textContent=`Signed in as ${credentials.username}`;$('signout').disabled=false;$('refresh-notes').disabled=false;loadNotes();
  }catch(error){if(epoch===authGeneration)$('session').textContent=error.message;}};
$('refresh-notes').onclick=loadNotes;
async function loadNotes(){clearNotes();if(!token||!packet)return;const epoch=authGeneration,view=generation;noteController=new AbortController();const signal=noteController.signal;
  const matched=packet.predictions.filter(r=>r.identity_state==='matched'&&r.object_id);if(!matched.length){$('notes').textContent='No accepted identities in this frame.';return;}
  try{const values=await Promise.all(matched.map(async row=>{const response=await fetch(`/api/notes/${$('sequence').value}/${index}/${row.track_id}?run=${encodeURIComponent($('run').value)}`,{headers:{Authorization:`Bearer ${token}`},signal});if(response.status===401){if(epoch===authGeneration){signout();$('session').textContent='Session expired; sign in again.';}throw Error('Session expired; sign in again.');}if(!response.ok)throw Error('Notes unavailable. Use Refresh notes to retry.');return {row,data:await response.json()};}));
    if(epoch!==authGeneration||view!==generation)return;
    for(const {row,data} of values){const heading=document.createElement('h3');heading.textContent=row.object_name||row.object_id;$('notes').append(heading);
      if(!data.notes.length){const p=document.createElement('p');p.textContent='No authorized notes.';$('notes').append(p);}
      for(const note of data.notes){const p=document.createElement('p');p.textContent=`${note.visibility} · ${note.author_id}\n${note.content}`;$('notes').append(p);}
      if(data.notes.length===data.limit){const p=document.createElement('p');p.textContent='Showing the first 100 notes. Use the companion for the complete list.';$('notes').append(p);}}
  }catch(error){if(error.name!=='AbortError'&&epoch===authGeneration&&view===generation)$('notes').textContent=error.message;}}
window.addEventListener('resize',()=>{if(picture&&packet)render();});
init();
