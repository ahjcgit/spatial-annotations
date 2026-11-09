'use strict';
const $ = id => document.getElementById(id);
let token = '', me = null, currentObject = null, editId = null, annotations = [], generation = 0;
function status(message, error = false) { $('status').textContent = message; $('status').classList.toggle('error', error); }
async function api(path, method = 'GET', body) {
  const response = await fetch(path, {method, headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {})}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  if (response.status === 401 && token) { token = ''; me = null; generation++; clearNotes(); renderIdentity(); }
  if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(typeof error.detail === 'string' ? error.detail : `Request failed (${response.status}). Check required fields and permissions.`); }
  return response.status === 204 ? null : response.json();
}
function action(id, fn, event = 'click') { $(id).addEventListener(event, async e => { e.preventDefault(); try { await fn(); } catch (error) { status(error.message, true); } }); }
function markerId() { const raw = $('marker').value.trim().replace(/^spatial:v1:/, '').toLowerCase(); if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(raw)) throw new Error('Use a canonical UUID or spatial:v1:<UUID> marker.'); return raw; }
function newUuid() { const bytes = crypto.getRandomValues(new Uint8Array(16)); bytes[6] = bytes[6] & 15 | 64; bytes[8] = bytes[8] & 63 | 128; const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join(''); return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`; }
function clearNotes() { annotations = []; $('notes').replaceChildren(); $('note-count').textContent = 'Refresh to retrieve authorized annotations.'; $('more').hidden = true; cancelEdit(); }
function cancelEdit() { editId = null; $('content').value = ''; $('save-note').textContent = 'Create annotation'; $('cancel-edit').hidden = true; }
function renderIdentity() { $('identity').textContent = me ? `Signed in as ${me.username}` : 'Browsing as guest'; $('groups').replaceChildren(); $('note-group').replaceChildren(new Option('Choose a group', '')); $('member-group').replaceChildren(); }
async function signIn(register) {
  const credentials = {username: $('username').value, password: $('password').value};
  token = ''; me = null; generation++; clearNotes(); renderIdentity();
  if (register) await api('/auth/register', 'POST', credentials);
  const result = await api('/auth/login', 'POST', credentials); token = result.access_token; me = result.user; $('password').value = ''; renderIdentity();
  await loadGroups(); if (currentObject) await loadNotes(); status(`Signed in as ${me.username}.`);
}
async function loadGroups() {
  if (!me) return;
  const version = generation, groups = await api('/groups'); if (version !== generation) return;
  $('groups').replaceChildren(); $('note-group').replaceChildren(new Option('Choose a group', '')); $('member-group').replaceChildren();
  for (const group of groups) {
    $('note-group').add(new Option(group.name, group.id));
    const box = document.createElement('div'); box.className = 'group'; box.textContent = `${group.name} · ${group.member_ids.length} members`;
    if (group.owner_id === me.id) {
      $('member-group').add(new Option(group.name, group.id));
      for (const userId of group.member_ids.filter(id => id !== me.id)) {
        const row = document.createElement('div'); row.className = 'member'; row.textContent = userId;
        const button = document.createElement('button'); button.textContent = 'Remove'; button.className = 'secondary';
        button.onclick = async () => { try { await api(`/groups/${group.id}/members/${userId}`, 'DELETE'); await loadGroups(); await loadNotes(); status('Membership removed.'); } catch (e) { status(e.message, true); } }; row.append(button); box.append(row);
      }
    }
    $('groups').append(box);
  }
}
function showMarker(id) { $('qr').src = `/markers/${id}.png`; $('qr').hidden = false; $('print').hidden = false; }
function renderObject(obj) {
  $('detection-label').value = obj.spatial_metadata?.detection_label || '';
  currentObject = obj; $('object-status').textContent = `${obj.name || 'Unnamed object'} · ${obj.marker_id}`;
  for (const [field,key] of [['object-name','name'],['description','description'],['location','location_label'],['latitude','latitude'],['longitude','longitude']]) $(field).value = obj[key] ?? '';
}
async function lookup() {
  const id = markerId(), version = ++generation; currentObject = null; clearNotes(); showMarker(id);
  $('object-status').textContent = 'Looking up object…';
  try { const obj = await api(`/objects/by-marker/${id}`); if (version !== generation) return; renderObject(obj); await loadNotes(); status('Object selected. Only annotations you can access are shown.'); }
  catch (e) { if (version === generation) { $('object-status').textContent = `Unregistered or unavailable · ${id}`; for (const field of ['object-name','description','location','latitude','longitude','detection-label']) $(field).value = ''; } throw e; }
}
async function loadNotes(append = false) {
  if (!currentObject) return;
  const version = generation, id = currentObject.id, offset = append ? annotations.length : 0;
  if (!append) clearNotes();
  const list = await api(`/objects/${id}/annotations?limit=100&offset=${offset}`);
  if (version !== generation || currentObject?.id !== id) return;
  annotations = append ? annotations.concat(list) : list; renderNotes(); $('more').hidden = list.length < 100;
}
function renderNotes() {
  $('notes').replaceChildren(); $('note-count').textContent = `${annotations.length} authorized annotation(s) loaded`;
  for (const note of annotations) {
    const box = document.createElement('article'); box.className = 'note';
    const meta = document.createElement('p'); meta.className = 'badge'; meta.textContent = `${note.visibility.toUpperCase()} · ${note.author_username} · ${new Date(note.created_at).toLocaleString()}`;
    const content = document.createElement('p'); content.className = 'note-content'; content.textContent = note.content;
    box.append(meta, content);
    if (me?.id === note.author_id) {
      const edit = document.createElement('button'); edit.textContent = 'Edit'; edit.className = 'secondary';
      edit.onclick = () => { editId = note.id; $('content').value = note.content; $('visibility').value = note.visibility; $('note-group').value = note.group_id || ''; $('save-note').textContent = 'Save changes'; $('cancel-edit').hidden = false; $('content').focus(); };
      const remove = document.createElement('button'); remove.textContent = 'Delete'; remove.className = 'secondary';
      remove.onclick = async () => { if (!confirm('Delete this annotation?')) return; try { await api(`/annotations/${note.id}`, 'DELETE'); await loadNotes(); status('Annotation deleted.'); } catch (e) { status(e.message, true); } };
      const controls = document.createElement('div'); controls.className = 'row'; controls.append(edit, remove); box.append(controls);
    }
    $('notes').append(box);
  }
}
action('auth', () => signIn(false), 'submit'); action('register', () => { if ($('auth').reportValidity()) return signIn(true); });
action('logout', async () => { try { if (token) await api('/auth/logout', 'POST'); } finally { token = ''; me = null; generation++; clearNotes(); renderIdentity(); } if (currentObject) await loadNotes(); status('Signed out.'); });
action('lookup', lookup, 'submit'); action('new-marker', () => { generation++; currentObject = null; clearNotes(); const id = newUuid(); $('marker').value = id; showMarker(id); $('object-status').textContent = `New marker · ${id}`; for (const field of ['object-name','description','location','latitude','longitude','detection-label']) $(field).value = ''; status('Fill in the registration form, then save the object.'); });
action('print', () => window.print());
action('object-form', async () => {
  const data = {name: $('object-name').value, description: $('description').value, location_label: $('location').value, latitude: $('latitude').value === '' ? null : Number($('latitude').value), longitude: $('longitude').value === '' ? null : Number($('longitude').value)};
  const id = markerId(); const isUpdate = currentObject?.marker_id === id;
  data.spatial_metadata = {...(isUpdate ? currentObject.spatial_metadata : {}), detection_label: $('detection-label').value.trim().toLowerCase()};
  const obj = await api(isUpdate ? `/objects/${currentObject.id}` : '/objects', isUpdate ? 'PATCH' : 'POST', isUpdate ? data : {...data, marker_id: id});
  generation++; clearNotes(); renderObject(obj); showMarker(id); await loadNotes(); status('Object saved. Print and attach its marker.');
}, 'submit');
action('note-form', async () => {
  if (!currentObject) throw new Error('Select a registered object first.');
  const data = {content: $('content').value, visibility: $('visibility').value, group_id: $('visibility').value === 'group' ? $('note-group').value || null : null};
  await api(editId ? `/annotations/${editId}` : '/annotations', editId ? 'PATCH' : 'POST', editId ? data : {...data, object_id: currentObject.id}); cancelEdit(); await loadNotes(); status('Annotation saved. Refresh on the glasses to retrieve it.');
}, 'submit');
action('cancel-edit', cancelEdit); action('refresh', () => loadNotes()); action('more', () => loadNotes(true));
action('group-form', async () => { await api('/groups', 'POST', {name: $('group-name').value}); await loadGroups(); status('Group created.'); }, 'submit');
action('member-form', async () => { if (!$('member-group').value) throw new Error('Create a group first.'); await api(`/groups/${$('member-group').value}/members`, 'POST', {username: $('member-name').value}); await loadGroups(); status('Member added.'); }, 'submit');
