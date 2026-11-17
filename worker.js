// IPTV aracı sunucusu (Cloudflare Worker)
// Ortam değişkeni: TOKEN (gizli anahtar). İstek: /?k=TOKEN&u=<kodlanmış hedef url>
const CORS={'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*','Access-Control-Expose-Headers':'*'};
export default {
  async fetch(req,env){
    if(req.method==='OPTIONS')return new Response(null,{headers:CORS});
    const url=new URL(req.url);
    if(!env.TOKEN||url.searchParams.get('k')!==env.TOKEN)return new Response('yetkisiz',{status:401,headers:CORS});
    const target=url.searchParams.get('u');
    if(!target||!/^https?:\/\//i.test(target))return new Response('u gerekli',{status:400,headers:CORS});
    const h=new Headers();
    for(const n of ['range','user-agent'])if(req.headers.get(n))h.set(n,req.headers.get(n));
    let r;
    try{r=await fetch(target,{headers:h,redirect:'follow'})}catch(e){return new Response('hedefe ulaşılamadı: '+e.message,{status:502,headers:CORS})}
    const ct=r.headers.get('content-type')||'';
    const isM3U=/mpegurl/i.test(ct)||/\.m3u8?(\?|$)/i.test(new URL(r.url).pathname+new URL(r.url).search);
    const out=new Headers(CORS);
    for(const n of ['content-type','content-length','content-range','accept-ranges'])if(r.headers.get(n))out.set(n,r.headers.get(n));
    if(isM3U){
      const text=await r.text();
      if(!text.trimStart().startsWith('#EXTM3U'))return new Response(text,{status:r.status,headers:out});
      const base=r.url,self=url.origin+'/?k='+encodeURIComponent(env.TOKEN)+'&u=';
      const abs=x=>self+encodeURIComponent(new URL(x,base).href);
      const body=text.split(/\r?\n/).map(l=>{
        if(!l.trim())return l;
        if(l.startsWith('#'))return l.replace(/URI="([^"]+)"/g,(m,u)=>'URI="'+abs(u)+'"');
        return abs(l.trim());
      }).join('\n');
      out.delete('content-length');out.set('content-type','application/vnd.apple.mpegurl');
      return new Response(body,{status:r.status,headers:out});
    }
    return new Response(r.body,{status:r.status,headers:out});
  }
};
