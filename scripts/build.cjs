const fs = require('node:fs/promises');
const path = require('node:path');
const { createPackage } = require('@electron/asar');
async function build() {
  const root = path.resolve(__dirname, '..');
  const pkg = JSON.parse(await fs.readFile(path.join(root,'package.json'),'utf8'));
  const out = path.join(root, '..', 'ScoreFlow-Windows-x64');
  const electron = path.join(root, 'node_modules', 'electron', 'dist');
  await fs.access(path.join(electron, 'electron.exe'));
  await fs.mkdir(out, { recursive: true });
  await fs.cp(electron, out, { recursive: true });
  await fs.copyFile(path.join(electron,'LICENSE'),path.join(out,'ELECTRON-LICENSE'));
  await fs.rename(path.join(out, 'electron.exe'), path.join(out, 'ScoreFlow.exe'));
  if (process.platform === 'win32') {
    const { rcedit } = await import('rcedit');
    await rcedit(path.join(out,'ScoreFlow.exe'), { icon: path.join(root,'app','icon.ico'),
      'version-string': { ProductName:'ScoreFlow',FileDescription:'谱音 · ScoreFlow',CompanyName:'ScoreFlow contributors',OriginalFilename:'ScoreFlow.exe' },
      'file-version':pkg.version,'product-version':pkg.version });
  }
  const stage = path.join(root, 'dist', 'app');
  await fs.mkdir(stage, { recursive: true });
  await fs.cp(path.join(root, 'app'), path.join(stage, 'app'), { recursive: true });
  await fs.cp(path.join(root, 'tests'), path.join(stage, 'tests'), { recursive: true });
  delete pkg.devDependencies; delete pkg.scripts;
  await fs.writeFile(path.join(stage, 'package.json'), JSON.stringify(pkg, null, 2));
  await createPackage(stage, path.join(out, 'resources', 'app.asar'));
  await fs.cp(path.join(root,'engine'),path.join(out,'resources','engine'),{recursive:true,filter:p=>!p.includes('__pycache__')});
  for(const name of ['LICENSE','README.md','RUNTIME.md','THIRD_PARTY_NOTICES.md']) await fs.copyFile(path.join(root,name),path.join(out,name));
  await fs.cp(path.join(root,'docs'),path.join(out,'docs'),{recursive:true});
  for(const file of ['README.en.md','docs/INSTALL.en.md']) await fs.rm(path.join(out,file),{force:true});
  console.log(out);
}
build().catch(e=>{console.error(e);process.exitCode=1;});
