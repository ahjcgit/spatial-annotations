'use strict';
let visionRevision = 0, visionChoice = 0, visionStream = null, visionImage = null;
function stopVisionCamera() {
  visionStream?.getTracks().forEach(track => track.stop()); visionStream = null;
  $('vision-video').srcObject = null; $('vision-video').hidden = true; $('vision-capture').disabled = true;
}
function clearVision() {
  visionRevision++; visionChoice++; stopVisionCamera();
  visionImage?.close(); visionImage = null;
  $('vision-canvas').hidden = true;
  $('vision-detections').replaceChildren(); $('vision-candidates').replaceChildren();
  $('vision-status').textContent = 'Select a photo or open a webcam preview.';
}
function drawVision(detections) {
  if (!visionImage) return;
  const canvas = $('vision-canvas'), ctx = canvas.getContext('2d');
  canvas.width = visionImage.width; canvas.height = visionImage.height;
  ctx.drawImage(visionImage, 0, 0); canvas.hidden = false;
  ctx.strokeStyle = '#ffff00'; ctx.lineWidth = Math.max(2,canvas.width/200);
  for (const detection of detections) {
    const [x1,y1,x2,y2] = detection.box;
    ctx.strokeRect(x1*canvas.width,y1*canvas.height,(x2-x1)*canvas.width,(y2-y1)*canvas.height);
  }
}
function validDetection(d) {
  return typeof d.label === 'string' && Number.isFinite(d.confidence) && d.confidence >= 0 && d.confidence <= 1 &&
    Array.isArray(d.box) && d.box.length === 4 && d.box.every(v => Number.isFinite(v) && v >= 0 && v <= 1) &&
    d.box[0] < d.box[2] && d.box[1] < d.box[3];
}
async function chooseVisionDetection(detection, revision) {
  if (revision !== visionRevision) return;
  generation++; currentObject=null; clearNotes(); $('object-status').textContent='No object confirmed';
  $('qr').hidden=true; $('print').hidden=true;
  const choice = ++visionChoice;
  $('vision-candidates').replaceChildren(); drawVision([detection]);
  $('vision-status').textContent = `Finding registered ${detection.label} objects…`;
  try {
    const objects = await api('/vision/candidates?label='+encodeURIComponent(detection.label));
    if (revision !== visionRevision || choice !== visionChoice) return;
    $('vision-status').textContent = objects.length ? 'Confirm which physical object this is. The model has not identified the instance.' : `No registered ${detection.label} objects. Set Visual category in the object registration form.`;
    for (const obj of objects) {
      const button = document.createElement('button'); button.textContent = `Confirm ${obj.name || obj.marker_id} · ${obj.marker_id.slice(0,8)}`;
      button.onclick = async () => {
        if (revision !== visionRevision || choice !== visionChoice) return;
        const version = ++generation; clearNotes(); renderObject(obj); $('marker').value = obj.marker_id;
        // Confirmation is explicit; the internal UUID never comes from visual classification.
        $('qr').hidden = true; $('print').hidden = true;
        $('vision-status').textContent = `Model + your confirmation: ${obj.name || obj.marker_id}`;
        try { await loadNotes(); if (version === generation) status('Confirmed object selected. Only authorized annotations are shown.'); }
        catch (error) { if (version === generation) status(error.message,true); }
      };
      $('vision-candidates').append(button);
    }
  } catch (error) { if (revision === visionRevision && choice === visionChoice) $('vision-status').textContent = error.message; }
}
async function detectVisionImage(image, revision) {
  if (revision !== visionRevision) { image.close(); return; }
  visionImage = image; drawVision([]);
  $('vision-status').textContent = 'Detecting objects…';
  // Normalize orientation and resize before upload; box coordinates refer to these exact pixels.
  const raw = await new Promise(resolve => $('vision-canvas').toBlob(resolve,'image/jpeg',.9));
  if (revision !== visionRevision) return;
  if (!raw || raw.size > 2*1024*1024) throw new Error('Image too large after resizing. Choose a smaller photo.');
  const result = await api('/vision/detect','POST',raw);
  if (revision !== visionRevision) return;
  const detections = result.detections.filter(validDetection); drawVision(detections);
  $('vision-status').textContent = detections.length ? `${detections.length} detections · ${Math.round(result.inference_ms)} ms inference. Select a category, then confirm the object.` : 'No confident object found. Try a clearer photo or use QR.';
  for (const detection of detections) {
    const button=document.createElement('button');button.textContent=`${detection.label} · ${Math.round(detection.confidence*100)}%`;
    button.onclick=()=>chooseVisionDetection(detection,revision);$('vision-detections').append(button);
  }
}
function beginVision() {
  if (!token) throw new Error('Sign in before model detection.');
  clearVision();generation++;currentObject=null;clearNotes();
  $('object-status').textContent='No object confirmed';$('qr').hidden=true;$('print').hidden=true;
  return visionRevision;
}
async function resizedVisionImage(source) {
  const original=await createImageBitmap(source);
  const scale=Math.min(1,1280/Math.max(original.width,original.height));
  try { return await createImageBitmap(original,{resizeWidth:Math.max(1,Math.round(original.width*scale)),resizeHeight:Math.max(1,Math.round(original.height*scale))}); }
  finally { original.close(); }
}
$('vision-file').addEventListener('change',async () => {
  const file=$('vision-file').files[0];$('vision-file').value='';if (!file) return;
  let revision;
  try {
    revision=beginVision();
    if (!['image/jpeg','image/png'].includes(file.type) || file.size>12*1024*1024) throw new Error('Choose a JPEG/PNG photo smaller than 12 MiB.');
    await detectVisionImage(await resizedVisionImage(file),revision);
  } catch(error) { if (revision===undefined || revision===visionRevision) $('vision-status').textContent=error.message; }
});
action('vision-camera',async () => {
  const revision=beginVision();
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    $('vision-status').textContent='Webcam requires HTTPS or localhost. On this computer open http://localhost:'+location.port+'; over LAN HTTP use photo upload.';return;
  }
  try {
    const stream=await navigator.mediaDevices.getUserMedia({video:{width:{ideal:1280},height:{ideal:720}},audio:false});
    if (revision!==visionRevision) { stream.getTracks().forEach(track=>track.stop());return; }
    visionStream=stream;$('vision-video').srcObject=stream;$('vision-video').hidden=false;
    await $('vision-video').play();
    if (revision!==visionRevision) return;
    $('vision-capture').disabled=false;$('vision-status').textContent='Live preview only. Aim at the object, then Capture and detect.';
  } catch(error) { if (revision===visionRevision) { stopVisionCamera();$('vision-status').textContent=`Camera unavailable: ${error.message}. Use photo upload instead.`; } }
});
action('vision-capture',async () => {
  const revision=visionRevision;if (!visionStream || !token) return;
  $('vision-capture').disabled=true;
  try {
    const image=await resizedVisionImage($('vision-video'));
    if (revision!==visionRevision) { image.close();return; }
    stopVisionCamera();await detectVisionImage(image,revision);
  } catch(error) { if (revision===visionRevision) { stopVisionCamera();$('vision-status').textContent=error.message; } }
});
action('vision-stop',() => { clearVision();generation++;currentObject=null;clearNotes();$('object-status').textContent='No object selected'; });
window.addEventListener('pagehide',clearVision);
