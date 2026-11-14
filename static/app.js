'use strict';
const $ = selector => document.querySelector(selector);
const state = {role:'professional', csrf:'', producers:[], detail:null, mode:null, editId:null};
const fmt = n => new Intl.NumberFormat('fr-FR',{maximumFractionDigits:1}).format(n);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const prettyDate = value => new Date(value+'T12:00:00').toLocaleDateString('fr-FR');
function notice(message, error=false){$('#notice').textContent=message;$('#notice').className=error?'error':'';$('#notice').hidden=false;}
function loginView(){state.role='professional';state.csrf='';$('#login-form').hidden=false;$('#register-form').hidden=true;state.producers=[];state.detail=null;for(const id of ['#producer-list','#recent-producers','#stats','#harvest-list','#advice-list','#detail-name','#detail-meta','#detail-notes','#editor-fields','#user-name','#prediction-history'])$(id).textContent='';$('#workspace').hidden=true;$('#login-view').hidden=false;if($('#editor').open)$('#editor').close();}
async function api(path,method='GET',data){
 let response;
 try { response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-Requested-With':'MonCacao','X-CSRF-Token':state.csrf},body:data===undefined?undefined:JSON.stringify(data)}); }
 catch {throw new Error('Connexion indisponible. Votre saisie reste ouverte ; réessayez lorsque le réseau revient.');}
 const result=await response.json();
 if(!response.ok){if(response.status===401&&path!='/login')loginView();throw new Error(result.error||'Une erreur est survenue.');}
 return result;
}
function show(view){document.querySelectorAll('.view').forEach(el=>el.hidden=el.id!==view);document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.view===(view==='detail'?'producers':view)));$('#notice').hidden=true;window.scrollTo(0,0);}
function initials(name){return name.split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase();}
function renderProducers(){
 const query=$('#search').value.toLocaleLowerCase();
 const filtered=state.producers.filter(p=>`${p.name} ${p.region} ${p.phone}`.toLocaleLowerCase().includes(query));
 $('#producer-list').innerHTML=filtered.map(p=>`<article class="card producer-card"><span class="avatar">${esc(initials(p.name))}</span><h2>${esc(p.name)}</h2><p>${esc(p.region)}, ${esc(p.phone||'Téléphone non renseigné')}</p><p>${p.harvest_count} ${p.harvest_count > 1 ? 'récoltes enregistrées' : 'récolte enregistrée'}<br>${p.last_harvest?'Dernière récolte : '+prettyDate(p.last_harvest):'Première récolte à renseigner'}</p><button class="secondary" data-producer="${p.id}">Ouvrir la fiche</button></article>`).join('')||'<div class="card empty">'+(query?'Aucun producteur ne correspond à votre recherche.':'Aucun producteur pour le moment. Ajoutez votre première fiche pour commencer.')+'</div>';
 $('#recent-producers').innerHTML=state.producers.slice(0,5).map(p=>`<div class="producer-row"><span class="avatar">${esc(initials(p.name))}</span><div><p><strong>${esc(p.name)}</strong></p><small>${esc(p.region)}, ${p.harvest_count} ${p.harvest_count > 1 ? 'récoltes' : 'récolte'}</small></div><button class="text-button" data-producer="${p.id}" aria-label="Ouvrir la fiche de ${esc(p.name)}">Ouvrir</button></div>`).join('')||'<div class="empty">Votre suivi commence ici.<br>Ajoutez un producteur, puis sa première récolte.</div>';
}
async function refresh(){const [p,d]=await Promise.all([api('/producers'),api('/dashboard')]);state.producers=p.producers;renderProducers();$('#stats').innerHTML=[...(state.role==='producer'?[]:[['Producteurs suivis',d.producers,`${d.pending} sans récolte enregistrée`]]),['Récoltes enregistrées',d.harvests,'Toutes dates confondues'],['Cacao récolté',fmt(d.kg)+' kg','Poids total saisi'],['Montant des ventes',fmt(d.revenue),'FCFA, poids multiplié par prix de vente']].map(s=>`<article class="stat"><span>${s[0]}</span><strong>${s[1]}</strong><small>${s[2]}</small></article>`).join('');}
async function openProducer(id){const data=await api('/producers/'+id);state.detail=data;$('#detail-name').textContent=data.producer.name;$('#detail-meta').textContent=data.producer.region+', '+(data.producer.phone||'Téléphone non renseigné');$('#detail-notes').textContent=data.producer.notes;$('#harvest-list').innerHTML=data.harvests.length?`<table><thead><tr><th>Date de récolte</th><th>Surface</th><th>Poids</th><th>Prix / kg</th><th>Montant des ventes</th><th>Dépenses</th><th>Action</th></tr></thead><tbody>${data.harvests.map(h=>`<tr><td>${prettyDate(h.observed_on)}</td><td>${fmt(h.area_ha)} ha</td><td>${fmt(h.harvest_kg)} kg</td><td>${fmt(h.price_fcfa_kg)} FCFA</td><td>${fmt(h.harvest_kg*h.price_fcfa_kg)} FCFA</td><td>${fmt(h.cost_fcfa)} FCFA</td><td><button class="text-button" data-harvest="${h.id}">Consulter / modifier</button></td></tr>`).join('')}</tbody></table>`:'<div class="empty">Aucune récolte enregistrée. Saisissez les observations collectées sur le terrain.</div>';$('#advice-list').innerHTML=data.advice.map(a=>`<article class="card"><p>${esc(a.content)}</p><small>Saisi par ${esc(a.author)}, ${esc(a.created_at)}</small></article>`).join('')||`<p class="empty">${state.role==='producer'?'Vous n’avez pas encore ajouté de note.':'Aucun conseil enregistré pour ce producteur.'}</p>`;renderPredictions(data.predictions||[]);show('detail');}
function field(label,name,value='',type='text',extra=''){return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${extra}></label>`;}
function select(label,name,value){return `<label>${label}<select name="${name}">${['Non renseigné','Oui','Non'].map(v=>`<option${value===v?' selected':''}>${v}</option>`).join('')}</select></label>`;}
function editor(mode,item=null){state.mode=mode;state.editId=item?.id??null;$('#editor-error').textContent='';let html='';
 if(mode==='producer'){$('#editor-title').textContent=state.role==='producer'?'Mes informations':item?'Modifier le producteur':'Ajouter un producteur';html=`<div class="form-grid">${field('Nom complet *','name',item?.name,'text','required maxlength="120"')}${field('Région / localité *','region',item?.region,'text','required maxlength="120"')}${field('Téléphone','phone',item?.phone,'tel','maxlength="40"')}<label class="full">Notes de suivi<textarea name="notes" maxlength="2000">${esc(item?.notes)}</textarea></label></div>`;}
 if(mode==='harvest'){const h=item||{};$('#editor-title').textContent=item?'Consulter / modifier la récolte':'Saisir une récolte';const today=new Date().toLocaleDateString('en-CA');html='<p class="help">Une ligne par producteur et par date. Saisissez le poids de cette récolte, et non un cumul déjà enregistré. La surface correspond à la parcelle concernée.</p><div class="form-grid">'+field('Date de récolte *','observed_on',h.observed_on||today,'date','required min="2000-01-01"')+field('Surface concernée (ha) *','area_ha',h.area_ha??'','number','required min="0.01" max="100000" step="any"')+field('Âge des cacaoyers (années) *','age_years',h.age_years??'','number','required min="0" max="150" step="any"')+field('Poids récolté (kg) *','harvest_kg',h.harvest_kg??'','number','required min="0" max="100000000" step="any"')+field('Prix de vente (FCFA/kg) *','price_fcfa_kg',h.price_fcfa_kg??'','number','required min="0" max="1000000" step="any"')+field('Dépenses pour cette récolte (FCFA) *','cost_fcfa',h.cost_fcfa??'','number','required min="0" max="100000000000" step="any"')+select('Autres arbres dans la plantation','agroforestry',h.agroforestry)+select('Maladie observée','disease',h.disease)+`<label class="full">Observations terrain<textarea name="notes" maxlength="2000">${esc(h.notes)}</textarea></label></div>`;}
 if(mode==='advice'){$('#editor-title').textContent=state.role==='producer'?'Ajouter une note':'Ajouter un conseil';html='<p class="help">Notez votre conseil à partir de ce que vous avez observé. Votre nom et la date seront ajoutés automatiquement.</p><label>Conseil ou prochaine action *<textarea name="content" maxlength="3000" required rows="6"></textarea></label>';}
 if(state.role==='producer'&&mode==='advice')html='<p class="help">Notez ce que vous avez observé ou les travaux à prévoir.</p><label>Ma note<textarea name="content" maxlength="3000" required rows="6"></textarea></label>';$('#editor-fields').innerHTML=html;$('#editor').showModal();
}
async function enter(result){state.role=result.user.role||'professional';configureAccount();state.csrf=result.csrf;$('#user-name').textContent=result.user.name;$('#login-view').hidden=true;$('#workspace').hidden=false;show('overview');await refresh();}
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('#login-error').textContent='';try{const result=await api('/login','POST',Object.fromEntries(new FormData(e.target)));e.target.reset();await enter(result);}catch(err){$('#login-error').textContent=err.message;}finally{b.disabled=false;}});
$('#logout').addEventListener('click',async()=>{try{await api('/logout','POST',{});loginView();}catch(err){notice(err.message,true);}});
$('#search').addEventListener('input',renderProducers);
$('#close-editor').onclick=$('#cancel-editor').onclick=()=>$('#editor').close();
$('#edit-producer').onclick=()=>editor('producer',state.detail.producer);
$('#new-harvest').onclick=()=>editor('harvest');$('#new-advice').onclick=()=>editor('advice');
document.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b)return;try{if(b.dataset.view){if(state.role==='producer'&&b.dataset.view==='producers'){await openProducer(state.producers[0].id);}else show(b.dataset.view);}if(b.dataset.selfAction){await openProducer(state.producers[0].id);if(b.dataset.selfAction==='prediction')await predictionEditor();if(b.dataset.selfAction==='harvest')editor('harvest');}if(b.dataset.action==='new-producer')editor('producer');if(b.dataset.producer)await openProducer(b.dataset.producer);if(b.dataset.harvest)editor('harvest',state.detail.harvests.find(h=>h.id===Number(b.dataset.harvest)));if(b.dataset.export){b.disabled=true;const r=await fetch('/api/export/'+b.dataset.export);if(!r.ok){if(r.status===401)loginView();throw new Error('Export indisponible. Reconnectez-vous puis réessayez.');}const url=URL.createObjectURL(await r.blob());const a=document.createElement('a');a.href=url;a.download='moncacao-'+b.dataset.export+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);notice('Fichier téléchargé.');}}catch(err){notice(err.message,true);}finally{if(b.dataset.export)b.disabled=false;}});
$('#editor-form').addEventListener('submit',async e=>{e.preventDefault();const b=e.submitter;b.disabled=true;$('#editor-error').textContent='';const data=Object.fromEntries(new FormData(e.target));try{let id=state.detail?.producer.id;if(state.mode==='producer'){if(state.editId){await api('/producers/'+state.editId,'PUT',data);id=state.editId;}else{id=(await api('/producers','POST',data)).id;}}else if(state.mode==='harvest'){for(const k of ['area_ha','age_years','harvest_kg','price_fcfa_kg','cost_fcfa'])data[k]=Number(data[k]);await api('/producers/'+id+'/harvests'+(state.editId?'/'+state.editId:''),state.editId?'PUT':'POST',data);}else if(state.mode==='prediction'){const inputs={};for(const f of state.predictionSchema.fields)inputs[f.name]=f.type==='number'?Number(data[f.name]):data[f.name];await api('/producers/'+id+'/predictions','POST',{inputs,area_ha:Number(data.area_ha)});}else{await api('/producers/'+id+'/advice','POST',data);}$('#editor').close();await refresh();await openProducer(id);notice('Les informations sont enregistrées.');}catch(err){$('#editor-error').textContent=err.message;}finally{b.disabled=false;}});
// Retire the previous offline cache; authenticated records are not cached on this browser.
async function retireLegacyWorker(){if('serviceWorker' in navigator){for(const reg of await navigator.serviceWorker.getRegistrations()){if(reg.active?.scriptURL===location.origin+'/sw.js')await reg.unregister();}}if('caches' in window){for(const name of await caches.keys())if(name.startsWith('mon-cacao-'))await caches.delete(name);}}
retireLegacyWorker().catch(()=>{});
api('/me').then(enter).catch(err=>{if(!$('#workspace').hidden)notice(err.message,true);});

const predictionLabels = { 'Coût_production/ha':'Dépenses par hectare (FCFA)', Age_verger:'Âge des cacaoyers (années)', Pluviometrie:'Quantité de pluie', Niveau_education:'Niveau scolaire', Competences:'Lecture et écriture', Agroforesterie:'Autres arbres dans la plantation', 'fumier/ compost':'Fumier ou compost', Herbicide:'Produit contre les mauvaises herbes', Insecticide:'Produit contre les insectes', Fongicide:'Produit contre les champignons' };
function renderPredictions(predictions){
 $('#prediction-history').innerHTML=predictions.map(p=>`<article class="card prediction-card"><span class="pill">Estimation, ${esc(p.created_at)} UTC</span><h3>${new Intl.NumberFormat('fr-FR',{maximumFractionDigits:3}).format(p.productivity_t_ha)} t/ha</h3><p>Soit <strong>${fmt(p.estimated_total_kg)} kg estimés</strong> pour ${fmt(p.area_ha)} ha.</p><small>Saisi par ${esc(p.author)}</small><details><summary>Voir les informations utilisées</summary><dl>${Object.entries(p.inputs).map(([key,value])=>`<dt>${esc(predictionLabels[key]||key)}</dt><dd>${esc(value)}</dd>`).join('')}</dl></details></article>`).join('')||`<div class="card empty">${state.role==='producer'?'Vous n’avez pas encore fait d’estimation. Complétez les informations de votre plantation pour commencer.':'Aucune estimation pour ce producteur. Ajoutez les informations de sa plantation pour faire le calcul.'}</div>`;
}
async function predictionEditor(){
 const button=$('#new-prediction');button.disabled=true;
 try{
  const schema=await api('/prediction-schema');state.predictionSchema=schema;state.mode='prediction';state.editId=null;
  const previous=state.detail.predictions?.[0];const harvest=state.detail.harvests?.[0];
  const defaults={...(previous?.inputs||{})};
  if(!previous&&harvest)defaults.Age_verger=harvest.age_years;
  if(!previous)defaults['Région']=state.detail.producer.region;
  $('#editor-title').textContent='Estimer la récolte';$('#editor-error').textContent='';
  $('#editor-fields').innerHTML='<p class="help">Complétez les informations sur la plantation. Indiquez les dépenses pour un hectare, en FCFA.</p><div class="form-grid">'+field('Surface de la plantation (ha) *','area_ha',previous?.area_ha??harvest?.area_ha??'','number','required min="0.01" max="100000" step="any"')+schema.fields.map(f=>{
   if(f.type==='number')return field(f.label+' *',f.name,defaults[f.name]??'','number',`required min="${f.minimum}" max="${f.maximum}" step="any"`);
   return `<label>${esc(f.label)} *<select name="${esc(f.name)}" required><option value="">Choisir</option>${f.options.map(o=>`<option value="${esc(o)}"${o===defaults[f.name]?' selected':''}>${esc(o)}</option>`).join('')}</select></label>`;
  }).join('')+'</div><p class="help">Le résultat sera enregistré dans votre historique. Les récoltes déjà enregistrées ne seront pas modifiées.</p>';
  $('#editor').showModal();
 }catch(err){notice(err.message,true);}finally{button.disabled=false;}
}
$('#new-prediction').addEventListener('click',predictionEditor);

function configureAccount(){
 const personal=state.role==='producer';
 $('#account-label').textContent=personal?'Espace producteur':'Espace professionnel';
 document.querySelector('nav [data-view="overview"]').textContent=personal?'Mes récoltes':'Résumé';
 document.querySelector('#overview .section-heading [data-view="producers"]').textContent=personal?'Ouvrir':'Voir tous';
 $('#overview-title').textContent=personal?'Mes récoltes':'Résumé';
 $('#overview-description').textContent=personal?'Retrouvez vos récoltes enregistrées et estimez votre production.':'Le total des récoltes que vous avez enregistrées.';
 document.querySelectorAll('[data-action="new-producer"]').forEach(b=>b.hidden=personal);
 document.querySelector('nav [data-view="producers"]').textContent=personal?'Ma plantation':'Mes producteurs';
 document.querySelector('#detail [data-view]').textContent=personal?'Retour à mes récoltes':'Retour aux producteurs';
 document.querySelector('#detail [data-view]').dataset.view=personal?'overview':'producers';
 $('#detail-label').textContent=personal?'MA PLANTATION':'FICHE PRODUCTEUR';
 $('#edit-producer').textContent=personal?'Mes informations':'Modifier la fiche';
 $('#producer-actions').hidden=!personal;
 $('#stats').classList.toggle('personal-stats',personal);
 $('#recent-title').textContent=personal?'Ma plantation':'Vos producteurs';
 $('#advice-title').textContent=personal?'Mes notes de suivi':'Conseils et suivi';
 $('#new-advice').textContent=personal?'Ajouter une note':'Ajouter un conseil';
 $('#advice-help').textContent=personal?'Gardez une trace des travaux réalisés et des problèmes observés.':'Notez ici vos conseils au producteur. Faites vérifier les conseils techniques par un spécialiste agricole.';
}
$('#show-register').onclick=()=>{$('#login-form').hidden=true;$('#register-form').hidden=false;$('#register-error').textContent='';};
$('#show-login').onclick=()=>{$('#register-form').hidden=true;$('#login-form').hidden=false;};
$('#register-form').addEventListener('submit',async e=>{
 e.preventDefault();const b=e.submitter;b.disabled=true;$('#register-error').textContent='';
 const data=Object.fromEntries(new FormData(e.target));
 try{
  if(data.password!==data.password_confirm)throw new Error('Les deux mots de passe doivent être identiques.');
  await api('/register','POST',data);
  e.target.reset();$('#register-form').hidden=true;$('#login-form').hidden=false;
  $('#login-form [name="email"]').value=data.email;
  $('#login-error').textContent='Votre compte est créé. Connectez-vous pour commencer.';
 }catch(err){$('#register-error').textContent=err.message;}finally{b.disabled=false;}
});
