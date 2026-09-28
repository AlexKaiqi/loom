(()=>{
  const navHolder=document.querySelector('.nav-holder');
  const smallScreen=matchMedia('(max-width:760px)');
  function syncNavigation(){navHolder.open=!smallScreen.matches;}
  smallScreen.addEventListener('change',syncNavigation);syncNavigation();
  function revealHash(){
    let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
    if(!id)return;
    const target=document.getElementById(id);if(!target)return;
    for(let p=target.parentElement;p;p=p.parentElement){if(p.tagName==='DETAILS')p.open=true;}
    requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
  }
  window.addEventListener('hashchange',revealHash);revealHash();
  const links=[...document.querySelectorAll('.page-toc a[href^="#"]')];
  const headings=links.map(a=>document.getElementById(decodeURIComponent(a.hash.slice(1))));
  const toc=document.querySelector('.page-toc'),tocToggle=toc?.querySelector('.toc-toggle');
  function expandToc(open){
    toc?.classList.toggle('is-open',open);
    tocToggle?.setAttribute('aria-expanded',String(open));
    tocToggle?.setAttribute('aria-label',open?'收起本页目录':'展开本页目录');
  }
  tocToggle?.addEventListener('click',()=>expandToc(!toc.classList.contains('is-open')));
  links.forEach((link,i)=>link.addEventListener('click',()=>{
    expandToc(false);
    const heading=headings[i];
    if(heading){heading.tabIndex=-1;heading.focus({preventScroll:true});}
  }));
  document.addEventListener('pointerdown',e=>{if(toc&&!toc.contains(e.target))expandToc(false);});
  toc?.addEventListener('keydown',e=>{
    if(e.key!=='Escape')return;
    expandToc(false);
    const target=tocToggle.offsetParent?tocToggle:headings[links.findIndex(a=>a.classList.contains('active'))];
    if(target){if(target!==tocToggle)target.tabIndex=-1;target.focus({preventScroll:true});}
  });
  let ticking=false;
  function mark(){
    ticking=false;let active=0;
    headings.forEach((h,i)=>{if(h&&h.getBoundingClientRect().top<130)active=i;});
    if(scrollY>0&&Math.ceil(scrollY+innerHeight)>=document.documentElement.scrollHeight)active=links.length-1;
    links.forEach((a,i)=>{a.classList.toggle('active',i===active);if(i===active)a.setAttribute('aria-current','location');else a.removeAttribute('aria-current');});
  }
  function queueMark(){if(!ticking){ticking=true;requestAnimationFrame(mark);}}
  addEventListener('scroll',queueMark,{passive:true});
  addEventListener('resize',queueMark);mark();
  const dialog=document.getElementById('diagram-dialog'),holder=document.getElementById('dialog-content');
  let returnFocus=null;
  document.querySelectorAll('figure .zoom').forEach(btn=>btn.addEventListener('click',()=>{
    const f=btn.closest('figure');const svg=f.querySelector('svg');if(!svg)return;
    returnFocus=btn;document.getElementById('dialog-title').textContent=f.querySelector('figcaption span').textContent;
    holder.replaceChildren(svg.cloneNode(true));dialog.showModal();holder.scrollTop=0;holder.scrollLeft=0;
  }));
  document.getElementById('dialog-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('close',()=>{holder.replaceChildren();if(returnFocus)returnFocus.focus();});
  dialog.addEventListener('click',e=>{if(e.target===dialog){const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close();}});
  document.querySelectorAll('.copy').forEach(btn=>btn.addEventListener('click',async()=>{
    const text=document.getElementById(btn.dataset.copy).querySelector('code').textContent;
    try{
      if(navigator.clipboard&&window.isSecureContext)await navigator.clipboard.writeText(text);
      else{const t=document.createElement('textarea');t.value=text;t.style.position='fixed';t.style.opacity='0';document.body.append(t);t.select();const ok=document.execCommand('copy');t.remove();if(!ok)throw Error('clipboard unavailable');}
      btn.textContent='已复制';
    }catch{btn.textContent='请选择代码复制';}
    setTimeout(()=>btn.textContent='复制',1800);
  }));
  let printState=[];
  addEventListener('beforeprint',()=>{printState=[...document.querySelectorAll('details')].map(d=>[d,d.open]);printState.forEach(([d])=>d.open=true);});
  addEventListener('afterprint',()=>printState.forEach(([d,v])=>d.open=v));
  document.getElementById('print').addEventListener('click',()=>window.print());
})();
