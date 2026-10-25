'use strict';
const $ = id => document.getElementById(id);
const Music = window.ScoreMusic;
const state = { events: [], anchors: [], pages:[], currentPage:0, duration: 0, beat: 0, playing: false, busy: false, image: null, zoom: 1, runtime: false, demo: false, hasSource: false,canExportXML:true };
const api = async p => { const r = await p; if (!r.ok) throw new Error(r.error); return r.value; };
let toastTimer;
function toast(message, error = false) { $('toast').textContent = message; $('toast').classList.toggle('error', error); $('toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').hidden = true, error ? 10000 : 4200); }
function bind(id, fn, event = 'click') { $(id).addEventListener(event, async e => { try { await fn(e); } catch (error) { toast(error.message, true); } }); }
const formatTime = seconds => `${Math.floor(seconds / 60).toString().padStart(2,'0')}:${Math.floor(seconds % 60).toString().padStart(2,'0')}`;
const tempo = () => Math.max(30, Math.min(300, Number($('tempo').value) || 120));

class SamplePlayer {
  constructor() { this.context = null; this.voices = new Set(); this.sample = null; this.sampleBpm = 120; }
  async prepare() {
    if (!this.context) {
      this.context = new AudioContext({ latencyHint: 'interactive' });
      this.gain = this.context.createGain(); this.gain.gain.value = .65;
      const limiter = this.context.createDynamicsCompressor(); limiter.threshold.value = -10; limiter.ratio.value = 4;
      this.gain.connect(limiter); limiter.connect(this.context.destination);
    }
    await this.context.resume(); this.gain.gain.value = Number($('volume').value) / 100;
  }
  async play(beat) {
    this.stop(); await this.prepare();
    if (!this.sample) throw new Error('音色尚未加载完成，请稍候');
    this.startBeat = beat; this.bpm = tempo(); this.startTime = this.context.currentTime + .025;
    const source = this.context.createBufferSource(); source.buffer = this.sample;
    source.playbackRate.value = this.bpm / this.sampleBpm; source.connect(this.gain);
    source.start(this.startTime, Math.min(this.sample.duration-.001,beat*60/this.sampleBpm));
    this.voices.add(source); source.onended=()=>{this.voices.delete(source);source.disconnect();};
    state.playing = true; state.beat = beat; updateButtons();
  }
  position() { return this.startBeat + Math.max(0, this.context.currentTime - this.startTime) * this.bpm / 60; }
  stop() {
    if (state.playing && this.context) state.beat = Math.min(state.duration, this.position());
    for (const source of this.voices) { try { source.stop(); } catch {} } this.voices.clear(); state.playing = false;
  }
}
const player = new SamplePlayer();
let soundGeneration=0;
async function prepareSound(resume=false) {
  const generation=++soundGeneration,wasPlaying=resume&&state.playing;
  player.stop(); state.soundLoading=true; updateButtons();
  $('sound-status').textContent='正在加载采样音色…';
  try {
    const response=await api(window.scoreflow.renderAudio(Number($('instrument').value),tempo()));
    await player.prepare();
    const bytes=response.bytes;
    const audio=await player.context.decodeAudioData(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
    if(generation!==soundGeneration)return;
    player.sample=audio; player.sampleBpm=response.bpm;
    $('sound-status').textContent=`${response.name} · GeneralUser GS 采样音色`;
    state.soundLoading=false;updateButtons();
    if(wasPlaying)await player.play(state.beat);
  } catch(e) {
    if(generation===soundGeneration){state.soundLoading=false;player.sample=null;$('sound-status').textContent='音色加载失败，点击播放可重试';updateButtons();}
    throw e;
  }
}

function updateButtons() {
  const playable = state.events.length > 0 && !state.busy && !state.soundLoading;
  $('play').disabled = !playable; $('rewind').disabled = !playable; $('seek').disabled = !playable;
  $('play').classList.toggle('playing', state.playing); $('play-symbol').setAttribute('href', state.playing ? '#i-pause' : '#i-play');
  $('recognize').disabled = !state.hasSource || state.busy || !state.runtime;
  $('recognize').hidden = state.busy; $('cancel').hidden = !state.busy; $('progress').hidden = !state.busy;
  for (const id of ['import', 'append', 'empty-import', 'demo', 'meter', 'mode', 'runtime', 'instrument']) $(id).disabled = state.busy;
  for (const id of ['export-top','export-midi','export-xml']) $(id).disabled = !state.events.length || state.demo || state.busy;
  $('export-xml').disabled ||= !state.canExportXML;
  renderPageControls();
}
function renderPageControls(){
  const pages=state.pages;
  $('page-toolbar').hidden=!pages.length||state.demo;
  $('page-count').textContent=`${pages.length} 页`;
  const selected=String(state.currentPage),list=$('page-select');
  if(list.options.length!==pages.length||[...list.options].some((o,i)=>o.dataset.pageId!==pages[i]?.id)){
    list.replaceChildren(...pages.map((page,index)=>{const o=document.createElement('option');o.value=index;o.dataset.pageId=page.id||String(index);return o;}));
  }
  [...list.options].forEach((option,index)=>option.textContent=`${index+1}. ${pages[index].name}${pages[index].status==='recognized'?' · 已识别':pages[index].status==='working'?' · 识别中':''}`);
  list.value=selected;list.disabled=state.busy;
  $('page-prev').disabled=state.busy||state.currentPage<=0;
  $('page-next').disabled=state.busy||state.currentPage>=pages.length-1;
  $('page-left').disabled=state.busy||state.currentPage<=0;
  $('page-right').disabled=state.busy||state.currentPage>=pages.length-1;
  $('page-remove').disabled=state.busy||pages.length<=1;
}
function showPage(index){
  if(index<0||index>=state.pages.length)return;
  state.currentPage=index;const page=state.pages[index];state.image=page;
  $('score-image').src=page.dataURL;$('page').hidden=false;$('empty').hidden=true;
  $('filename').textContent=`${state.pages.length>1?`${index+1}/${state.pages.length} · `:''}${page.name}`;$('filename').title=page.name;
  $('image-size').textContent=`${page.width} × ${page.height}`;
  $('score-overlay').setAttribute('viewBox',`0 0 1920 ${page.height*1920/page.width}`);
  const start=Music.rational(page.start||0);
  state.anchors=Music.anchorsFor(Music.normalizeEvents(page.events||[]),page.geometry||[],page.width).map(a=>({...a,beat:a.beat+start,page:index}));
  const approximate=page.route?.engine==='tabbox'||state.anchors.some(a=>a.approximate);
  $('score-hint').textContent=state.anchors.length?`第 ${index+1}/${state.pages.length} 页 · 点击音符定位整曲${approximate?' · 六线谱落点为近似位置':''}`:state.events.length?'此页缺少坐标，可用整曲时间轴定位':'可调整页序；一次识别后自动连接完整曲目';
  $('score-scroll').scrollTop=0;$('score-scroll').scrollLeft=0;lastAnchor=null;lastFollow=0;
  buildOverlay();renderPageControls();
}
function selectPage(index){
  player.stop();showPage(index);
  if(state.events.length)state.beat=Music.rational(state.pages[index].start||0);
  updatePosition();updateButtons();
}
function clearPlayback() {
  player.stop(); player.sample=null; soundGeneration++; state.soundLoading=false; state.beat = 0; state.events = []; state.anchors = []; state.duration = 0; $('seek').value = 0;
  $('roll-empty').hidden = false; $('score-overlay').replaceChildren();
  for (const id of ['stat-layout','stat-notes','stat-meter','stat-tempo']) $(id).textContent = '—';
  $('note-count').textContent = '等待识别'; $('review').hidden = true; $('demo-notice').hidden = true;
  $('play-status').textContent = '准备好，听见你的谱面。'; $('position-label').textContent = '识别完成后，点击谱面即可定位播放';
  drawRoll(); updateButtons(); updatePosition();
}
function displayImage(data) {
  clearPlayback(); state.image = data; state.hasSource = !data.demo; state.demo = !!data.demo; state.zoom = 1;
  state.pages=(data.pages?.length?data.pages:[{...data,id:'single',index:0,start:0}]).map((p,i)=>({...p,id:p.id||String(i),index:i}));state.currentPage=0;
  $('route-description').textContent=state.pages.length>1?`${state.pages.length} 页将按页序串行识别，再连接完整曲目`:'混合谱默认识别五线谱，也可手动切换为六线谱。';
  $('demo-label').hidden = !data.demo;
  showPage(0);setZoom(1);updateButtons();
}
const layoutName = layout => ({ five_only: '五线谱', six_only: '六线谱 · 优化中', mixed_5_6: '五线谱 + 六线谱' }[layout] || '谱面');
function displayResult(data) {
  displayImage(data); state.events = Music.normalizeEvents(data.events); state.duration = Math.max(Music.duration(state.events),Music.rational(data.duration||0));state.canExportXML=data.canExportXML!==false;
  if(!data.pages?.length)state.pages[0]={...state.pages[0],events:state.events,geometry:data.geometry||[],route:data.route,start:0,duration:state.duration};
  showPage(0);
  $('seek').max = state.duration; $('tempo').value = Math.round(data.bpm || 120);
  $('stat-layout').textContent = data.demo ? '原创播放示例' : state.pages.length>1?`完整曲目 · ${state.pages.length} 页`:layoutName(state.pages[0].route?.layout||data.route?.layout);
  $('stat-notes').textContent = `${state.events.length} 个`;
  $('stat-meter').textContent = data.meters?.length ? data.meters[0].meter.join('/') + (data.meters.length > 1 ? ' · 变拍号' : '') : '未确认';
  $('stat-tempo').textContent = `${Math.round(data.bpm || 120)} 拍/分`;
  $('note-count').textContent = `${state.events.length} 个音符 · ${state.duration.toFixed(1)} 拍`;
  $('roll-empty').hidden = true;
  $('demo-notice').hidden = !data.demo;
  $('route-description').textContent = data.demo ? '内置播放示例，未运行识别' : state.pages.length>1?`${state.pages.length} 页已按页序连接，播放时自动翻页` : data.route?.engine === 'tabbox' ? '六线谱模型识别 · 支持混合页，持续优化中' : data.route?.layout === 'mixed_5_6' ? '已隔离六线谱区域，使用优化后的五线谱链路' : '五线谱模型 + 现有校正链路';
  const messages = [], flags = data.reviewFlags || [];
  if (data.route?.layout === 'six_only') messages.push('六线谱仍在优化，建议核对弦品、节奏及近似定位。');
  const known = { decode_truncated: '六线谱解码可能未完整结束', bar_count_mismatch: '识别小节数与谱面检测数不一致', meter_unconfirmed: '部分小节拍号未确认', bar_duration_mismatch: '部分小节时值与拍号不一致', muted_note_audio_unavailable: '含无法按音高试听的闷音' };
  for (const type of new Set(flags.map(f => f.type))) if (known[type]) messages.push(known[type]);
  const other = flags.filter(f => !known[f.type] && !['mixed_staff_mask_primary','approximate_tab_geometry','user_meter_override','staff_pixel_barlines_used'].includes(f.type));
  if (other.length) messages.push(`另有 ${other.length} 项校正复核提示，详见识别结果文件夹。`);
  if(!state.canExportXML)messages.push('页间声部数量不同，整曲 MIDI 已保存；MusicXML 请使用各页文件。');
  $('review').hidden = !messages.length; $('review').textContent = [...new Set(messages)].join('\n');
  $('play-status').textContent = data.demo ? '原创旋律 · 播放示例' : '识别完成，试听你的谱面。';
  $('position-label').textContent = state.anchors.length ? '点击谱面或时间轴，从任意位置开始' : '点击时间轴，从任意位置开始';
  buildOverlay(); drawRoll(); updateButtons(); updatePosition(); prepareSound().catch(e=>toast(e.message,true));
}
function setZoom(value) {
  state.zoom = Math.min(2.5, Math.max(.6, value)); $('page').style.width = `${state.zoom * 100}%`;
  $('zoom-value').textContent = Math.abs(state.zoom - 1) < .01 ? '适应宽度' : `${Math.round(state.zoom * 100)}%`;
}
function svgNode(name, attributes) { const node = document.createElementNS('http://www.w3.org/2000/svg', name); for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value); return node; }
let cursorLine, overlayRings = [];
function buildOverlay() {
  const overlay = $('score-overlay'); overlay.replaceChildren(); overlayRings = [];
  for (const a of state.anchors) {
    const ring = svgNode('circle', { cx: a.x, cy: a.y, r: 16, fill: '#c0d7ae', 'fill-opacity': '0', stroke: '#729f56', 'stroke-opacity': '0', 'stroke-width': 2, 'pointer-events': 'none' });
    overlay.append(ring); overlayRings.push({ ring, a });
  }
  cursorLine = svgNode('line', { x1: 0, x2: 0, y1: 0, y2: 0, stroke: '#d3a550', 'stroke-width': 3, 'pointer-events': 'none', opacity: 0 }); overlay.append(cursorLine);
}
let lastAnchor = null, lastFollow = 0;
function updateOverlay() {
  const active = state.anchors.filter(a => a.beat <= state.beat + .001 && a.beat + a.duration > state.beat + .001);
  for (const { ring, a } of overlayRings) { const on = active.includes(a); ring.setAttribute('fill-opacity', on ? '.38' : '0'); ring.setAttribute('stroke-opacity', on ? '.9' : '0'); }
  const before = state.anchors.filter(a => a.beat <= state.beat + .001);
  const anchor = before.length ? before.reduce((m, a) => a.beat > m.beat ? a : m) : state.anchors[0];
  if (!anchor || !cursorLine) return;
  const next = state.anchors.find(a => a.beat > anchor.beat + .001);
  const sameRow = next && Math.abs(next.y - anchor.y) < 75 && (next.staff == null || anchor.staff == null || next.staff === anchor.staff);
  const ratio = sameRow ? Math.max(0, Math.min(1, (state.beat - anchor.beat) / (next.beat - anchor.beat))) : 0;
  const x = anchor.x + (sameRow ? (next.x - anchor.x) * ratio : 0);
  const row = state.anchors.filter(a => Math.abs(a.y - anchor.y) < 65);
  cursorLine.setAttribute('x1', x); cursorLine.setAttribute('x2', x);
  cursorLine.setAttribute('y1', Math.min(...row.map(a => a.y)) - 45); cursorLine.setAttribute('y2', Math.max(...row.map(a => a.y)) + 45); cursorLine.setAttribute('opacity', '.95');
  if (state.playing && $('follow').checked && anchor !== lastAnchor && performance.now() - lastFollow > 400) {
    const scale = $('page').clientWidth / 1920, target = anchor.y * scale + $('page').offsetTop;
    const scroller = $('score-scroll');
    if (target < scroller.scrollTop + 60 || target > scroller.scrollTop + scroller.clientHeight - 65) scroller.scrollTo({ top: Math.max(0, target - scroller.clientHeight / 2), behavior: 'smooth' });
    if (x * scale > scroller.scrollLeft + scroller.clientWidth - 40 || x * scale < scroller.scrollLeft + 30) scroller.scrollTo({ left: Math.max(0, x * scale - scroller.clientWidth / 2), behavior: 'smooth' });
    lastFollow = performance.now();
  }
  lastAnchor = anchor;
}
let rollMetrics = { width: 0, beatWidth: 46, left: 40 };
function drawRoll() {
  const canvas = $('roll'), h = $('roll-scroll').clientHeight - 1;
  const beatWidth = Math.min(46, 15900 / Math.max(16, state.duration));
  const width = Math.max($('roll-scroll').clientWidth, 40 + Math.max(16, state.duration) * beatWidth);
  const dpr = devicePixelRatio || 1; canvas.width = Math.round(width * dpr); canvas.height = Math.round(h * dpr); canvas.style.width = `${width}px`; canvas.style.height = `${h}px`;
  const ctx = canvas.getContext('2d'); ctx.scale(dpr, dpr); rollMetrics = { width, beatWidth, left: 40 };
  ctx.fillStyle = '#fbfcf8'; ctx.fillRect(0,0,width,h);
  const low = state.events.length ? Math.min(...state.events.map(e => e.pitch)) - 2 : 48;
  const high = state.events.length ? Math.max(...state.events.map(e => e.pitch)) + 2 : 72;
  const rows = Math.max(12, high - low + 1), rh = (h - 20) / rows;
  ctx.font = '8px Segoe UI';
  for (let pitch = low; pitch <= low + rows; pitch++) {
    const y = 20 + (low + rows - pitch - 1) * rh, black = [1,3,6,8,10].includes(pitch % 12);
    ctx.fillStyle = black ? '#f0f3eb' : '#fbfcf8'; ctx.fillRect(40,y,width-40,rh);
    ctx.fillStyle = black ? '#cbd3c1' : '#e7ecdf'; ctx.fillRect(0,y,37,rh - .4);
    if (pitch % 12 === 0) { ctx.fillStyle = '#829371'; ctx.fillText(`C${Math.floor(pitch / 12) - 1}`, 8,y+rh*.85); }
  }
  for (let beat = 0; beat <= Math.max(16,state.duration); beat++) {
    const x = 40 + beat*beatWidth; ctx.strokeStyle = beat % 4 === 0 ? '#d6dfcd' : '#e7ecdf'; ctx.lineWidth = .6; ctx.beginPath(); ctx.moveTo(x,0); ctx.lineTo(x,h); ctx.stroke();
    if (beat % 4 === 0) { ctx.fillStyle = '#9ba88d'; ctx.fillText(`${beat + 1}`, x+5,12); }
  }
  for (const e of state.events) {
    const x = 40+e.start*beatWidth, y = 20 + (low + rows - e.pitch - 1)*rh;
    ctx.fillStyle = '#7b9f68'; ctx.beginPath(); ctx.roundRect(x+1,y+.7,Math.max(3,e.duration*beatWidth-2),Math.max(2,rh-1.5),2); ctx.fill();
  }
  for(const [i,page]of state.pages.entries())if(i>0&&page.start!=null){const x=40+Music.rational(page.start)*beatWidth;ctx.strokeStyle='#a9bd95';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();ctx.fillStyle='#819574';ctx.fillText(`第${i+1}页`,x+4,h-4);}
  $('roll-head').hidden = !state.events.length;
  $('roll-head').style.left = `${40+state.beat*beatWidth}px`;
}
let lastRollBeat = -1;
function updatePosition() {
  $('seek').value = state.beat; $('time-current').textContent = formatTime(state.beat * 60 / tempo()); $('time-total').textContent = formatTime(state.duration * 60 / tempo());
  $('beat-label').textContent = `${state.beat.toFixed(1)} 拍`; $('end-label').textContent = `${state.duration.toFixed(1)} 拍`;
  if (state.events.length) {
    if(state.playing&&$('follow').checked){const pageIndex=Music.pageAt(state.pages,state.beat);if(pageIndex!==state.currentPage)showPage(pageIndex);}
    updateOverlay();
    $('roll-head').style.left = `${40+state.beat*rollMetrics.beatWidth}px`;
    if (state.playing && $('follow').checked) { const x=40+state.beat*rollMetrics.beatWidth, pane=$('roll-scroll'); if(x>pane.scrollLeft+pane.clientWidth-25 || x<pane.scrollLeft+40) pane.scrollLeft=Math.max(0,x-100); }
  }
}
async function seekTo(beat, play = true) {
  if (!state.events.length || state.busy || state.soundLoading) return;
  player.stop(); state.beat = Math.min(state.duration, Math.max(0, beat));
  if($('follow').checked){const index=Music.pageAt(state.pages,state.beat);if(index!==state.currentPage)showPage(index);}
  if (play && state.beat < state.duration) await player.play(state.beat);
  updatePosition(); updateButtons();
}
async function togglePlay() {
  if (!state.events.length || state.busy || state.soundLoading) return;
  if (!player.sample) await prepareSound();
  if (state.playing) player.stop(); else await player.play(state.beat >= state.duration - .001 ? 0 : state.beat);
  updatePosition(); updateButtons();
}
async function importFile(append=false) { const data = await api(window.scoreflow.openImage(append)); if (data) { displayImage(data); toast(`已导入 ${state.pages.length} 页，可调整页序后开始识别`); } }
for (const id of ['import','empty-import']) bind(id, ()=>importFile(false));
bind('append',()=>importFile(true));
bind('page-select',()=>selectPage(Number($('page-select').value)),'change');
bind('page-prev',()=>selectPage(state.currentPage-1));bind('page-next',()=>selectPage(state.currentPage+1));
async function editPageOrder(direction){
  const ids=state.pages.map(p=>p.id),current=state.currentPage,id=ids[current];
  if(direction===0)ids.splice(current,1);else [ids[current],ids[current+direction]]=[ids[current+direction],ids[current]];
  const data=await api(window.scoreflow.editPages(ids));displayImage(data);
  const index=state.pages.findIndex(p=>p.id===id);showPage(index>=0?index:Math.min(current,state.pages.length-1));
  toast('页序已更新。再次识别会复用已完成页的结果。');
}
bind('page-left',()=>editPageOrder(-1));bind('page-right',()=>editPageOrder(1));bind('page-remove',()=>editPageOrder(0));
bind('demo', async () => { displayResult(await api(window.scoreflow.loadDemo())); toast('播放示例已载入，可点击谱面或按空格试听'); });
bind('recognize', async () => {
  player.stop(); clearPlayback(); state.busy = true; updateButtons(); $('progress-text').textContent = '正在准备谱面…';
  try { const data = await api(window.scoreflow.recognize({ meter: $('meter').value, mode: $('mode').value })); displayResult(data); toast(`${data.pages?.length||1} 页识别完成，已连接整曲，MIDI 已自动保存`); }
  catch (e) { $('play-status').textContent = e.message.includes('取消') ? '识别已取消，可再次开始。' : '本次识别未完成'; throw e; }
  finally { state.busy = false; updateButtons(); }
});
bind('cancel', async () => { $('cancel').disabled = true; await api(window.scoreflow.cancel()); $('cancel').disabled = false; });
bind('play', togglePlay); bind('rewind', () => seekTo(0, state.playing));
bind('seek', () => seekTo(Number($('seek').value), true), 'change');
bind('seek', () => { player.stop(); state.beat=Number($('seek').value); updatePosition(); updateButtons(); }, 'input');
bind('score-overlay', e => { const rect=$('score-overlay').getBoundingClientRect(); const anchor=Music.nearestAnchor(state.anchors,(e.clientX-rect.left)*1920/rect.width,(e.clientY-rect.top)*1920/rect.width); if(anchor) return seekTo(anchor.beat,true); });
bind('roll', e => { const rect=$('roll').getBoundingClientRect(); return seekTo((e.clientX-rect.left-rollMetrics.left)/rollMetrics.beatWidth,true); });
bind('tempo', async () => { const playing=state.playing; player.stop(); $('tempo').value=tempo(); if(state.events.length) await prepareSound(); if(playing) await player.play(state.beat); updatePosition(); updateButtons(); }, 'change');
bind('instrument', async () => { localStorage.setItem('scoreflow-instrument',$('instrument').value); if(state.events.length) await prepareSound(true); }, 'change');
const savedInstrument=localStorage.getItem('scoreflow-instrument'); if([...$('instrument').options].some(o=>o.value===savedInstrument)) $('instrument').value=savedInstrument;
bind('volume', () => { if(player.gain) player.gain.gain.setTargetAtTime(Number($('volume').value)/100,player.context.currentTime,.02); }, 'input');
bind('zoom-out', () => setZoom(state.zoom-.15)); bind('zoom-in', () => setZoom(state.zoom+.15));
for (const [id,kind] of [['export-top','midi'],['export-midi','midi'],['export-xml','musicxml']]) bind(id, async () => { const name=await api(window.scoreflow.exportFile(kind,Number($('instrument').value))); if(name) toast(`已导出 ${name}`); });
bind('results', () => api(window.scoreflow.openResults()));
bind('runtime', async () => { const info=await api(window.scoreflow.chooseRuntime()); setRuntime(info); toast(info.message,!info.ready); });
function setRuntime(info) { state.runtime=info.ready; $('runtime-label').textContent=info.ready?'模型环境已就绪':'配置模型运行环境'; $('runtime-label').title=info.message; updateButtons(); }
window.scoreflow.onProgress(data => { $('progress-text').textContent=data.message || '正在识别…';if(data.stage==='error'){for(const page of state.pages)if(page.status==='working')page.status='pending';renderPageControls();}if(data.pageId){const index=state.pages.findIndex(p=>p.id===data.pageId);if(index>=0){if(data.stage==='page-start'){state.pages[index].status='working';showPage(index);}if(data.stage==='page-done')state.pages[index].status='recognized';renderPageControls();}} });
document.addEventListener('keydown', e => { if(['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName)) return; if(e.code==='Space'){e.preventDefault();togglePlay().catch(x=>toast(x.message,true));} if(e.ctrlKey&&e.key.toLowerCase()==='o'){e.preventDefault();if(!state.busy)importFile().catch(x=>toast(x.message,true));} });
let dragCount=0;
document.addEventListener('dragenter', e=>{e.preventDefault();if(!state.busy){dragCount++;$('drop-zone').hidden=false;}});
document.addEventListener('dragleave', e=>{e.preventDefault();dragCount--;if(dragCount<=0)$('drop-zone').hidden=true;});
document.addEventListener('dragover',e=>e.preventDefault());
document.addEventListener('drop',async e=>{e.preventDefault();dragCount=0;$('drop-zone').hidden=true;if(state.busy)return;try{const files=[...e.dataTransfer.files];if(files.length){const data=await api(window.scoreflow.importDroppedPages(files,state.pages.length>0&&!state.demo));displayImage(data);toast(`当前曲目共 ${state.pages.length} 页`);}}catch(x){toast(x.message,true);}});
new ResizeObserver(()=>{drawRoll();updateOverlay();}).observe($('roll-scroll'));
function frame(){if(state.playing){state.beat=Math.min(state.duration,player.position());if(state.beat>=state.duration){player.stop();state.beat=state.duration;updateButtons();}updatePosition();}requestAnimationFrame(frame);}requestAnimationFrame(frame);
api(window.scoreflow.info()).then(info=>{$('version').textContent=info.version;setRuntime(info.runtime);}).catch(e=>toast(e.message,true));
window.addEventListener('beforeunload',()=>player.stop());
// Exposed only inside the sandboxed page for desktop regression tests.
window.ScoreFlowView={state,displayResult,displayImage,seekTo,togglePlay,player};
drawRoll();updateButtons();
