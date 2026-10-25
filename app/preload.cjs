const { contextBridge, ipcRenderer, webUtils } = require('electron');
contextBridge.exposeInMainWorld('scoreflow', {
  info: () => ipcRenderer.invoke('info'),
  openImage: (append=false) => ipcRenderer.invoke('open-image',append),
  loadDemo: () => ipcRenderer.invoke('load-demo'),
  importDropped: (file) => ipcRenderer.invoke('import-image', webUtils.getPathForFile(file)),
  importDroppedPages: (files,append=false) => ipcRenderer.invoke('import-images',files.map(file=>webUtils.getPathForFile(file)),append),
  editPages: (ids) => ipcRenderer.invoke('edit-pages',{ids}),
  recognize: (options) => ipcRenderer.invoke('recognize', options),
  cancel: () => ipcRenderer.invoke('cancel'),
  exportFile: (kind, program) => ipcRenderer.invoke('export', kind, program),
  renderAudio: (program, bpm) => ipcRenderer.invoke('render-audio', program, bpm),
  chooseRuntime: () => ipcRenderer.invoke('choose-runtime'),
  openResults: () => ipcRenderer.invoke('open-results'),
  onProgress: (fn) => { const cb = (_, data) => fn(data); ipcRenderer.on('progress', cb); return () => ipcRenderer.removeListener('progress', cb); }
});
