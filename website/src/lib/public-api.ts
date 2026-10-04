import lab from '../../backend/data/public-demo/lab.json';
import events from '../../backend/data/public-demo/events.json';
import history from '../../backend/data/public-demo/history.json';
import trace from '../../backend/data/public-demo/technical-trace.json';
import manifest from '../../backend/data/public-demo/manifest.json';
import { artifactBodies } from './public-artifacts.generated';

export function publicApi(request: Request): Response {
  const url = new URL(request.url);
  const json = (value: unknown, status=200) => new Response(JSON.stringify(value), {status,headers:{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
  const missing = () => json({error:'Not found'},404);
  if (!['GET','HEAD'].includes(request.method)) return missing();
  const routes: Record<string,unknown> = {'/api/lab':lab,'/api/lab/events':events,'/api/history':history,'/api/runs':history,'/api/technical-trace':trace,'/api/health':{status:'ok',mode:'recorded run · not live',live_tasks:0,standalone:true},'/api/artifacts':{artifacts:manifest.artifacts.map(({artifact_id,title,category,summary,media_type})=>({artifact_id,title,category,summary,media_type}))}};
  if (Object.hasOwn(routes,url.pathname)) return url.search ? missing() : json(routes[url.pathname]);
  const match=/^\/api\/artifacts\/([a-z][a-z0-9-]{0,48})$/.exec(url.pathname);
  if (!match || !['','?download=1'].includes(url.search)) return missing();
  const id=match[1]!;
  const item=manifest.artifacts.find(a=>a.artifact_id===id);
  const content=artifactBodies[id];
  if(!item||content===undefined) return missing();
  if(url.search) return new Response(content,{headers:{'Content-Type':item.media_type,'Content-Disposition':`attachment; filename="${item.file}"`,'X-Content-Type-Options':'nosniff'}});
  return json({artifact_id:id,title:item.title,content,media_type:item.media_type});
}
