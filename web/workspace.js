'use strict';
const $=s=>document.querySelector(s);
const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let session=null,config=null,files={},poll=null,deleteId=null,refreshing=false;
const states={VALIDATING:'Validando lote',READY:'Listo para generar',INVALID:'Requiere corrección',RUNNING:'Generando reporte',SUCCEEDED:'Reporte disponible',FAILED:'Ejecución fallida'};
function message(text=''){ $('#message').textContent=text; }
async function api(path,{method='GET',body}={}){
 const response=await fetch(path,{method,credentials:'same-origin',headers:{...(body?{'Content-Type':'application/json'}:{}),...(method!=='GET'?{'X-CSRF-Token':session?.csrf||''}:{})},...(body?{body:JSON.stringify(body)}:{})});
 let result;try{result=await response.json()}catch{throw Error('El backend no está disponible. Iniciá python3 -m siter.server serve y abrí su URL.')}
 if(!response.ok){if(response.status===401&&path!=='/api/login')showLogin();throw Error(result.error||'No se pudo completar la solicitud')}
 return result;
}
function showLogin(){session=null;clearTimeout(poll);files={};$('#files-input').value='';$('#attestation').checked=false;$('#workspace').hidden=true;$('#login').hidden=false;$('#identity').replaceChildren();$('#runs').replaceChildren()}
function fileList(){$('#file-list').innerHTML=Object.keys(files).map(name=>`<li>${escapeHTML(name)} · ${new Blob([files[name]]).size.toLocaleString('es-AR')} bytes</li>`).join('')}
function sourceChanged(){const bq=$('#source-input').value!=='csv';if(bq)delete files['transactions.csv'];fileList();$('#source-note').textContent=bq?'Se leerá la tabla autorizada, sin SQL de usuario. Adjuntá los CSV complementarios. El modelo se ejecuta en Python; no implica paridad SQL en cloud.':'UTF-8, separador coma. Hasta 100.000 filas por archivo y 24 MiB por solicitud.'}
async function openWorkspace(){
 config=await api('/api/config');$('#retention-note').textContent=config.ephemeral?'Demo gratuita: los usuarios, las sesiones y los archivos se reinician cuando el servidor se reinicia. Descargá tus resultados al terminar; no se garantiza conservarlos 24 horas. Solo datos anonimizados, sin presentación ante ARCA.':'Solo datos sintéticos o anonimizados. Los lotes vencen a las 24 horas y podés eliminarlos antes. Sin presentación ante ARCA.';$('#login').hidden=true;$('#workspace').hidden=false;
 $('#identity').innerHTML=`<span>${escapeHTML(session.username)}</span><button class="button small" id="logout">Salir</button>`;
 $('#logout').onclick=async()=>{try{await api('/api/logout',{method:'POST'});showLogin();message()}catch(e){message(e.message)}};
 $('#period-input').innerHTML=[...config.rules.valid_periods].reverse().map(p=>`<option>${escapeHTML(p)}</option>`).join('');
 $('#rules-input').innerHTML=`<option>${escapeHTML(config.rules.rules_id)}</option>`;
 $('#reporter-input').value=config.rules.synthetic_reporter_cuit;$('#entity-input').value=String(config.rules.synthetic_entity_code).padStart(5,'0');
 $('#source-input').innerHTML='<option value="csv">Archivos CSV</option>'+config.sources.map(s=>`<option value="${escapeHTML(s.id)}">BigQuery · ${escapeHTML(s.label)}</option>`).join('');
 $('#contract').innerHTML='<p class="sub">Importes en centavos enteros. Identificadores como texto, conservando ceros iniciales. CUIT y CBU sustitutos deben conservar dígitos verificadores válidos.</p>'+Object.entries(config.contract.files).map(([name,f])=>`<details class="contract-item"><summary><strong>${escapeHTML(name)}</strong> · ${f.required?'Obligatorio':'Opcional'}</summary><dl>${Object.entries(f.columns).map(([field,type])=>`<dt>${escapeHTML(field)}</dt><dd>${escapeHTML(type)}</dd>`).join('')}</dl></details>`).join('')+'<p class="sub">synthetic_name contiene un alias ficticio. No se verifica automáticamente la anonimización. Los saldos deben conciliar con los movimientos del período.</p>';
 fileList();await refresh();
}
async function refresh(){
 if(!session||refreshing)return;refreshing=true;clearTimeout(poll);
 try{
 const runs=await api('/api/runs');
 $('#runs').innerHTML=runs.length?runs.map(r=>{
  const audit=r.detail.audit,errors=r.detail.errors||[],ready=r.state==='READY',done=r.state==='SUCCEEDED',active=['VALIDATING','RUNNING'].includes(r.state);
  return `<article class="run"><div class="run-top"><div><h3>${escapeHTML(r.config.period)} · ${r.config.presentation==='original'?'Original':'Rectificativa'} ${r.config.sequence}</h3><small>${new Date(r.created*1000).toLocaleString('es-AR')}</small></div><span class="tag ${done||ready?'green':''}" role="status">${states[r.state]||escapeHTML(r.state)}</span></div><p class="run-meta">${escapeHTML(r.id)} · CUIT ${escapeHTML(r.config.reporter_cuit)} · Entidad ${escapeHTML(r.config.entity_code)}<br>Eliminación programada: ${new Date(r.expires*1000).toLocaleString('es-AR')}</p>${errors.length?`<ul class="error-list">${errors.map(e=>`<li><strong>${escapeHTML(e.file||'Pipeline')}${e.row?` · fila ${e.row}`:''}${e.field?` · ${escapeHTML(e.field)}`:''}</strong>: ${escapeHTML(e.message)}</li>`).join('')}</ul><p class="sub">Corregí los archivos y cargá un nuevo lote. Se muestran hasta 100 errores.</p>`:''}${ready?`<p class="success-box">Validaciones aprobadas · ${r.detail.validation.reported_accounts} cuentas a informar · conciliación sin diferencias.</p>`:''}${done?`<p class="success-box">${audit.reported_accounts} cuentas informadas · ${audit.quality.period_transactions} movimientos del período · TXT validado.</p>`:''}<div class="form-actions">${ready?`<button class="button primary" data-execute="${r.id}">Generar reporte</button>`:''}${done?`<a class="button primary" href="/index.html?run=${r.id}">Revisar resultados</a>${['txt','zip','audit','accounts'].map(k=>`<a class="button" href="/api/runs/${r.id}/files/${k}" download>${k.toUpperCase()}</a>`).join('')}`:''}${!active?`<button class="button danger" data-delete="${r.id}">Eliminar lote</button>`:'<span class="sub">Podés cerrar esta página; el trabajo continúa en el servidor.</span>'}</div></article>`
 }).join(''):'<p class="sub">Todavía no hay ejecuciones. Cargá tus CSV o probá la muestra incluida.</p>';
 document.querySelectorAll('[data-execute]').forEach(b=>b.onclick=async()=>{b.disabled=true;try{await api(`/api/runs/${b.dataset.execute}/execute`,{method:'POST'});await refresh()}catch(e){message(e.message);b.disabled=false}});
 document.querySelectorAll('[data-delete]').forEach(b=>b.onclick=()=>{deleteId=b.dataset.delete;$('#delete-dialog').showModal()});
 }catch(e){message(e.message)}finally{refreshing=false;if(session)poll=setTimeout(refresh,2500)}
}
$('#login-form').onsubmit=async e=>{e.preventDefault();const button=e.target.querySelector('button');button.disabled=true;try{const data=new FormData(e.target);await api('/api/login',{method:'POST',body:Object.fromEntries(data)});e.target.reset();session=await api('/api/session');message();await openWorkspace()}catch(err){message(err.message)}finally{button.disabled=false}};
$('#files-input').onchange=async e=>{try{const selected=[...e.target.files];if(selected.reduce((n,f)=>n+f.size,0)>20*1024*1024)throw Error('El total de CSV no puede superar 20 MiB.');const next={};for(const file of selected){if(!config.contract.files[file.name])throw Error(`Archivo no admitido: ${file.name}`);if(file.name in next)throw Error(`Archivo duplicado: ${file.name}`);next[file.name]=new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer())}files=next;sourceChanged();message()}catch(err){files={};fileList();message(err.message)}};
$('#sample-button').onclick=async()=>{try{files=await api('/api/sample');$('#source-input').value='csv';$('#files-input').value='';sourceChanged();message('Muestra cargada. Confirmá el uso de datos ficticios y validá el lote.')}catch(e){message(e.message)}};
$('#source-input').onchange=sourceChanged;
$('#presentation-input').onchange=e=>{const replacement=e.target.value==='replacement';$('#sequence-input').readOnly=!replacement;$('#sequence-input').min=replacement?'1':'0';$('#sequence-input').value=replacement?'1':'0'};
$('#upload-form').onsubmit=async e=>{e.preventDefault();const button=$('#validate-button');button.disabled=true;try{
 const source=$('#source-input').value;const required=Object.entries(config.contract.files).filter(([name,f])=>f.required&&!(source!=='csv'&&name==='transactions.csv')).map(([name])=>name);
 const missing=required.filter(n=>!(n in files));if(missing.length)throw Error('Faltan archivos: '+missing.join(', '));
 const body={files,source,anonymized:$('#attestation').checked,config:{period:$('#period-input').value,rules_id:$('#rules-input').value,reporter_cuit:$('#reporter-input').value,entity_code:$('#entity-input').value,presentation:$('#presentation-input').value,sequence:Number($('#sequence-input').value)}};
 if(new Blob([JSON.stringify(body)]).size>config.max_body_bytes)throw Error('El lote supera el límite de 24 MiB por solicitud.');
 await api('/api/runs',{method:'POST',body});files={};$('#files-input').value='';$('#attestation').checked=false;fileList();message('Lote recibido. Podés seguir su validación en Mis ejecuciones.');await refresh();$('#runs').scrollIntoView({behavior:'smooth'});
 }catch(err){message(err.message)}finally{button.disabled=false}};
$('#refresh').onclick=refresh;$('#cancel-delete').onclick=()=>$('#delete-dialog').close();
$('#confirm-delete').onclick=async()=>{const b=$('#confirm-delete');b.disabled=true;try{await api(`/api/runs/${deleteId}`,{method:'DELETE'});$('#delete-dialog').close();message('Ejecución y archivos eliminados.');await refresh()}catch(e){message(e.message)}finally{b.disabled=false}};
(async()=>{try{session=await api('/api/session');await openWorkspace()}catch(e){showLogin();if(!e.message.includes('Sign in'))message(e.message)}})();
