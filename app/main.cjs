const { app, BrowserWindow, ipcMain, dialog, shell, nativeImage, Menu } = require('electron');
const fs = require('node:fs/promises');
const path = require('node:path');
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const { pathToFileURL } = require('node:url');
const Music = require('./music.cjs');
const { INSTRUMENTS, makeMidi } = require('./midi.cjs');

app.setName('ScoreFlow');
const ROOT = path.join(__dirname, '..');
const engineRoot = () => app.isPackaged ? path.join(process.resourcesPath, 'engine') : path.join(ROOT, 'engine');
const beside = () => app.isPackaged ? path.dirname(app.getPath('exe')) : ROOT;
let win, source = null, result = null, activeJob = null, demoData = null, batchJob = null;
let sourcePages = [];
const audioJobs = new Set(), audioCache = new Map();
let renderQueue = Promise.resolve();
const userRoot = () => app.getPath('userData');
const emit = data => { if (win && !win.isDestroyed()) win.webContents.send('progress', data); };

async function readJSON(file) { return JSON.parse(await fs.readFile(file, 'utf8')); }
async function exists(file) { try { await fs.access(file); return true; } catch { return false; } }
async function runtimeRoot() {
  if (process.env.SCOREFLOW_RUNTIME_ROOT) return path.resolve(process.env.SCOREFLOW_RUNTIME_ROOT);
  for (const f of [path.join(userRoot(), 'runtime.json'), path.join(beside(), 'runtime.local.json')]) {
    try { const c = await readJSON(f); if (c.root && await exists(c.root)) return path.resolve(c.root); } catch {}
  }
  const bundled = path.join(beside(), 'runtime');
  return await exists(bundled) ? bundled : null;
}
async function runtimeInfo() {
  const root = await runtimeRoot();
  if (!root) return { ready: false, message: '请选择模型运行环境文件夹' };
  const candidates = ['python/python.exe', 'python/Scripts/python.exe', 'oemer_env/Scripts/python.exe'];
  let python = path.join(root, candidates[0]);
  for (const candidate of candidates) {
    if (await exists(path.join(root, candidate))) { python = path.join(root, candidate); break; }
  }
  const checks = await Promise.all([python, path.join(root, 'gpu_runtime_v2', 'homr_weights_lock.json'), path.join(root, 'model_registry.json')].map(exists));
  return { ready: checks.every(Boolean), root, python, message: checks.every(Boolean) ? '本地引擎已就绪 · NVIDIA GPU' : '运行环境不完整，请重新选择' };
}
function spawnEngine(args, onMessage = () => {}, requestedOutput = null) {
  return new Promise(async (resolve, reject) => {
    try {
      if (activeJob) throw new Error('已有识别任务正在运行');
      const info = await runtimeInfo();
      if (!info.ready) throw new Error(info.message);
      if(batchJob?.cancelled)throw new Error('识别已取消');
      const output = requestedOutput || path.join(userRoot(), 'results', `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`);
      const child = spawn(info.python, [path.join(engineRoot(), 'runner.py'), ...args, '--output', output], {
        windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', SCOREFLOW_RUNTIME_ROOT: info.root, SCOREFLOW_STATE_ROOT: path.join(userRoot(), 'gpu-state') }
      });
      const job = { child, cancelled: false, output };
      activeJob = job;
      let buffer = '', tail = '', settled = false;
      const timer = setTimeout(() => { job.cancelled = true; child.kill(); }, 15 * 60 * 1000);
      child.stdout.on('data', chunk => {
        buffer += chunk.toString('utf8');
        const lines = buffer.split('\n'); buffer = lines.pop();
        for (const line of lines) { try { onMessage(JSON.parse(line)); } catch { tail = (tail + line + '\n').slice(-4000); } }
      });
      child.stderr.on('data', chunk => { tail = (tail + chunk.toString('utf8')).slice(-4000); });
      const finish = async (error, code) => {
        if (settled) return; settled = true; clearTimeout(timer);
        if (activeJob === job) activeJob = null;
        if (job.cancelled) return reject(new Error('识别已取消'));
        if (error) return reject(error);
        if (code !== 0) return reject(new Error(tail.trim() || `识别引擎退出（${code}）`));
        try { resolve(await readJSON(path.join(output, 'result.json'))); } catch (e) { reject(new Error(`未能读取识别结果：${e.message}`)); }
      };
      child.once('error', e => finish(e));
      child.once('close', code => finish(null, code));
    } catch (e) { reject(e); }
  });
}
async function imageData(file) {
  const stat = await fs.stat(file);
  if (stat.size > 100 * 1024 ** 2) throw new Error('图片超过 100 MB，请先缩小图片');
  const image = nativeImage.createFromPath(file);
  if (image.isEmpty()) throw new Error('无法读取图片，请选择 PNG、JPEG、WebP 或 BMP 图片');
  const size = image.getSize();
  if (size.width * size.height > 100_000_000) throw new Error('图片尺寸过大，请先缩小至一亿像素以内');
  const ratio=Math.min(1,2400/size.width,5000/size.height);
  const preview=ratio<1?image.resize({width:Math.round(size.width*ratio),height:Math.round(size.height*ratio)}):image;
  return { dataURL: preview.toDataURL(), width: size.width, height: size.height };
}
async function importImage(file) {
  return importImages([file]);
}
function documentPreview() {
  const pages=sourcePages.map((p,index)=>({...p.preview,id:p.id,index,name:p.name,status:p.raw?'recognized':'pending'}));
  return { ...pages[0],pages,name:pages.length>1?`${pages[0].name} 等 ${pages.length} 页`:pages[0].name,demo:false };
}
async function importImages(files,append=false) {
  if (batchJob || activeJob) throw new Error('请先等待识别完成，或取消当前任务');
  if(!Array.isArray(files)||!files.length)throw new Error('请选择至少一张谱面图片');
  if(files.length+(append?sourcePages.length:0)>64)throw new Error('每首曲目最多导入 64 页');
  const ordered=[...files].sort((a,b)=>path.basename(a).localeCompare(path.basename(b),'zh-CN',{numeric:true,sensitivity:'base'}));
  const incoming=[];
  for(const file of ordered){
  if (typeof file !== 'string' || !['.png', '.jpg', '.jpeg', '.bmp', '.webp'].includes(path.extname(file).toLowerCase())) throw new Error('请选择 PNG、JPEG、WebP 或 BMP 图片');
  const preview = await imageData(file);
    incoming.push({id:crypto.randomUUID(),file:path.resolve(file),name:path.basename(file),preview,raw:null,cacheKey:null});
  }
  sourcePages=append?[...sourcePages,...incoming]:incoming;
  source=sourcePages[0].file;result=null;demoData=null;
  return documentPreview();
}
async function presentResult(raw) {
  if(raw.pages?.length){
    const pages=[];
    for(const page of raw.pages){
      const image=await imageData(page.image);
      pages.push({...image,id:page.id,index:page.index,name:page.name,start:Music.rational(page.start),duration:Music.rational(page.duration),
        events:Music.normalizeEvents(page.events),geometry:page.geometry?await readJSON(page.geometry):[],status:'recognized',
        route:{layout:page.route?.detected_layout||page.route?.layout||'unknown',engine:page.route?.selected_engine||page.route?.engine}});
    }
    return {...pages[0],name:raw.title||'完整曲目',pages,events:Music.normalizeEvents(raw.events),duration:Music.rational(raw.duration),bpm:raw.bpm||120,meters:raw.meters||[],
      route:{layout:raw.route?.detected_layout,page_count:pages.length,engine:pages.length===1?pages[0].route.engine:null},reviewFlags:raw.corrections?.review_flags||[],canExportXML:!!raw.musicxml,demo:false};
  }
  const image = await imageData(raw.image);
  const geometry = raw.geometry ? await readJSON(raw.geometry) : [];
  const events = Music.normalizeEvents(raw.events || []);
  if (!events.length) throw new Error('识别结果中没有可播放的音符');
  return { ...image, name: source ? path.basename(source) : '谱面', events, geometry, bpm: raw.bpm || 120, meters: raw.meters || [],
    route: { layout: raw.route?.detected_layout || raw.route?.layout || 'unknown', engine: raw.route?.selected_engine || raw.route?.engine },
    reviewFlags: raw.corrections?.review_flags || [], canExportXML:!!raw.musicxml, demo: false };
}
async function assemblePages(pages,folder,title) {
  const info=await runtimeInfo();
  const manifest=path.join(folder,'pages.json');
  await fs.writeFile(manifest,JSON.stringify({title,pages:pages.map(p=>({id:p.id,name:p.name,result:path.join(p.raw.folder,'result.json')}))},null,2));
  const output=path.join(folder,'complete');
  if(batchJob?.cancelled)throw new Error('识别已取消');
  await new Promise((resolve,reject)=>{
    const child=spawn(info.python,[path.join(engineRoot(),'assemble.py'),manifest,'--output',output],{windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,PYTHONIOENCODING:'utf-8'}});
    const job={child,cancelled:false,kind:'assemble'};activeJob=job;let error='';
    child.stderr.on('data',b=>error=(error+b.toString('utf8')).slice(-3000));
    child.once('error',reject);child.once('close',code=>{if(activeJob===job)activeJob=null;if(job.cancelled||batchJob?.cancelled)reject(new Error('识别已取消'));else code===0?resolve():reject(new Error(error||'曲目合并失败'));});
  });
  return readJSON(path.join(output,'result.json'));
}
async function recognizeDocument(options={}) {
  if(!sourcePages.length)throw new Error('请先导入谱面图片');
  if(batchJob||activeJob)throw new Error('已有识别任务正在运行');
  const meter=options?.meter||'auto',mode=options?.mode||'auto';
  if(!['auto','staff','tab'].includes(mode))throw new Error('无效识别模式');
  if(!['auto','2/4','3/4','4/4','3/8','6/8','9/8','12/8'].includes(meter))throw new Error('无效拍号');
  const job={cancelled:false};batchJob=job;result=null;
  const pages=[...sourcePages],folder=path.join(userRoot(),'results',`piece-${Date.now()}-${crypto.randomBytes(4).toString('hex')}`);
  try{
    await fs.mkdir(folder,{recursive:true});
    for(let index=0;index<pages.length;index++){
      if(job.cancelled)throw new Error('识别已取消');
      const page=pages[index],prefix=`第 ${index+1}/${pages.length} 页`;
      emit({stage:'page-start',pageIndex:index,pageId:page.id,total:pages.length,message:`${prefix} · ${page.name}`});
      const digest=crypto.createHash('sha256').update(await fs.readFile(page.file)).digest('hex');
      if(job.cancelled)throw new Error('识别已取消');
      const cacheKey=JSON.stringify([digest,mode,meter]);
      if(!page.raw||page.cacheKey!==cacheKey){
        const output=path.join(folder,'pages',`${String(index+1).padStart(3,'0')}-${page.id}`);
        page.raw=await spawnEngine(['recognize','--image',page.file,'--mode',mode,...(meter==='auto'?[]:['--meter',meter])],data=>emit({...data,pageIndex:index,pageId:page.id,total:pages.length,message:`${prefix} · ${data.message||'正在识别…'}`}),output);
        page.cacheKey=cacheKey;
      }
      if(job.cancelled)throw new Error('识别已取消');
      emit({stage:'page-done',pageIndex:index,pageId:page.id,total:pages.length,message:`${prefix} 已完成并保存`});
    }
    if(job.cancelled)throw new Error('识别已取消');
    emit({stage:'assemble',message:`正在连接 ${pages.length} 页的音符、休止与谱面位置…`});
    const title=path.parse(pages[0].name).name+(pages.length>1?' · 完整曲目':'');
    const raw=await assemblePages(pages,folder,title);
    if(job.cancelled)throw new Error('识别已取消');
    const view=await presentResult(raw);result=raw;
    emit({stage:'done',message:`${pages.length} 页已连接成完整曲目，MIDI 已自动保存`});return view;
  }catch(e){emit({stage:'error',message:e.message});throw e;}
  finally{if(batchJob===job)batchJob=null;}
}
function handle(name, fn) {
  ipcMain.handle(name, async (event, ...args) => {
    if (!win || event.sender !== win.webContents || event.senderFrame !== win.webContents.mainFrame) throw new Error('Unsupported sender');
    try { return { ok: true, value: await fn(...args) }; } catch (e) { return { ok: false, error: e.message }; }
  });
}
function registerHandlers() {
  handle('info', async () => ({ version: app.getVersion(), runtime: await runtimeInfo() }));
  handle('open-image', async (append=false) => {
    const selection = await dialog.showOpenDialog(win, { title: append?'追加谱页':'导入谱面（可一次选择多页）', properties: ['openFile','multiSelections'], filters: [{ name: '谱面图片', extensions: ['png','jpg','jpeg','webp','bmp'] }] });
    return selection.canceled ? null : importImages(selection.filePaths,append===true);
  });
  handle('import-image', importImage);
  handle('import-images',importImages);
  handle('edit-pages',async ({ids}={})=>{
    if(batchJob||activeJob)throw new Error('识别运行时无法调整页序');
    if(!Array.isArray(ids)||!ids.length||new Set(ids).size!==ids.length||ids.some(id=>!sourcePages.some(p=>p.id===id)))throw new Error('无效谱页顺序');
    sourcePages=ids.map(id=>sourcePages.find(p=>p.id===id));source=sourcePages[0].file;result=null;demoData=null;return documentPreview();
  });
  handle('load-demo', async () => {
    if (batchJob||activeJob) throw new Error('请先取消当前识别任务');
    source = null; result = null;sourcePages=[];
    const demo = await readJSON(path.join(__dirname, 'demo.json')); demoData = demo;
    return { ...demo, dataURL: 'data:image/svg+xml;base64,' + (await fs.readFile(path.join(__dirname, 'demo.svg'))).toString('base64'), demo: true };
  });
  handle('recognize',recognizeDocument);
  handle('cancel', () => {
    if(batchJob)batchJob.cancelled=true;
    if (activeJob) {
      const job = activeJob; job.cancelled = true;
      if(job.kind==='assemble')job.child.kill();
      else if (job.child.stdin?.writable) job.child.stdin.write('CANCEL\n');
      const timeout = setTimeout(() => { if (activeJob === job) job.child.kill(); }, 8000);
      job.child.once('close', () => clearTimeout(timeout));
    }
    return true;
  });
  handle('render-audio', async (program, playbackBpm) => {
    if (!Number.isInteger(program) || !INSTRUMENTS.some(i=>i.program===program)) throw new Error('无效音色');
    const data = result || demoData;
    if (!data?.events?.length) throw new Error('请先识别谱面或载入播放示例');
    const runtime = await runtimeRoot();
    if (!runtime) throw new Error('请先配置包含采样音色的运行环境');
    const synth = path.join(runtime,'audio','fluidsynth','fluidsynth.exe'), sf2 = path.join(runtime,'audio','GeneralUser-GS.sf2');
    if (!await exists(synth) || !await exists(sf2)) throw new Error('未找到采样音色库，请安装完整运行环境');
    const audioBpm = Number(playbackBpm) || data.bpm || 120;
    if (!Number.isFinite(audioBpm) || audioBpm < 30 || audioBpm > 300) throw new Error('无效试听速度');
    const midi = makeMidi(data.events,data.meters,audioBpm,program,data.duration);
    const key = crypto.createHash('sha256').update(midi).digest('hex');
    const folder = path.join(userRoot(),'audio-cache'), output = path.join(folder,key+'.wav');
    if (!audioCache.has(key)) {
      const task = renderQueue.catch(()=>{}).then(async () => {
        await fs.mkdir(folder,{recursive:true});
        if (!await exists(output)) {
          const midiPath = path.join(folder,key+'.mid'); await fs.writeFile(midiPath,midi);
          await new Promise((resolve,reject) => {
            const child = spawn(synth,['-n','-i','-q','-F',output,'-T','wav','-O','s16','-r','44100','-g','0.7','-o','synth.chorus.active=0','-o','synth.reverb.active=1','-o','synth.reverb.level=0.16',sf2,midiPath],{windowsHide:true,stdio:['ignore','ignore','pipe']});
            audioJobs.add(child); let error='';const timer=setTimeout(()=>child.kill(),120000);
            child.stderr.on('data',b=>{error=(error+b.toString()).slice(-1200);});
            child.once('error',e=>{clearTimeout(timer);audioJobs.delete(child);reject(e);});
            child.once('close',code=>{clearTimeout(timer);audioJobs.delete(child);code===0?resolve():reject(new Error('采样音色加载失败：'+error));});
          });
        }
        const bytes=await fs.readFile(output);
        if(bytes.length<44 || bytes.subarray(0,4).toString()!=='RIFF')throw new Error('音色渲染没有产生有效 WAV');
        return output;
      });
      audioCache.set(key,task);renderQueue=task;task.catch(()=>audioCache.delete(key));
    }
    const file = await audioCache.get(key);
    return { bytes:new Uint8Array(await fs.readFile(file)), program, name:INSTRUMENTS.find(i=>i.program===program).name, bpm:audioBpm };
  });
  handle('export', async (kind, program=24) => {
    if (!result) throw new Error('请先完成谱面识别；示例仅用于体验播放');
    const file = { midi: result.midi, musicxml: result.musicxml, json: path.join(result.folder, 'result.json') }[kind];
    if (!file) throw new Error('无效导出格式');
    const ext = { midi: 'mid', musicxml: 'musicxml', json: 'json' }[kind];
    const selection = await dialog.showSaveDialog(win, { title: '导出识别结果', defaultPath: `${path.parse(source).name}${result.pages?.length>1?'_完整曲目':''}.${ext}`, filters: [{ name: kind === 'midi' ? 'MIDI 文件' : kind, extensions: [ext] }] });
    if (selection.canceled) return null;
    if (kind === 'midi') await fs.writeFile(selection.filePath,makeMidi(result.events,result.meters,result.bpm,program,result.duration));
    else if (path.resolve(file) !== path.resolve(selection.filePath)) await fs.copyFile(file, selection.filePath);
    return path.basename(selection.filePath);
  });
  handle('choose-runtime', async () => {
    if (batchJob||activeJob) throw new Error('识别运行时无法切换环境');
    const selection = await dialog.showOpenDialog(win, { title: '选择模型运行环境（含 model_registry.json 的文件夹）', properties: ['openDirectory'] });
    if (!selection.canceled) { await fs.mkdir(userRoot(), { recursive: true }); await fs.writeFile(path.join(userRoot(), 'runtime.json'), JSON.stringify({ root: selection.filePaths[0] })); }
    return runtimeInfo();
  });
  handle('open-results', async () => { const folder = result?.folder || path.join(userRoot(), 'results'); await fs.mkdir(folder, { recursive: true }); const error = await shell.openPath(folder); if (error) throw new Error(error); return true; });
}
async function createWindow() {
  win = new BrowserWindow({ width: 1450, height: 940, minWidth: 1060, minHeight: 720, title: '谱音 · ScoreFlow', icon: path.join(__dirname,'icon.png'), backgroundColor: '#f5f4ef',
    show: false, autoHideMenuBar: true, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true, backgroundThrottling:false } });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', event => event.preventDefault());
  win.webContents.session.setPermissionRequestHandler((_contents, _permission, callback) => callback(false));
  win.once('ready-to-show', () => win.show());
  win.on('closed', () => { win = null; });
  await win.loadFile(path.join(__dirname, 'index.html'));
  if (process.argv.includes('--self-test')) await require('../tests/desktop.cjs').run({ win, app, importImage, presentResult, spawnEngine, adoptResult: raw=>{result=raw;demoData=null;} });
}
app.on('before-quit', () => { if (activeJob) { activeJob.cancelled = true; activeJob.child.kill(); } for(const child of audioJobs)child.kill(); });
app.whenReady().then(async () => { Menu.setApplicationMenu(null); registerHandlers(); await createWindow(); });
app.on('window-all-closed', () => app.quit());
