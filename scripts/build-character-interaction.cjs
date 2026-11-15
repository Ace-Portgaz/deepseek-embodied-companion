// Uses separately acquired Cubism Core and the user's model; publishes no assets.
const fs=require('node:fs'),path=require('node:path');
const root=process.argv[2]?path.resolve(process.argv[2]):path.resolve(__dirname,'../rem-phone-system/vendor/rem/RemBody/assets/rem-bust-v4');
const coreFile=path.join(root,'preview/vendor/live2dcubismcore.min.js');
const Core=Function('require','__dirname','module','exports',fs.readFileSync(coreFile,'utf8')+';return Live2DCubismCore;')(require,path.dirname(coreFile),{exports:{}},{});
setTimeout(()=>{
 try {
  const catalog=JSON.parse(fs.readFileSync(path.join(root,'catalog.json'),'utf8'));
  const item=catalog.outfits.find(x=>x.id==='deepseek-chan-user');
  if(!item)throw Error('Import DeepSeek-chan first');
  const entry=path.resolve(root,item.model),dir=path.dirname(entry);
  if(!entry.startsWith(root+path.sep))throw Error('Model path outside assets');
  const settings=JSON.parse(fs.readFileSync(entry,'utf8'));
  const local=name=>{const target=path.resolve(dir,name);if(!target.startsWith(dir+path.sep))throw Error('Resource path outside model');return target;};
  const b=fs.readFileSync(local(settings.FileReferences.Moc));
  const moc=Core.Moc.fromArrayBuffer(b.buffer.slice(b.byteOffset,b.byteOffset+b.byteLength));
  if(!moc)throw Error('Core rejected model');
  const model=Core.Model.fromMoc(moc);if(!model)throw Error('Model initialization failed');model.update();
  const cdi=settings.FileReferences.DisplayInfo;
  if(!cdi)throw Error('A CDI file with named parts is required');
  const names=new Map(JSON.parse(fs.readFileSync(local(cdi),'utf8')).Parts.map(x=>[x.Id,x.Name]));
  const groups=[['tail',/尾巴/],['hand',/手|食指/],['face',/五官|脸|鼻|嘴|眼|眉|耳朵/],['head',/头|发|钢盆/],['legs',/鞋|腿/],['body',/身体|胸|腰|衣|裙|领|脖|上身/]];
  const regions={};
  for(let i=0;i<model.drawables.count;i++){
   let part=model.drawables.parentPartIndices[i],depth=0;
   while(part>=0&&depth++<30){const name=names.get(model.parts.ids[part])||model.parts.ids[part],group=groups.find(x=>x[1].test(name));if(group){regions[model.drawables.ids[i]]=group[0];break;}part=model.parts.parentIndices[part];}
  }
  const list=(folder,suffix)=>fs.readdirSync(path.join(dir,folder)).filter(x=>x.endsWith(suffix)).sort().map(file=>({name:file.slice(0,-suffix.length),file:folder+'/'+file}));
  const config={version:1,expressions:list('Exp3','.exp3.json'),motions:list('Animation','.motion3.json'),regions};
  const target=local('interaction.json');
  if(fs.existsSync(target))throw Error('interaction.json exists; preserve it before regenerating');
  fs.writeFileSync(target,JSON.stringify(config,null,2)+'\n',{flag:'wx'});
  model.release();moc._release();
  console.log(`Generated ${config.expressions.length} expressions, ${config.motions.length} motions, ${Object.keys(regions).length} mapped meshes.`);
 }catch(error){console.error(error.message);process.exitCode=1;}
},1000);
