const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);

let tracks = [];
let filtered = [];
let playlists = [];
let queue = [];
let currentIdx = -1;
let activePlaylistId = null;
let viewMode = 'all';
let repeatMode = 'off'; // off | all | one
let pendingUploadPlaylistId = null;

const audio = $('#audio');
const trackBody = $('#trackBody');
const searchInput = $('#search');
const sortSelect = $('#sortSelect');
const viewTitle = $('#viewTitle');
const viewSubtitle = $('#viewSubtitle');
const artistsView = $('#artistsView');
const albumsView = $('#albumsView');

// --- XSS helpers ---
function escapeHtml(s){ return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function escapeAttr(s){ return escapeHtml(s); }
function sanitizeColor(c){ return /^#[0-9a-fA-F]{3,8}$/.test(c) ? c : '#2a2a2a'; }

const LIKED_SONGS_NAME = 'Liked Songs';

// --- View State Persistence ---
const STATE_KEY = 'ash_ui_state_v2';
function saveViewState(){
  try{
    const mainEl = document.querySelector('.main');
    const sideEl = document.querySelector('.sidebar');
    const state = {
      activePlaylistId,
      viewMode,
      search: searchInput ? searchInput.value : '',
      sort: sortSelect ? sortSelect.value : 'created_at-desc',
      scrollMain: mainEl ? mainEl.scrollTop : 0,
      scrollSide: sideEl ? sideEl.scrollTop : 0
    };
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
  }catch(e){}
}
function getSavedState(){
  try{
    const raw = localStorage.getItem(STATE_KEY);
    return raw ? JSON.parse(raw) : null;
  }catch(e){ return null; }
}

// --- Toast ---
function toast(msg, ms=2400){
  const t = $('#toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  setTimeout(()=>t.classList.add('hidden'), ms);
}

// --- Custom Confirm (replaces native confirm) ---
let _confirmResolve = null;
let _confirmBound = false;
function ashConfirm(message, {title='Подтвердите действие', okText='Удалить', cancelText='Отмена', danger=true}={}){
  const overlay = $('#confirmModal');
  const titleEl = $('#confirmTitle');
  const msgEl = $('#confirmMessage');
  const okBtn = $('#confirmOk');
  const cancelBtn = $('#confirmCancel');
  if(!overlay || !titleEl || !msgEl || !okBtn || !cancelBtn){
    return Promise.resolve(confirm(message));
  }
  titleEl.textContent = title;
  msgEl.textContent = message;
  okBtn.textContent = okText;
  cancelBtn.textContent = cancelText;
  okBtn.classList.toggle('danger', !!danger);
  overlay.classList.remove('hidden');
  overlay.style.display = 'flex';
  // focus ok for keyboard
  setTimeout(()=> okBtn.focus(), 30);

  return new Promise(resolve=>{
    _confirmResolve = resolve;
    const close = (val)=>{
      overlay.classList.add('hidden');
      overlay.style.display = '';
      cleanup();
      _confirmResolve = null;
      resolve(val);
    };
    const onOk = ()=> close(true);
    const onCancel = ()=> close(false);
    const onOverlay = (e)=>{ if(e.target===overlay) close(false); };
    const onKey = (e)=>{
      if(overlay.classList.contains('hidden')) return;
      if(e.key==='Escape'){ e.preventDefault(); close(false); }
    };
    function cleanup(){
      okBtn.removeEventListener('click', onOk);
      cancelBtn.removeEventListener('click', onCancel);
      overlay.removeEventListener('click', onOverlay);
      document.removeEventListener('keydown', onKey);
      _confirmBound = false;
    }
    // ensure single binding per open
    if(_confirmBound) cleanup();
    _confirmBound = true;
    okBtn.addEventListener('click', onOk);
    cancelBtn.addEventListener('click', onCancel);
    overlay.addEventListener('click', onOverlay);
    document.addEventListener('keydown', onKey);
  });
}

// --- Fetch helpers ---
async function api(path, opts={}){
  const res = await fetch(path, opts);
  if(!res.ok) throw new Error(await res.text());
  const ct = res.headers.get('content-type')||'';
  if(ct.includes('application/json')) return res.json();
  return res;
}
function formatDuration(s){
  if(!s) return '0:00';
  s = Math.round(s);
  const m = Math.floor(s/60);
  const sec = String(s%60).padStart(2,'0');
  return `${m}:${sec}`;
}
function totalDurationLabel(sec){
  const h = Math.floor(sec/3600);
  const m = Math.floor((sec%3600)/60);
  if(h>0) return `${h} ч ${m} мин`;
  return `${m} мин`;
}

// --- Loaders ---
async function loadStats(){
  try{
    const s = await api('/api/stats');
    $('#statTracks').textContent = s.tracks;
    $('#statDuration').textContent = totalDurationLabel(s.duration);
    $('#statPlaylists').textContent = s.playlists;
  }catch(e){console.error(e)}
}
async function loadTracks(){
  const q = searchInput.value.trim();
  const [sort, order] = sortSelect.value.split('-');
  const params = new URLSearchParams({sort, order});
  if(q) params.set('search', q);
  if(viewMode==='artists' || viewMode==='albums'){
    // handled separately
  }
  const data = await api('/api/tracks?'+params.toString());
  tracks = data;
  applyFilter();
}
async function loadPlaylists(){
  playlists = await api('/api/playlists');
  renderPlaylists();
}
async function loadArtists(){
  const arr = await api('/api/artists');
  artistsView.innerHTML = arr.map(a=>`<button class="chip" data-artist="${escapeAttr(a)}">${escapeHtml(a)}</button>`).join('') || '<span class="muted">Нет исполнителей</span>';
  artistsView.querySelectorAll('.chip').forEach(ch=>{
    ch.addEventListener('click', ()=>{
      artistsView.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
      ch.classList.add('active');
      const artist = ch.dataset.artist;
      filtered = tracks.filter(t=>t.artist===artist);
      queue = [...filtered];
      renderTracks();
      viewTitle.textContent = artist;
      viewSubtitle.textContent = `${filtered.length} треков`;
    });
  });
}
async function loadAlbums(){
  const arr = await api('/api/albums');
  if(!arr.length){
    albumsView.innerHTML = '<span class="muted">Нет альбомов</span>';
    return;
  }
  // поддержка старого формата (strings) и нового (AlbumResponse)
  if(typeof arr[0] === 'string'){
    albumsView.innerHTML = arr.map(a=>`<button class="chip" data-album="${escapeAttr(a)}">${escapeHtml(a)}</button>`).join('');
  } else {
    albumsView.innerHTML = arr.map(a=>`<button class="chip" data-album-id="${a.id}" data-album="${escapeAttr(a.title)}"><i class="ti ti-disc"></i> ${escapeHtml(a.title)} <span style="opacity:.6">— ${escapeHtml(a.artist)} • ${a.track_count}</span></button>`).join('');
  }
  albumsView.querySelectorAll('.chip').forEach(ch=>{
    ch.addEventListener('click', async ()=>{
      albumsView.querySelectorAll('.chip').forEach(c=>c.classList.remove('active'));
      ch.classList.add('active');
      const albumId = ch.dataset.albumId;
      const albumTitle = ch.dataset.album;
      if(albumId){
        // запрос через БД по album_id
        const data = await api('/api/tracks?album_id=' + albumId);
        filtered = data;
      } else {
        filtered = tracks.filter(t=>t.album===albumTitle);
      }
      queue = [...filtered];
      renderTracks();
      viewTitle.textContent = albumTitle;
      viewSubtitle.textContent = `${filtered.length} треков — альбом`;
    });
  });
}

function applyFilter(){
  if(activePlaylistId){
    const pl = playlists.find(p=>p.id===activePlaylistId);
    filtered = pl ? pl.tracks : [];
  } else {
    // if view is recent: last 20 by created_at
    if(viewMode==='recent'){
      filtered = [...tracks].slice(0,20);
    } else {
      filtered = [...tracks];
    }
  }
  queue = [...filtered];
  renderTracks();
}

function renderPlaylists(){
  const list = $('#playlistList');
  // Liked Songs всегда первым
  const sorted = [...playlists].sort((a,b)=>{
    if(a.name===LIKED_SONGS_NAME) return -1;
    if(b.name===LIKED_SONGS_NAME) return 1;
    return 0;
  });
  list.innerHTML = sorted.map(p=>{
    const isLiked = p.name===LIKED_SONGS_NAME;
    const delBtn = isLiked ? '' : `<button data-del="${p.id}" title="Удалить"><i class="ti ti-trash"></i></button>`;
    const dotIcon = isLiked ? '<i class="ti ti-heart-filled" style="font-size:8px;color:var(--bg)"></i>' : '';
    const dotBg = isLiked ? '#d6d3cf' : sanitizeColor(p.cover_color);
    return `
    <div class="pl-item ${activePlaylistId===p.id?'active':''}" data-id="${p.id}">
      <div class="pl-dot" style="background:${dotBg};display:grid;place-items:center">${dotIcon}</div>
      <div class="pl-info">
        <strong>${escapeHtml(p.name)}</strong>
        <span>${p.track_count} треков</span>
      </div>
      <button class="pl-upload" data-upload="${p.id}" title="Загрузить сразу в этот плейлист"><i class="ti ti-upload"></i></button>
      ${delBtn}
    </div>
  `;
  }).join('') || '<span class="muted" style="font-size:12px">Нет плейлистов</span>';

  list.querySelectorAll('.pl-item').forEach(el=>{
    el.addEventListener('click', (e)=>{
      if(e.target.closest('[data-del]') || e.target.closest('[data-upload]')) return;
      activePlaylistId = Number(el.dataset.id);
      viewMode='playlist';
      const pl = playlists.find(p=>p.id===activePlaylistId);
      viewTitle.textContent = pl.name;
      viewSubtitle.textContent = pl.description || `${pl.track_count} треков • пепельная подборка`;
      $('#artistsView').classList.add('hidden');
      $('#albumsView').classList.add('hidden');
      document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
      applyFilter();
      renderPlaylists();
      updateUploadLabel();
      saveViewState();
    });
  });
  list.querySelectorAll('[data-upload]').forEach(btn=>{
    btn.addEventListener('click', (e)=>{
      e.stopPropagation();
      pendingUploadPlaylistId = Number(btn.dataset.upload);
      updateUploadLabel();
      $('#uploadInput').click();
      setTimeout(()=>{ if(pendingUploadPlaylistId===Number(btn.dataset.upload)){ pendingUploadPlaylistId=null; updateUploadLabel(); } }, 30000);
    });
  });
  list.querySelectorAll('[data-del]').forEach(btn=>{
    btn.addEventListener('click', async (e)=>{
      e.stopPropagation();
      const id = Number(btn.dataset.del);
      const pl = playlists.find(p=>p.id===id);
      const ok = await ashConfirm(`Плейлист «${pl?pl.name:'#' + id}» будет удалён. Треки останутся в фонотеке.`, {title:'Удалить плейлист?', okText:'Удалить', cancelText:'Отмена', danger:true});
      if(!ok) return;
      await api(`/api/playlists/${id}`, {method:'DELETE'});
      if(activePlaylistId===id) { activePlaylistId=null; viewTitle.textContent='Вся фонотека'; viewSubtitle.textContent='Угольно-серый архив твоего звука'; updateUploadLabel(); }
      await loadPlaylists();
      await loadStats();
      applyFilter();
      saveViewState();
      toast('Плейлист удалён');
    });
  });
  // drag & drop на плейлист — сразу загрузка в него
  list.querySelectorAll('.pl-item').forEach(el=>{
    el.addEventListener('dragover', e=>{ e.preventDefault(); el.style.borderColor='var(--ash-light)'; el.style.background='var(--surface-2)'; });
    el.addEventListener('dragleave', ()=>{ el.style.borderColor=''; el.style.background=''; });
    el.addEventListener('drop', async e=>{
      e.preventDefault(); el.style.borderColor=''; el.style.background='';
      const pid = Number(el.dataset.id);
      const files = e.dataTransfer.files;
      if(files.length) await uploadFiles(files, pid);
    });
  });

  // picker
  const pickerList = $('#pickerList');
  if(pickerList){
    pickerList.innerHTML = playlists.map(p=>`<button data-pick="${p.id}">${escapeHtml(p.name)}</button>`).join('');
  }
}

function renderTracks(){
  if(!filtered.length){
    trackBody.innerHTML = '';
    $('#emptyState').classList.remove('hidden');
    return;
  }
  $('#emptyState').classList.add('hidden');
  trackBody.innerHTML = filtered.map((t, i)=>{
    const isActive = queue[currentIdx] && queue[currentIdx].id===t.id;
    const inAny = playlists.some(pl=>pl.tracks.some(x=>x.id===t.id));
    const inLiked = playlists.find(p=>p.name===LIKED_SONGS_NAME)?.tracks.some(x=>x.id===t.id);
    const heartIcon = inLiked ? '<i class="ti ti-heart-filled" style="color:var(--ash-light)"></i>' : (inAny ? '<i class="ti ti-heart-filled" style="color:var(--ash-light)"></i>' : '<i class="ti ti-heart"></i>');
    const heartTitle = inLiked ? 'В Liked Songs — убрать' : (inAny ? 'В плейлисте — управление' : 'Добавить в Liked Songs');
    return `<tr class="${isActive?'active':''}" data-id="${t.id}" data-idx="${i}">
      <td><div class="cell-title"><span class="idx">${String(i+1).padStart(2,'0')}</span>
        <div class="art">${isActive?'<i class="ti ti-player-play"></i>':'<i class="ti ti-music"></i>'}</div></div></td>
      <td><div class="cell-title" style="flex-direction:column;align-items:flex-start;gap:2px">
        <strong>${escapeHtml(t.title)}</strong><span>${escapeHtml(t.artist)} • ${escapeHtml(t.year||'—')}</span></div></td>
      <td class="muted">${escapeHtml(t.album)}</td>
      <td style="font-family:var(--mono);font-size:12px">${escapeHtml(formatDuration(t.duration))}</td>
      <td><div class="actions">
        <button class="icon-btn heart-btn" data-heart="${t.id}" title="${heartTitle}">${heartIcon}</button>
        <button class="icon-btn add-btn" data-add="${t.id}" title="Добавить в плейлист"><i class="ti ti-plus"></i></button>
        <button class="icon-btn del-btn" data-del="${t.id}" title="Удалить"><i class="ti ti-trash"></i></button>
      </div></td>
    </tr>`;
  }).join('');

  trackBody.querySelectorAll('tr').forEach(tr=>{
    tr.addEventListener('click', (e)=>{
      if(e.target.closest('.add-btn') || e.target.closest('.del-btn')) return;
      const idx = Number(tr.dataset.idx);
      playAt(idx);
    });
  });
  trackBody.querySelectorAll('.heart-btn').forEach(b=>{
    const tid = Number(b.dataset.heart);
    b.addEventListener('click', async (e)=>{
      e.stopPropagation();
      const liked = getLikedPlaylist();
      if(!liked) return toast('Liked Songs не найден');
      const inLiked = liked.tracks.some(t=>t.id===tid);
      try{
        if(inLiked){
          await api(`/api/playlists/${liked.id}/tracks/${tid}`, {method:'DELETE'});
          toast('Убрано из Liked Songs');
          liked.tracks = liked.tracks.filter(t=>t.id!==tid);
          liked.track_count = liked.tracks.length;
        } else {
          await api(`/api/playlists/${liked.id}/tracks/${tid}`, {method:'POST'});
          toast('Добавлено в Liked Songs');
          const t = tracks.find(x=>x.id===tid);
          if(t && !liked.tracks.some(x=>x.id===tid)){ liked.tracks.push(t); liked.track_count = liked.tracks.length; }
        }
        renderTracks();
        renderPlaylists();
        updatePlayerHeart();
      }catch(err){ toast('Ошибка'); }
    });
  });
  trackBody.querySelectorAll('.add-btn').forEach(b=>{
    b.addEventListener('click', (e)=>{
      e.stopPropagation();
      openPlaylistManager(Number(b.dataset.add));
    });
  });
  trackBody.querySelectorAll('.del-btn').forEach(b=>{
    b.addEventListener('click', async (e)=>{
      e.stopPropagation();
      const id = Number(b.dataset.del);
      const t = filtered.find(x=>x.id===id) || tracks.find(x=>x.id===id);
      const name = t ? `«${t.title}» — ${t.artist}` : `трек #${id}`;
      const ok = await ashConfirm(`${name}\n\nФайл будет удалён с диска без возможности восстановления.`, {title:'Удалить трек?', okText:'Удалить', cancelText:'Отмена', danger:true});
      if(!ok) return;
      const row = b.closest('tr');
      if(row) { row.style.opacity='0.4'; b.disabled=true; }
      try{
        await api(`/api/tracks/${id}`, {method:'DELETE'});
      }catch(err){ toast('Ошибка удаления'); if(row){row.style.opacity=''; b.disabled=false;} return; }
      toast('Трек удалён — пепел развеян');
      // optimistic update без перезагрузки страницы
      tracks = tracks.filter(x=>x.id!==id);
      filtered = filtered.filter(x=>x.id!==id);
      playlists.forEach(pl=>{ pl.tracks = pl.tracks.filter(x=>x.id!==id); pl.track_count = pl.tracks.length; });
      const qIdx = queue.findIndex(x=>x.id===id);
      if(qIdx !== -1){
        queue.splice(qIdx,1);
        if(qIdx === currentIdx){
          audio.pause();
          audio.src='';
          $('#playerTitle').textContent='Ничего не играет';
          $('#playerArtist').textContent='Выбери трек из пепла';
          $('#playerCover').innerHTML='<i class="ti ti-music"></i>';
          $('#playBtn').innerHTML='<i class="ti ti-player-play"></i>';
          currentIdx = -1;
        } else if(qIdx < currentIdx){
          currentIdx--;
        }
      }
      renderTracks();
      renderPlaylists();
      saveViewState();
      try{ await loadStats(); }catch(e){}
      // синхронизируем с сервером в фоне (перезагрузит плейлисты/треки если рассинхрон)
      loadPlaylists().then(()=>{ if(activePlaylistId) applyFilter(); saveViewState(); }).catch(()=>{});
      // не ждём loadTracks чтобы не мигал, но обновим скрыто
      // await loadTracks() можно вызвать если нужно, но optimistic уже актуален
    });
  });
}

// --- Player ---
function playAt(idx){
  if(idx<0 || idx>=queue.length) return;
  currentIdx = idx;
  const t = queue[currentIdx];
  audio.src = `/api/stream/${t.id}`;
  audio.play().catch(()=>{});
  $('#playerTitle').textContent = t.title;
  $('#playerArtist').textContent = `${t.artist} — ${t.album}`;
  $('#playerCover').textContent = t.title[0]?.toUpperCase() || '';
  if(!$('#playerCover').textContent) $('#playerCover').innerHTML = '<i class="ti ti-music"></i>';
  $('#playBtn').innerHTML = '<i class="ti ti-player-pause"></i>';
  renderTracks();
  updatePlayerHeart();
  saveViewState();
}
function togglePlay(){
  if(!queue.length) return;
  if(currentIdx===-1){ playAt(0); return;}
  if(audio.paused){ audio.play(); $('#playBtn').innerHTML='<i class="ti ti-player-pause"></i>';}
  else { audio.pause(); $('#playBtn').innerHTML='<i class="ti ti-player-play"></i>';}
}
function updateRepeatUI(){
  const btn = $('#repeatBtn');
  if(repeatMode === 'off'){
    btn.innerHTML = '<i class="ti ti-repeat"></i>';
    btn.style.color = 'var(--text-faint)';
    btn.style.borderColor = 'var(--border)';
    btn.title = 'Без повтора — клик для повтора плейлиста';
    btn.classList.remove('active');
  } else if(repeatMode === 'all'){
    btn.innerHTML = '<i class="ti ti-repeat"></i>';
    btn.style.color = 'var(--ash-light)';
    btn.style.borderColor = 'var(--ash-light)';
    btn.title = 'Повтор плейлиста — клик для повтора трека';
    btn.classList.add('active');
  } else { // one
    btn.innerHTML = '<i class="ti ti-repeat-once"></i>';
    btn.style.color = 'var(--ash-light)';
    btn.style.borderColor = 'var(--ash-light)';
    btn.title = 'Повтор трека — клик чтобы выключить';
    btn.classList.add('active');
  }
}

function updateUploadLabel(){
  const label = $('#uploadLabel');
  if(!label) return;
  if(activePlaylistId){
    const pl = playlists.find(p=>p.id===activePlaylistId);
    const name = pl ? pl.name : 'плейлист';
    label.textContent = `Загрузить в «${name}»`;
    label.insertAdjacentHTML('afterbegin', '<i class="ti ti-playlist-add"></i> ');
    label.title = `Файлы сразу попадут в плейлист «${name}» и в фонотеку`;
  } else if(pendingUploadPlaylistId){
    const pl = playlists.find(p=>p.id===pendingUploadPlaylistId);
    const name = pl ? pl.name : 'плейлист';
    label.textContent = `Загрузить в «${name}»`;
    label.insertAdjacentHTML('afterbegin', '<i class="ti ti-playlist-add"></i> ');
  } else {
    label.innerHTML = '<i class="ti ti-upload"></i> Загрузить';
    label.title = 'Загрузить в фонотеку';
  }
}
function updatePlayerHeart(){
  const btn = $('#likeBtn');
  if(!btn) return;
  // всегда видима
  btn.style.display='grid'; btn.style.visibility='visible'; btn.style.opacity='1';
  const cur = queue[currentIdx];
  if(!cur || currentIdx<0){
    btn.innerHTML='<i class="ti ti-heart"></i>';
    btn.style.color=''; btn.style.opacity='1'; btn.title='Добавить в Liked Songs';
    btn.classList.remove('active');
    return;
  }
  const liked = getLikedPlaylist();
  const inLiked = liked ? liked.tracks.some(t=>t.id===cur.id) : false;
  const inAny = playlists.some(pl=>pl.tracks.some(t=>t.id===cur.id));
  if(inLiked){
    btn.innerHTML='<i class="ti ti-heart-filled"></i>';
    btn.style.color='var(--ash-light)'; btn.style.opacity='1'; btn.title='Убрать из Liked Songs';
    btn.classList.add('active');
  } else if(inAny){
    btn.innerHTML='<i class="ti ti-heart-filled"></i>';
    btn.style.color='var(--ash-light)'; btn.style.opacity='1'; btn.title='В плейлисте — управление';
    btn.classList.add('active');
  } else {
    btn.innerHTML='<i class="ti ti-heart"></i>';
    btn.style.color=''; btn.style.opacity='1'; btn.title='Добавить в Liked Songs';
    btn.classList.remove('active');
  }
}

async function uploadFiles(files, targetPlaylistId){
  if(!files || !files.length) return;
  const targetId = targetPlaylistId ?? pendingUploadPlaylistId ?? activePlaylistId;
  const fd = new FormData();
  for(const f of files) fd.append('files', f);
  if(targetId) fd.append('playlist_id', String(targetId));
  const plName = targetId ? (playlists.find(p=>p.id===targetId)?.name || 'плейлист') : null;
  toast(targetId ? `Загрузка в «${plName}»...` : 'Загрузка...');
  try{
    const uploaded = await api('/api/upload', {method:'POST', body:fd});
    if(targetId){
      toast(`Загружено ${uploaded.length} трек(ов) в «${plName}»`);
    } else {
      toast('Загружено — добро пожаловать в пепел');
    }
    await loadTracks();
    await loadStats();
    await loadPlaylists();
    updateUploadLabel();
    // если загружали в активный плейлист — обновить отображение
    if(targetId && targetId===activePlaylistId){
      applyFilter();
      renderPlaylists();
    }
  }catch(err){ toast('Ошибка загрузки'); console.error(err); }
}

function handleEnded(){
  // вызывается при окончании трека
  if(repeatMode === 'one'){
    audio.currentTime = 0;
    audio.play().catch(()=>{});
    return;
  }
  let n = currentIdx + 1;
  if(n >= queue.length){
    if(repeatMode === 'all'){
      n = 0;
    } else {
      // off — останавливаемся в конце очереди
      $('#playBtn').innerHTML = '<i class="ti ti-player-play"></i>';
      return;
    }
  }
  playAt(n);
}

function next(){
  if(!queue.length) return;
  // ручной клик "следующий" — всегда идёт к следующему, даже в режиме one
  let n = currentIdx + 1;
  if(n >= queue.length){
    if(repeatMode === 'all' || repeatMode === 'one'){
      n = 0; // в обоих режимах с повтором — закольцевать
    } else {
      return; // off — в конце стоп
    }
  }
  playAt(n);
}
function prev(){
  if(audio.currentTime > 3){ audio.currentTime = 0; return; }
  let p = currentIdx - 1;
  if(p < 0){
    if(repeatMode === 'all' || repeatMode === 'one'){
      p = queue.length - 1;
    } else {
      p = 0; // off — не закольцовывать, остаться в начале
      if(currentIdx === 0){ audio.currentTime = 0; return; }
    }
  }
  playAt(p);
}

// events
$('#playBtn').addEventListener('click', togglePlay);
$('#nextBtn').addEventListener('click', next);
$('#prevBtn').addEventListener('click', prev);
$('#repeatBtn').addEventListener('click', ()=>{
  if(repeatMode === 'off') repeatMode = 'all';
  else if(repeatMode === 'all') repeatMode = 'one';
  else repeatMode = 'off';
  updateRepeatUI();
  const msg = repeatMode === 'off' ? 'Повтор выключен' : repeatMode === 'all' ? 'Повтор плейлиста' : 'Повтор трека';
  toast(msg);
  try{ localStorage.setItem('ash_repeat', repeatMode); }catch(e){}
});
audio.addEventListener('ended', handleEnded);
audio.addEventListener('timeupdate', ()=>{
  if(!audio.duration) return;
  const pct = (audio.currentTime/audio.duration)*100;
  $('#progress').value = pct;
  $('#timeCurrent').textContent = formatDuration(audio.currentTime);
  $('#timeTotal').textContent = formatDuration(audio.duration);
});
audio.addEventListener('play', ()=> $('#playBtn').innerHTML='<i class="ti ti-player-pause"></i>');
audio.addEventListener('pause',()=> $('#playBtn').innerHTML='<i class="ti ti-player-play"></i>');
$('#progress').addEventListener('input', (e)=>{
  if(!audio.duration) return;
  audio.currentTime = (e.target.value/100)*audio.duration;
});
let prevVolume = 0.85;
function saveVolume(){
  try{
    localStorage.setItem('ash_volume', String(audio.volume));
    localStorage.setItem('ash_muted', audio.muted ? '1' : '0');
    localStorage.setItem('ash_prevVolume', String(prevVolume));
  }catch(e){}
}
function updateVolumeIcon(){
  const icon = document.querySelector('.vol-icon i');
  if(!icon) return;
  const volIcon = document.querySelector('.vol-icon');
  if(audio.muted || audio.volume === 0){
    icon.className = 'ti ti-volume-off';
    volIcon.title = 'Включить звук';
    volIcon.style.color = 'var(--text-faint)';
  } else if(audio.volume < 0.35){
    icon.className = 'ti ti-volume-3';
    volIcon.title = 'Выключить звук';
    volIcon.style.color = '';
  } else if(audio.volume < 0.7){
    icon.className = 'ti ti-volume-2';
    volIcon.title = 'Выключить звук';
    volIcon.style.color = '';
  } else {
    icon.className = 'ti ti-volume';
    volIcon.title = 'Выключить звук';
    volIcon.style.color = '';
  }
  const volInput = $('#volume');
  if(volInput) volInput.value = Math.round(audio.volume * 100);
}
$('#volume').addEventListener('input', e=>{
  const v = e.target.value/100;
  audio.volume = v;
  audio.muted = v === 0;
  if(v > 0) prevVolume = v;
  updateVolumeIcon();
  saveVolume();
});
document.querySelector('.vol-icon').addEventListener('click', ()=>{
  if(audio.muted || audio.volume === 0){
    // unmute
    audio.muted = false;
    const restore = prevVolume > 0.05 ? prevVolume : 0.85;
    audio.volume = restore;
    $('#volume').value = Math.round(restore*100);
    toast('Звук включён');
  } else {
    prevVolume = audio.volume;
    audio.muted = true;
    toast('Без звука');
  }
  updateVolumeIcon();
  saveVolume();
});
audio.addEventListener('volumechange', ()=>{ updateVolumeIcon(); saveVolume(); });

// search debounce
let sTimer;
searchInput.addEventListener('input', ()=>{
  clearTimeout(sTimer);
  sTimer=setTimeout(()=>{ activePlaylistId=null; viewTitle.textContent='Поиск'; viewSubtitle.textContent=`«${searchInput.value}»`; loadTracks().then(saveViewState); saveViewState(); }, 350);
});
sortSelect.addEventListener('change', ()=>{ loadTracks().then(saveViewState); saveViewState(); });

$('#shuffleBtn').addEventListener('click', ()=>{
  filtered = [...filtered].sort(()=>Math.random()-0.5);
  queue=[...filtered];
  renderTracks();
  toast('Перемешано — как пепел на ветру');
});
$('#playAllBtn').addEventListener('click', ()=>{
  if(!filtered.length) return;
  queue=[...filtered];
  playAt(0);
});
$('#scanBtn').addEventListener('click', async ()=>{
  $('#scanBtn').innerHTML='<i class="ti ti-loader-2"></i> Сканирую...';
  const r = await api('/api/scan', {method:'POST'});
  toast(r.message);
  await loadTracks(); await loadStats(); await loadPlaylists();
  if(viewMode==='artists') await loadArtists();
  if(viewMode==='albums') await loadAlbums();
  $('#scanBtn').innerHTML='<i class="ti ti-refresh"></i> Скан';
});
$('#uploadInput').addEventListener('change', async (e)=>{
  const files = e.target.files;
  if(!files.length) return;
  await uploadFiles(files);
  pendingUploadPlaylistId = null;
  updateUploadLabel();
  e.target.value='';
});
// drag & drop в основную область — загрузка (в активный плейлист если выбран)
const mainArea = document.querySelector('.main');
if(mainArea){
  mainArea.addEventListener('dragover', e=>{ e.preventDefault(); mainArea.style.outline='1px dashed var(--ash-light)'; });
  mainArea.addEventListener('dragleave', ()=>{ mainArea.style.outline=''; });
  mainArea.addEventListener('drop', async e=>{
    e.preventDefault(); mainArea.style.outline='';
    const files = e.dataTransfer.files;
    if(files.length) await uploadFiles(files);
  });
  // сохраняем скролл для восстановления после перезагрузки
  let scrollTimer;
  mainArea.addEventListener('scroll', ()=>{
    clearTimeout(scrollTimer);
    scrollTimer = setTimeout(saveViewState, 250);
  });
  const sideEl = document.querySelector('.sidebar');
  if(sideEl){
    sideEl.addEventListener('scroll', ()=>{
      clearTimeout(scrollTimer);
      scrollTimer = setTimeout(saveViewState, 250);
    });
  }
  window.addEventListener('beforeunload', saveViewState);
}
// sidebar resizer
(function(){
  const sidebar = document.querySelector('.sidebar');
  const resizer = document.getElementById('sidebarResizer');
  if(!sidebar || !resizer) return;
  const KEY='ash_sidebar_width';
  const MIN=220, MAX=520, DEF=364;
  try{
    let saved=parseInt(localStorage.getItem(KEY),10);
    if(saved===300) { saved=364; localStorage.setItem(KEY, saved); }
    if(saved && saved>=MIN && saved<=MAX) sidebar.style.width=saved+'px';
  }catch(e){}
  let startX=0, startW=0, dragging=false;
  function onMove(e){
    if(!dragging) return;
    let nw=startW + (e.clientX - startX);
    nw=Math.max(MIN, Math.min(MAX, nw));
    sidebar.style.width=nw+'px';
    document.body.style.userSelect='none';
    document.body.style.cursor='col-resize';
  }
  function onUp(){
    if(!dragging) return;
    dragging=false;
    resizer.classList.remove('dragging');
    document.body.style.userSelect='';
    document.body.style.cursor='';
    try{ localStorage.setItem(KEY, parseInt(sidebar.style.width,10)); }catch(e){}
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  resizer.addEventListener('mousedown', (e)=>{
    e.preventDefault();
    dragging=true;
    startX=e.clientX;
    startW=sidebar.getBoundingClientRect().width;
    resizer.classList.add('dragging');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  });
  resizer.addEventListener('dblclick', ()=>{
    sidebar.style.width=DEF+'px';
    try{ localStorage.setItem(KEY, DEF); }catch(e){}
  });
})();

// nav
$$('.nav-item').forEach(btn=>{
  btn.addEventListener('click', async ()=>{
    $$('.nav-item').forEach(b=>b.classList.remove('active'));
    btn.classList.add('active');
    activePlaylistId=null;
    pendingUploadPlaylistId=null;
    updateUploadLabel();
    viewMode = btn.dataset.view;
    artistsView.classList.add('hidden');
    albumsView.classList.add('hidden');
    if(viewMode==='all'){
      viewTitle.textContent='Вся фонотека';
      viewSubtitle.textContent='Угольно-серый архив твоего звука';
      await loadTracks();
    } else if(viewMode==='recent'){
      viewTitle.textContent='Недавнее';
      viewSubtitle.textContent='Последние добавленные';
      await loadTracks();
    } else if(viewMode==='artists'){
      viewTitle.textContent='Исполнители';
      viewSubtitle.textContent='Выбери голос из пепла';
      artistsView.classList.remove('hidden');
      await loadArtists();
      filtered=[]; renderTracks();
    } else if(viewMode==='albums'){
      viewTitle.textContent='Альбомы';
      viewSubtitle.textContent='Сборники пыли и звука';
      albumsView.classList.remove('hidden');
      await loadAlbums();
      filtered=[]; renderTracks();
    }
    renderPlaylists();
    saveViewState();
  });
});

// playlists create
$('#newPlaylistBtn').addEventListener('click', ()=> $('#newPlaylistForm').classList.toggle('hidden'));
$('#createPlBtn').addEventListener('click', async ()=>{
  const name = $('#plName').value.trim();
  if(!name) return toast('Введи название');
  const color = $('#plColor').value;
  await api('/api/playlists', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, cover_color:color})});
  $('#plName').value='';
  $('#newPlaylistForm').classList.add('hidden');
  await loadPlaylists(); await loadStats();
  toast('Плейлист создан');
});

// picker — Liked Songs + управление плейлистами
let pickerTrackId = null;
function getLikedPlaylist(){ return playlists.find(p=>p.name===LIKED_SONGS_NAME); }
async function handleAddClick(tid){
  const liked = getLikedPlaylist();
  if(!liked){ toast('Liked Songs не найден'); return; }
  const inLiked = liked.tracks.some(t=>t.id===tid);
  if(!inLiked){
    // первый клик — сразу в Liked Songs
    try{
      await api(`/api/playlists/${liked.id}/tracks/${tid}`, {method:'POST'});
      toast('Добавлено в Liked Songs');
      // optimistic
      const t = tracks.find(x=>x.id===tid) || filtered.find(x=>x.id===tid);
      if(t && !liked.tracks.some(x=>x.id===tid)){
        liked.tracks.push(t);
        liked.track_count = liked.tracks.length;
      }
      renderPlaylists();
      renderTracks();
    }catch(e){ toast('Ошибка'); }
  } else {
    // уже в избранном — открываем менеджер
    openPlaylistManager(tid);
  }
}
function openPlaylistManager(tid){
  pickerTrackId = tid;
  const picker = $('#plPicker');
  const list = $('#pickerList');
  const t = tracks.find(x=>x.id===tid) || filtered.find(x=>x.id===tid);
  const title = t ? `${escapeHtml(t.title)} — ${escapeHtml(t.artist)}` : 'Выберите плейлисты';
  picker.querySelector('h4').innerHTML = `<i class="ti ti-playlist-add"></i> Добавить в плейлист <span style="opacity:.6;font-weight:400;font-size:11px;display:block;margin-top:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:320px">${title}</span>`;
  // Spotify-like: поиск по плейлистам + список с чекмарками + кнопка создать
  const searchHtml = `<div style="margin-bottom:10px"><input id="plSearch" placeholder="Найти плейлист" style="width:100%;background:#2a2a2a;border:1px solid #3a3a3a;color:#fff;padding:8px 10px;border-radius:6px;font-size:12px;outline:none"></div>`;
  const itemsHtml = playlists.map(p=>{
    const checked = p.tracks.some(t=>t.id===tid);
    const isLiked = p.name===LIKED_SONGS_NAME;
    const icon = isLiked ? '<i class="ti ti-heart-filled" style="color:var(--ash-light)"></i>' : `<div style="width:28px;height:28px;border-radius:4px;background:${sanitizeColor(p.cover_color)};display:grid;place-items:center;font-size:12px;color:#fff">${escapeHtml(p.name[0]||'P')}</div>`;
    const check = checked ? '<i class="ti ti-check" style="color:#1db954;font-size:16px"></i>' : '<span style="width:16px"></span>';
    const nameEsc = escapeHtml(p.name);
    return `<div class="spotify-row" data-pick="${p.id}" style="display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:6px;cursor:pointer;hover:background:#2a2a2a" data-checked="${checked}">
      ${icon}
      <span style="flex:1;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:13px">${nameEsc}</span>
      <span style="opacity:.5;font-size:11px">${p.track_count}</span>
      ${check}
    </div>`;
  }).join('');
  const createHtml = `<div id="plCreateRow" style="display:flex;align-items:center;gap:10px;padding:10px 10px;border-radius:6px;cursor:pointer;margin-top:8px;border-top:1px solid #2a2a2a"><i class="ti ti-plus" style="background:#fff;color:#000;border-radius:50%;width:28px;height:28px;display:grid;place-items:center"></i> <span style="font-size:13px">Создать плейлист</span></div>`;
  list.innerHTML = searchHtml + `<div id="plRows" style="max-height:240px;overflow-y:auto">` + itemsHtml + `</div>` + createHtml;
  picker.classList.remove('hidden');
  // поиск фильтр
  const searchInp = list.querySelector('#plSearch');
  if(searchInp){
    searchInp.addEventListener('input', ()=>{
      const q = searchInp.value.toLowerCase();
      list.querySelectorAll('.spotify-row').forEach(row=>{
        const pid = Number(row.dataset.pick);
        const pl = playlists.find(p=>p.id===pid);
        row.style.display = pl.name.toLowerCase().includes(q) ? '' : 'none';
      });
    });
    setTimeout(()=>searchInp.focus(), 30);
  }
  // Spotify: клик по строке — мгновенно toggle (без Save)
  list.querySelectorAll('.spotify-row').forEach(row=>{
    row.addEventListener('click', async ()=>{
      const pid = Number(row.dataset.pick);
      const wasChecked = row.dataset.checked === 'true';
      row.style.opacity = '0.6';
      try{
        if(wasChecked){
          await api(`/api/playlists/${pid}/tracks/${tid}`, {method:'DELETE'});
          row.dataset.checked = 'false';
          row.querySelector('.ti-check')?.replaceWith(Object.assign(document.createElement('span'),{style:'width:16px'}));
          toast('Убрано');
        } else {
          await api(`/api/playlists/${pid}/tracks/${tid}`, {method:'POST'});
          row.dataset.checked = 'true';
          const check = document.createElement('i');
          check.className='ti ti-check'; check.style.color='#1db954'; check.style.fontSize='16px';
          row.lastElementChild.replaceWith(check);
          toast('Добавлено');
        }
        await loadPlaylists();
        renderTracks();
        updatePlayerHeart();
        if(activePlaylistId) applyFilter();
      }catch(e){ toast('Ошибка'); }
      row.style.opacity = '';
    });
    row.addEventListener('mouseenter', ()=> row.style.background='#2a2a2a');
    row.addEventListener('mouseleave', ()=> row.style.background='transparent');
  });
  // создать плейлист быстро
  const createRow = list.querySelector('#plCreateRow');
  if(createRow){
    createRow.addEventListener('click', async ()=>{
      const name = prompt('Название нового плейлиста:');
      if(!name) return;
      try{
        const pl = await api('/api/playlists', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name, cover_color:'#1db954'})});
        toast('Плейлист создан');
        await loadPlaylists();
        // сразу добавляем трек в новый плейлист
        await api(`/api/playlists/${pl.id}/tracks/${tid}`, {method:'POST'});
        toast('Добавлено в '+name);
        await loadPlaylists();
        openPlaylistManager(tid); // перерисуем
      }catch(e){ toast('Ошибка создания'); }
    });
  }
  // биндим Save/Cancel один раз (Save теперь просто закрывает, т.к. уже мгновенно)
  const saveBtn = $('#pickerSave');
  const cancelBtn = $('#pickerCancel');
  if(saveBtn && !saveBtn._bound){
    saveBtn._bound = true;
    saveBtn.textContent = 'Готово';
    saveBtn.addEventListener('click', async ()=>{
      picker.classList.add('hidden');
      await loadPlaylists();
      if(activePlaylistId) applyFilter(); else renderTracks();
      updatePlayerHeart();
    });
    cancelBtn.addEventListener('click', ()=> picker.classList.add('hidden'));
    // также клик вне закрывает, но изменения уже применены мгновенно, так что просто закрываем
  }
}
function openPicker(tid){ openPlaylistManager(tid); }
document.addEventListener('click', (e)=>{
  if(!e.target.closest('#plPicker') && !e.target.closest('.add-btn') && !e.target.closest('#likeBtn')){
    $('#plPicker').classList.add('hidden');
  }
});
$('#likeBtn').addEventListener('click', async ()=>{
  if(currentIdx<0 || !queue[currentIdx]) return toast('Ничего не играет');
  const tid = queue[currentIdx].id;
  const liked = getLikedPlaylist();
  if(!liked) return;
  const inLiked = liked.tracks.some(t=>t.id===tid);
  try{
    if(inLiked){
      await api(`/api/playlists/${liked.id}/tracks/${tid}`, {method:'DELETE'});
      toast('Убрано из Liked Songs');
      liked.tracks = liked.tracks.filter(t=>t.id!==tid);
      liked.track_count = liked.tracks.length;
    } else {
      await api(`/api/playlists/${liked.id}/tracks/${tid}`, {method:'POST'});
      toast('Добавлено в Liked Songs');
      const t = tracks.find(x=>x.id===tid) || queue.find(x=>x.id===tid);
      if(t) { liked.tracks.push(t); liked.track_count = liked.tracks.length; }
    }
    renderTracks();
    renderPlaylists();
    updatePlayerHeart();
  }catch(e){ toast('Ошибка'); }
});

// keyboard
document.addEventListener('keydown', (e)=>{
  if(e.target.tagName==='INPUT') return;
  if(e.code==='Space'){ e.preventDefault(); togglePlay(); }
  if(e.code==='KeyM'){ e.preventDefault(); document.querySelector('.vol-icon').click(); }
});

// init
(async()=>{
  audio.volume = 0.85;
  prevVolume = audio.volume;
  try{
    const saved = localStorage.getItem('ash_repeat');
    if(saved === 'all' || saved === 'one' || saved === 'off') repeatMode = saved;
    const v = localStorage.getItem('ash_volume');
    const m = localStorage.getItem('ash_muted');
    const pv = localStorage.getItem('ash_prevVolume');
    if(pv !== null && !isNaN(parseFloat(pv))) prevVolume = parseFloat(pv);
    if(v !== null && !isNaN(parseFloat(v))){
      const vol = Math.max(0, Math.min(1, parseFloat(v)));
      audio.volume = vol;
      const volInput = document.getElementById('volume');
      if(volInput) volInput.value = Math.round(vol*100);
    }
    if(m === '1') audio.muted = true;
  }catch(e){}
  updateRepeatUI();
  updateVolumeIcon();
  // восстанавливаем сортировку и поиск до загрузки треков
  const savedState = getSavedState();
  if(savedState){
    try{
      if(savedState.sort && sortSelect) sortSelect.value = savedState.sort;
      if(savedState.search && searchInput) searchInput.value = savedState.search;
    }catch(e){}
  }
  await loadPlaylists();
  await loadTracks();
  await loadStats();
  // восстанавливаем плейлист/вид/скролл после загрузки данных
  if(savedState){
    try{
      if(savedState.viewMode) viewMode = savedState.viewMode;
      if(savedState.activePlaylistId){
        const exists = playlists.find(p=>p.id===savedState.activePlaylistId);
        if(exists){
          activePlaylistId = savedState.activePlaylistId;
          viewMode = 'playlist';
          const pl = exists;
          viewTitle.textContent = pl.name;
          viewSubtitle.textContent = pl.description || `${pl.track_count} треков • пепельная подборка`;
          $('#artistsView').classList.add('hidden');
          $('#albumsView').classList.add('hidden');
          document.querySelectorAll('.nav-item').forEach(n=>n.classList.remove('active'));
          applyFilter();
          renderPlaylists();
          updateUploadLabel();
        } else {
          // плейлист удалён — сбрасываем на фонотеку
          activePlaylistId = null;
          viewMode = 'all';
        }
      }
      // nav active
      if(viewMode && viewMode!=='playlist'){
        document.querySelectorAll('.nav-item').forEach(n=>{
          n.classList.toggle('active', n.dataset.view===viewMode);
        });
        if(savedState.search){
          viewTitle.textContent='Поиск';
          viewSubtitle.textContent=`«${savedState.search}»`;
        } else if(viewMode==='artists'){
          artistsView.classList.remove('hidden');
          await loadArtists();
          filtered=[]; renderTracks();
        } else if(viewMode==='albums'){
          albumsView.classList.remove('hidden');
          await loadAlbums();
          filtered=[]; renderTracks();
        } else if(viewMode==='recent'){
          viewTitle.textContent='Недавнее';
          viewSubtitle.textContent='Последние добавленные';
          applyFilter();
        } else if(viewMode==='all'){
          viewTitle.textContent='Вся фонотека';
          viewSubtitle.textContent='Угольно-серый архив твоего звука';
        }
        if(viewMode!=='artists' && viewMode!=='albums'){
          // уже отрендерено через applyFilter/load
        }
      }
      // скролл
      requestAnimationFrame(()=>{
        setTimeout(()=>{
          const mainEl = document.querySelector('.main');
          const sideEl = document.querySelector('.sidebar');
          if(mainEl && savedState.scrollMain) mainEl.scrollTop = savedState.scrollMain;
          if(sideEl && savedState.scrollSide) sideEl.scrollTop = savedState.scrollSide;
        }, 80);
      });
    }catch(e){ console.error('restore state failed', e); }
  }
})();
