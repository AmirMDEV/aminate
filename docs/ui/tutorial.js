/* Offline presentation only. Lesson data never executes Maya commands. */
(() => {
  "use strict";
  const data = window.AMINATE_DOCS;
  if (!data?.sections?.length) return;
  const $ = id => document.getElementById(id);
  function applyComponents(root=document) {
    root.querySelectorAll('button:not(.uu-button)').forEach(old=>{
      const button=window.UNTITLED_UI.button(old.textContent.trim(),{color:old.classList.contains('primary')?'primary':'secondary',size:'lg'});
      for(const attr of old.attributes)if(attr.name!=='class')button.setAttribute(attr.name,attr.value);
      button.className+=' '+old.className;
      // Preserve the theme label anchor and semantic contents from the tutorial.
      if(old.id==='themeToggle')button.innerHTML=old.innerHTML;
      old.replaceWith(button);
    });
    root.querySelectorAll('input,select').forEach(input=>input.classList.add('uu-input'));
  }
  applyComponents();
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const categories = {
    "Start": ["quick-start","toolkit-bar"],
    "Set up": ["scene-helpers","reference-manager","customization"],
    "Animate": ["dynamic-parenting","hand-foot-hold","surface-contact","dynamic-pivot","universal-ikfk","animation-assistant","animation-styling"],
    "Draw & review": ["animators-pencil","history-timeline","onion-skin","video-reference","timeline-notes","smear-frames"],
    "Rig": ["retargeter","control-picker","rotation-doctor","character-skinning","rig-scale"]
  };
  const categoryFor = id => Object.keys(categories).find(key => categories[key].includes(id)) || "Rig";
  const sections = new Map(data.sections.map(s => [s.id,s]));
  // Versioned, serializable view state. Effects live in dispatch/applyTheme.
  const state = {version:1,lesson:"quick-start",step:-1,query:"",category:"All tools",theme:"system"};
  const themeOrder = ["system", "light", "dark"];
  const preferences = window.AMINATE_TUTORIAL_PREFERENCES;
  const saved = preferences?.read();
  if (themeOrder.includes(saved)) state.theme = saved;
  const finder=$('finder'), lessonRoot=$('lesson');
  const narrow=matchMedia('(max-width:760px)');
  const syncFinder=()=>{finder.open=!narrow.matches;};
  syncFinder();narrow.addEventListener('change',syncFinder);
  const mediaItems=s=>s.mediaItems?.length?s.mediaItems:[{type:'image',src:s.media,title:s.title+' in Maya'}];
  const renderMedia=(s,item=mediaItems(s)[0])=>`<figure class="media-gallery" data-practice-media><div class="media-frame">${item.type==='video'?`<video src="${esc(item.src)}" poster="${esc(item.poster||s.media)}" controls playsinline preload="none"><a href="${esc(item.src)}">Open video</a></video>`:`<img src="${esc(item.src)}" alt="${esc(item.title||s.title+' in Maya')}" loading="${item===mediaItems(s)[0]?'eager':'lazy'}">`}</div><figcaption>${esc(item.title||s.title+' in Maya')}</figcaption><a class="media-open" href="${esc(item.src)}">Open full-size ${item.type==='video'?'video':'picture'} ↗</a></figure>`;
  const stepList=s=>`<ol>${s.steps.map(step=>`<li>${esc(step)}</li>`).join('')}</ol>`;
  const renderReference=s=>`<details class="reference-disclosure" data-learning-support><summary>All steps & more help</summary><div class="reference-content"><h2>Before you start</h2><p>${esc(s.before)}</p><h2>Try it in Maya</h2>${stepList(s)}<h2>What you should see</h2><p>${esc(s.see)}</p><h3>If it looks wrong</h3><p>${esc(s.help)}</p><h3>Main buttons</h3><ul class="button-list">${s.buttons.map(b=>`<li>${esc(b)}</li>`).join('')}</ul>${(s.subsections||[]).map(sub=>`<details><summary>${esc(sub.title)}</summary><p>${esc(sub.intro)}</p><dl>${sub.items.map(([a,b])=>`<dt>${esc(a)}</dt><dd>${esc(b)}</dd>`).join('')}</dl></details>`).join('')}${s.tips?.length?`<details><summary>Useful tips</summary>${s.tips.map(t=>`<p>${esc(t)}</p>`).join('')}</details>`:''}${mediaItems(s).length>1?`<details><summary>More pictures & videos</summary><div class="extra-media">${mediaItems(s).slice(1).map(m=>renderMedia(s,m)).join('')}</div></details>`:''}<nav class="lesson-pagination" aria-label="Other lessons">${[-1,1].map(direction=>{const at=data.sections.indexOf(s);const next=data.sections[(at+direction+data.sections.length)%data.sections.length];return `<a data-lesson-route href="#${esc(next.id)}"><small>${direction<0?'Previous tool':'Next tool'}</small>${esc(next.tabTitle||next.title)}</a>`;}).join('')}</nav></div></details>`;
  function renderLesson(section) {
    const checking=state.step===section.steps.length, preparing=state.step<0;
    const text=preparing?section.before:checking?section.see:section.steps[state.step];
    const label=preparing?'Before you start':checking?'What you should see':`Step ${state.step+1} of ${section.steps.length}`;
    return `<div data-learning-stage data-learning-topic="selected"><header class="lesson-header"><p class="quiet">${esc(categoryFor(section.id))} · ${section.number} / ${data.sections.length}</p><h1 tabindex="-1">${esc(section.tabTitle||section.title)}</h1><p data-learning-objective>${esc(section.purpose)}</p></header><div class="practice-layout" data-learning-chunk="current"><div class="practice-copy"><div id="stepContent" aria-live="polite"><p class="step-label">${label}</p><p class="step-text" data-learning-result>${esc(text)}</p>${checking?`<details><summary>If it looks wrong</summary><p>${esc(section.help)}</p></details>`:''}</div><div class="step-actions" data-learning-action>${state.step>=0?'<button type="button" data-intent="previous-step">Back a step</button>':''}<button class="primary" type="button" data-primary-action data-intent="${checking?'restart-lesson':'next-step'}">${preparing?'Show first step':checking?'Start again':state.step===section.steps.length-1?'Check the result':'Next step'}</button></div><p class="practice-note">Follow these steps in Maya.</p></div>${renderMedia(section)}</div><div class="print-steps" hidden><h2>Try it in Maya</h2>${stepList(section)}<p>${esc(section.see)}</p></div></div>${renderReference(section)}`;
  }
  function renderCurrent(focus=false){const section=sections.get(state.lesson);lessonRoot.innerHTML = renderLesson(section);applyComponents(lessonRoot);$('currentTitle').textContent=section.tabTitle||section.title;document.title=`${section.tabTitle||section.title} — Aminate Tutorials`;$('toolStrip').querySelectorAll('a').forEach(a=>{if(a.dataset.target===state.lesson)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});if(focus)lessonRoot.querySelector('h1').focus({preventScroll:true});}
  function updateFinder(){const words=state.query.trim().toLowerCase().replace(/[-/]/g,' ').split(/\s+/).filter(Boolean);let count=0;$('toolStrip').querySelectorAll('a').forEach(a=>{const s=sections.get(a.dataset.target);const haystack=[s.title,s.tabTitle,s.purpose,s.searchTerms,s.when,...s.steps,...s.buttons].join(' ').toLowerCase().replace(/[-/]/g,' ');a.hidden=!(words.every(w=>haystack.includes(w))&&(state.category==='All tools'||categoryFor(s.id)===state.category));if(!a.hidden)count++;});$('resultCount').textContent=`${count} tool${count===1?'':'s'}`;$('emptyState').hidden=count!==0;}
  function applyTheme(){document.documentElement.dataset.theme=state.theme;$('themeLabel').textContent=state.theme[0].toUpperCase()+state.theme.slice(1);$('themeToggle').setAttribute('aria-label',`Colour theme: ${state.theme}. Change theme`);}
  function dispatch(intent,value){
    if(intent==='select-lesson'){state.lesson=sections.has(value)?value:'quick-start';state.step=-1;renderCurrent(true);if(narrow.matches)finder.open=false;}
    if(intent==='next-step'||intent==='previous-step'||intent==='restart-lesson'){const s=sections.get(state.lesson);state.step=intent==='restart-lesson'?-1:Math.max(-1,Math.min(s.steps.length,state.step+(intent==='next-step'?1:-1)));renderCurrent();lessonRoot.querySelector('[data-primary-action]').focus({preventScroll:true});}
    if(intent==='search'){state.query=value;updateFinder();}
    if(intent==='filter'){state.category=value;updateFinder();}
    if(intent==='toggle-theme'){state.theme=themeOrder[(themeOrder.indexOf(state.theme)+1)%themeOrder.length];applyTheme();preferences?.write(state.theme); }
  }
  $('categoryFilters').innerHTML=['All tools',...Object.keys(categories)].map(c=>`<option>${esc(c)}</option>`).join('');
  $('toolStrip').innerHTML=data.sections.map(s=>`<a href="#${esc(s.id)}" data-target="${esc(s.id)}"><span>${s.number}</span>${esc(s.tabTitle||s.title)}</a>`).join('');
  $('search').addEventListener('input',e=>dispatch('search',e.target.value));
  $('categoryFilters').addEventListener('change',e=>dispatch('filter',e.target.value));
  $('clearSearch').addEventListener('click',()=>{$('search').value='';$('categoryFilters').value='All tools';state.category='All tools';dispatch('search','');$('search').focus();});
  lessonRoot.addEventListener('click',e=>{const button=e.target.closest('[data-intent]');if(button)dispatch(button.dataset.intent);});
  document.addEventListener('click',e=>{const a=e.target.closest('a[href^="#"]');if(!a)return;const id=a.getAttribute('href').slice(1);if(sections.has(id)){e.preventDefault();if(location.hash.slice(1)!==id)location.hash=id;else dispatch('select-lesson',id);}if(id==='faq')$('faqDisclosure').open=true;});
  function followHash(){const id=location.hash.slice(1);if(id==='faq'){$('faqDisclosure').open=true;return;}dispatch('select-lesson',id);}
  window.addEventListener('hashchange',followHash);
  finder.addEventListener('keydown',e=>{if(e.key==='Escape'&&narrow.matches){finder.open=false;finder.querySelector('summary').focus();}});
  $('faqList').innerHTML=data.faq.map(item=>`<details><summary>${esc(item.q)}</summary><p>${esc(item.a)}</p></details>`).join('');
  const buttons=[...(data.buttons||[]),...data.sections.map(s=>({label:s.tabTitle||s.title,group:'Tool',tooltip:s.purpose}))];
  function renderButtons(){const terms=$('buttonSearch').value.trim().toLowerCase().split(/\s+/);const matches=buttons.filter(b=>terms.every(w=>[b.label,b.group,b.tooltip].join(' ').toLowerCase().includes(w)));$('buttonCount').textContent=matches.length?`${matches.length} matches`:'No matching buttons. Try one word.';$('buttonIndex').innerHTML=matches.map(b=>`<div class="index-row"><strong>${esc(b.label)}</strong><small>${esc(b.group)}</small><p>${esc(b.tooltip)}</p></div>`).join('');}
  $('buttonSearch').addEventListener('input',renderButtons);
  $('themeToggle').addEventListener('click',()=>dispatch('toggle-theme'));
  document.addEventListener('error',e=>{if(e.target.matches?.('img,video')){const caption=e.target.closest('figure')?.querySelector('figcaption');if(caption)caption.textContent='Picture or video missing. Keep the tutorial folder together. The steps still work.';}},true);
  applyTheme();updateFinder();renderButtons();followHash();
})();
