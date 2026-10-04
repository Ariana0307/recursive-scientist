// Remove source-location metadata while retaining runtime code and license notices.
import fs from 'node:fs';
import path from 'node:path';
const root=process.cwd();
let comments=0,locations=0;
function visit(dir){for(const entry of fs.readdirSync(dir,{withFileTypes:true})){
 const file=path.join(dir,entry.name);if(entry.isDirectory()){visit(file);continue;}
 if(entry.name.endsWith('.map'))throw new Error('Source maps must be disabled');
 if(!entry.name.endsWith('.mjs'))continue;
 let text=fs.readFileSync(file,'utf8');
 text=text.replace(/^\/\/#(?:end)?region[^\n]*\n?/gm,()=>{comments++;return '';});
 text=text.replace(/filePath:\s*"([^"]+)"/g,(match,value)=>{
  if(!path.isAbsolute(value))return match;
  const relative=path.relative(root,value);locations++;
  return 'filePath: '+JSON.stringify(relative.startsWith('..')?'source-route':relative.split(path.sep).join('/'));
 });
 fs.writeFileSync(file,text);
}}
visit('.output');console.log(JSON.stringify({removed_source_location_comments:comments,relativized_route_locations:locations}));
