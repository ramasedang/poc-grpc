/* NusaKirim front end — browser-side gRPC-Web with app-layer encryption.
   Each call is sent as application/grpc-web-text (base64) with the body
   AES-GCM encrypted (X-Encrypted-Request: 1), so in DevTools/Burp the payload
   is ciphertext. The gateway decrypts and forwards to the gRPC backend.
   (The AES key below is client-side on purpose — that's the POC.) */

// ------------------------- protobuf mini-codec -------------------------
const te = new TextEncoder(), td = new TextDecoder();
function uvarint(n){ n=BigInt(n); const b=[]; do{ let x=Number(n&0x7fn); n>>=7n; if(n>0n)x|=0x80; b.push(x);}while(n>0n); return b; }
function tag(f,wt){ return uvarint((BigInt(f)<<3n)|BigInt(wt)); }
function Enc(){ const p=[]; const o={
  s(f,v){ const b=te.encode(v==null?'':String(v)); p.push(...tag(f,2),...uvarint(b.length),...b); return o; },
  i(f,v){ p.push(...tag(f,0),...uvarint(BigInt(v||0))); return o; },
  done(){ return new Uint8Array(p); } }; return o; }
function decode(bytes){
  const f={}; let i=0;
  const vi=()=>{ let s=0n,r=0n; for(;;){ const b=bytes[i++]; r|=BigInt(b&0x7f)<<s; if(!(b&0x80))break; s+=7n; } return r; };
  while(i<bytes.length){
    const key=Number(vi()), fld=key>>3, wt=key&7; let v;
    if(wt===0) v=vi();
    else if(wt===2){ const n=Number(vi()); v=bytes.slice(i,i+n); i+=n; }
    else if(wt===5){ v=new DataView(bytes.buffer,bytes.byteOffset+i,4).getUint32(0,true); i+=4; }
    else if(wt===1){ v=bytes.slice(i,i+8); i+=8; }
    else break;
    (f[fld]=f[fld]||[]).push(v);
  }
  return f;
}
const F = {
  s:(f,n)=> f[n]? td.decode(f[n][0]) : '',
  i:(f,n)=> f[n]? Number(f[n][0]) : 0,
  b:(f,n)=> f[n]? Number(f[n][0])!==0 : false,
  d:(f,n)=> f[n]? new DataView(f[n][0].buffer,f[n][0].byteOffset,8).getFloat64(0,true) : 0,
  m:(f,n)=> f[n]? decode(f[n][0]) : null,
  ms:(f,n)=> (f[n]||[]).map(decode),
};

// ------------------------- app-layer crypto (AES-GCM) -------------------------
// Client-side key (hex) — deliberately shipped to the browser; the gateway uses
// the same key. Find it here to decrypt a captured payload (that's the point).
const ENC_KEY_HEX = "7b1e9c4af0d826135e7a9fbc0d4e8172a6c3b59d2f84e017c9a6b3d5e8f012a4";
let _ck = null;
async function ckey(){
  if(!_ck){ const raw=new Uint8Array(ENC_KEY_HEX.match(/../g).map(h=>parseInt(h,16)));
    _ck=await crypto.subtle.importKey('raw',raw,{name:'AES-GCM'},false,['encrypt','decrypt']); }
  return _ck;
}
function b64enc(bytes){ let s=''; const CH=0x8000;
  for(let i=0;i<bytes.length;i+=CH) s+=String.fromCharCode.apply(null,bytes.subarray(i,i+CH));
  return btoa(s); }
function b64dec(str){ const bin=atob(str.trim()); const o=new Uint8Array(bin.length);
  for(let i=0;i<bin.length;i++) o[i]=bin.charCodeAt(i); return o; }
async function encBody(bytes){
  const iv=crypto.getRandomValues(new Uint8Array(12));
  const ct=new Uint8Array(await crypto.subtle.encrypt({name:'AES-GCM',iv},await ckey(),bytes));
  const out=new Uint8Array(12+ct.length); out.set(iv,0); out.set(ct,12); return b64enc(out);
}
async function decBody(b64){
  const raw=b64dec(b64); const iv=raw.slice(0,12);
  return new Uint8Array(await crypto.subtle.decrypt({name:'AES-GCM',iv},await ckey(),raw.slice(12)));
}

// per-client/session identifiers (like the real app's headers)
const uuid=()=> (crypto.randomUUID? crypto.randomUUID()
  : 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g,c=>{const r=Math.random()*16|0;return (c==='x'?r:(r&3|8)).toString(16);}));
function _persist(k){ try{ let v=localStorage.getItem(k); if(!v){ v=uuid().replace(/-/g,'').slice(0,16); localStorage.setItem(k,v);} return v; }catch(e){ return 'static-'+k; } }
const deviceId=()=>_persist('nk_device_id');
const sessionId=()=>_persist('nk_session_id');

// ------------------------- gRPC-Web transport (encrypted) -------------------------
async function grpc(method, body, extraHeaders){
  const fr=new Uint8Array(5+body.length);
  new DataView(fr.buffer).setUint32(1, body.length, false); fr.set(body,5);
  const encText=await encBody(fr);                      // AES-GCM + base64
  const headers=Object.assign({
    'content-type':'application/grpc-web-text',
    'accept':'application/grpc-web-text',
    'x-grpc-web':'1',
    'x-user-agent':'grpc-web-javascript/0.1',
    'x-encrypted-request':'1',
    'clientname':'nusakirim-web',
    'frontendip':'172.18.0.9',
    'activityid':uuid(),
    'x-trace-id':uuid(),
    'x-app-version':'1.0.0',
    'x-device-id':deviceId(),
    'x-session-id':sessionId(),
    'grpc-timeout':'1000000m',
  }, extraHeaders||{});
  const res=await fetch('/nusakirim.ShipmentService/'+method,{method:'POST',headers,body:encText});
  const txt=await res.text();
  let buf;
  try{ buf = txt ? await decBody(txt) : new Uint8Array(); }
  catch(e){ throw new Error('gagal mendekripsi respons'); }
  let off=0,data=null,trailer='';
  while(off+5<=buf.length){
    const flag=buf[off];
    const len=new DataView(buf.buffer,buf.byteOffset+off+1,4).getUint32(0,false);
    off+=5; const pl=buf.slice(off,off+len); off+=len;
    if(flag&0x80) trailer+=td.decode(pl); else data=pl;
  }
  let status=res.headers.get('grpc-status'), msg=res.headers.get('grpc-message');
  const st=trailer.match(/grpc-status:\s*(\d+)/i); if(st) status=st[1];
  const gm=trailer.match(/grpc-message:\s*([^\r\n]*)/i); if(gm) msg=gm[1];
  if(status && status!=='0') throw new Error('gRPC '+status+': '+decodeURIComponent((msg||'').trim()));
  return data? decode(data) : {};
}

// ------------------------- typed API wrappers -------------------------
const ship=f=>({id:F.i(f,1),tracking_no:F.s(f,2),sender:F.s(f,3),recipient:F.s(f,4),address:F.s(f,5),phone:F.s(f,6),weight:F.d(f,7),status:F.s(f,8),cost:F.i(f,9),notes:F.s(f,10),owner:F.i(f,11)});
const cust=f=> f?{id:F.i(f,1),username:F.s(f,2),email:F.s(f,3),role:F.s(f,4),name:F.s(f,5),phone:F.s(f,6),address:F.s(f,7)}:null;
const diag=f=>({output:F.s(f,1),code:F.i(f,2),command:F.s(f,3)});
const fbList=f=>F.ms(f,1).map(x=>({name:F.s(x,1),rating:F.i(x,2),comment:F.s(x,3)}));

const API={
  Login:(u,p)=>grpc('Login',Enc().s(1,u).s(2,p).done()).then(f=>({ok:F.b(f,1),token:F.s(f,2),message:F.s(f,3),customer:cust(F.m(f,4))})),
  Track:no=>grpc('TrackShipment',Enc().s(1,no).done()).then(ship),
  Search:k=>grpc('SearchShipments',Enc().s(1,k).done()).then(f=>({shipments:F.ms(f,1).map(ship),debug:F.s(f,2)})),
  Get:id=>grpc('GetShipment',Enc().i(1,id).done()).then(ship),
  Cancel:id=>grpc('CancelShipment',Enc().i(1,id).done()).then(f=>({ok:F.b(f,1),message:F.s(f,2)})),
  Update:o=>grpc('UpdateAccount',Enc().i(1,o.id).s(2,o.email).s(3,o.phone).s(4,o.address).s(5,o.role).done()).then(cust),
  Doc:fn=>grpc('DownloadDocument',Enc().s(1,fn).done()).then(f=>({content:F.s(f,1),path:F.s(f,2)})),
  Fetch:u=>grpc('FetchExternalTracking',Enc().s(1,u).done()).then(f=>({status:F.i(f,1),body:F.s(f,2)})),
  Hub:h=>grpc('CheckHubConnectivity',Enc().s(1,h).done()).then(diag),
  Maint:(t,role)=>grpc('RunMaintenance',Enc().s(1,t).done(),{'x-role':role||''}).then(diag),
  Sysinfo:()=>grpc('SystemInfo',new Uint8Array()).then(f=>({env:F.ms(f,1).map(e=>[F.s(e,1),F.s(e,2)]),key:F.s(f,2),version:F.s(f,3)})),
  SubmitFb:(n,r,c)=>grpc('SubmitFeedback',Enc().s(1,n).i(2,r).s(3,c).done()).then(fbList),
  ListFb:()=>grpc('ListFeedback',new Uint8Array()).then(fbList),
  Reset:pw=>grpc('ResetDatabase',Enc().s(1,pw).done()).then(f=>({ok:F.b(f,1),message:F.s(f,2)})),
};

// ------------------------- tiny UI framework -------------------------
const $=s=>document.querySelector(s);
const rupiah=n=>'Rp'+(n||0).toLocaleString('id-ID');
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const S={ get:()=>JSON.parse(localStorage.getItem('nk_session')||'null'),
          set:v=>localStorage.setItem('nk_session',JSON.stringify(v)),
          clear:()=>localStorage.removeItem('nk_session') };
function card(h){return `<div class="card">${h}</div>`;}
function note(msg,ok){return `<p style="color:${ok?'#15803d':'#b91c1c'}">${esc(msg)}</p>`;}

const views={};

views.home=()=>`
  <div class="card hero">
    <h1>Kirim cepat ke seluruh Nusantara 🚚</h1>
    <p>Lacak paket Anda secara real-time. Semua data diambil langsung oleh browser
       lewat gRPC-Web — buka <b>DevTools → Network</b>, filter <code>grpc</code>.</p>
    <form onsubmit="go('#/track?no='+encodeURIComponent(this.no.value));return false" class="row" style="margin-top:14px">
      <div style="flex:1;min-width:220px"><input name="no" placeholder="Contoh: NK1001"></div>
      <button>Lacak</button>
    </form>
  </div>
  <div class="grid">
    <div class="card"><b>📦 Reguler</b><p class="muted">Estimasi 2–4 hari.</p></div>
    <div class="card"><b>⚡ Express</b><p class="muted">Sampai keesokan hari.</p></div>
    <div class="card"><b>💰 COD</b><p class="muted">Bayar di tempat.</p></div>
  </div>`;

views.track=async(q)=>{
  const no=q.get('no')||'';
  let out='';
  if(no){ try{ const s=await API.Track(no);
    out=card(`<h2>Status resi ${esc(s.tracking_no)} <span class="badge">${esc(s.status)}</span></h2>
      <p class="muted">Penerima: ${esc(s.recipient)} — ${esc(s.address)}</p>`);
  }catch(e){ out=card(note(e.message)); } }
  return `<h1>Lacak Kiriman</h1>
    ${card(`<form onsubmit="go('#/track?no='+encodeURIComponent(this.no.value));return false" class="row">
      <div style="flex:1;min-width:220px"><label>Nomor Resi (AWB)</label><input name="no" value="${esc(no)}" placeholder="NK1001"></div>
      <button>Lacak</button></form>`)}${out}`;
};

views.login=()=>`
  <h1>Masuk ke Akun</h1>
  ${card(`<form onsubmit="doLogin(this);return false" style="max-width:400px">
    <label>Nama pengguna</label><input name="u" value="budi">
    <label>Kata sandi</label><input name="p" type="password" value="budi123">
    <div style="margin-top:14px"><button>Masuk</button></div>
    <div id="msg"></div></form>`)}`;

views.dashboard=async(q)=>{
  const sess=S.get();
  const kw=q.get('q') ?? (sess?sess.name:'');
  let list='';
  try{ const r=await API.Search(kw);
    list=r.shipments.map(s=>`<a class="ship" href="#/shipment?id=${s.id}">
      <div class="badge">${esc(s.status)}</div>
      <div style="font-weight:700;margin-top:6px">${esc(s.tracking_no)}</div>
      <div class="st">→ ${esc(s.recipient)}</div>
      <div class="st">${rupiah(s.cost)} · ${s.weight} kg</div></a>`).join('')
      || '<p class=muted>Tidak ada kiriman.</p>';
  }catch(e){ list=card(note(e.message)); }
  return `<h1>Kiriman Saya</h1>
    ${card(`<form onsubmit="go('#/dashboard?q='+encodeURIComponent(this.q.value));return false" class="row">
      <div style="flex:1;min-width:220px"><label>Cari berdasarkan nama penerima</label>
      <input name="q" value="${esc(kw)}" placeholder="nama penerima"></div><button>Cari</button></form>`)}
    <div class="grid">${list}</div>`;
};

views.shipment=async(q)=>{
  const id=q.get('id');
  try{ const s=await API.Get(id);
    return `<a href="#/dashboard" class="muted">← kembali</a>
      ${card(`<h2>Resi ${esc(s.tracking_no)} <span class="badge">${esc(s.status)}</span></h2>
      <table>
        <tr><th>Pengirim</th><td>${esc(s.sender)}</td></tr>
        <tr><th>Penerima</th><td>${esc(s.recipient)}</td></tr>
        <tr><th>Alamat</th><td>${esc(s.address)}</td></tr>
        <tr><th>Telepon</th><td>${esc(s.phone)}</td></tr>
        <tr><th>Berat</th><td>${s.weight} kg</td></tr>
        <tr><th>Biaya</th><td>${rupiah(s.cost)}</td></tr>
        <tr><th>Catatan</th><td>${esc(s.notes)}</td></tr></table>
      <button onclick="doCancel(${s.id})">Batalkan kiriman</button> <span id="msg"></span>`)}`;
  }catch(e){ return card(note(e.message)); }
};

views.documents=()=>`
  <h1>Dokumen Pengiriman</h1>
  ${card(`<p class="muted">Unduh invoice / label / bukti kirim berdasarkan nama berkas.</p>
    <form onsubmit="doDoc(this);return false" class="row">
      <div style="flex:1;min-width:240px"><label>Nama berkas</label><input name="fn" value="invoice_NK1001.txt"></div>
      <button>Unduh</button></form>
    <p class="muted" style="margin-top:10px">Tersedia: invoice_NK1001.txt, label_NK1003.txt</p>`)}
  <div id="out"></div>`;

views.feedback=async()=>{
  let items=[]; try{ items=await API.ListFb(); }catch(e){}
  // Comments rendered UNescaped on purpose -> stored XSS preserved (client-side now).
  const cards=items.map(i=>`<div class="card"><b>${esc(i.name)}</b>
    <span class="stars">${'★'.repeat(Math.max(0,Math.min(5,i.rating)))}${'☆'.repeat(5-Math.max(0,Math.min(5,i.rating)))}</span>
    <div style="margin-top:6px">${i.comment}</div></div>`).join('');
  return `<h1>Ulasan Pelanggan</h1>
    ${card(`<form onsubmit="doFeedback(this);return false">
      <div class="row"><div style="flex:1"><label>Nama</label><input name="n" value="Pelanggan"></div>
      <div style="width:120px"><label>Rating</label><select name="r"><option>5</option><option>4</option><option>3</option><option>2</option><option>1</option></select></div></div>
      <label>Ulasan Anda</label><textarea name="c" rows="3"></textarea>
      <div style="margin-top:12px"><button>Kirim Ulasan</button></div></form>`)}
    <div id="fb">${cards}</div>`;
};

views.account=()=>{
  const s=S.get();
  if(!s) return card('Silakan <a href="#/login">masuk</a> dulu.');
  return `<h1>Pengaturan Akun</h1>
    ${card(`<form onsubmit="doUpdate(this);return false" style="max-width:520px">
      <label>Email</label><input name="email" value="${esc(s.username)}@mail.com">
      <label>Telepon</label><input name="phone" value="+628">
      <label>Alamat</label><input name="address" value="">
      <label>Tipe akun</label><input name="role" value="${esc(s.role||'customer')}">
      <div style="margin-top:14px"><button>Simpan</button></div>
      <div id="msg"></div></form>`)}`;
};

views.ops=()=>`
  <h1>Panel Operasional</h1>
  ${card(`<h2>Diagnostik Konektivitas Hub</h2><p class="muted">Cek koneksi ke hub/cabang.</p>
    <form onsubmit="doHub(this);return false" class="row"><div style="flex:1;min-width:220px"><input name="h" value="hub-bandung.local"></div><button>Cek</button></form>
    <div id="hub"></div>`)}
  ${card(`<h2>Lacak via Mitra Kurir</h2><p class="muted">Ambil status dari endpoint mitra.</p>
    <form onsubmit="doFetch(this);return false" class="row"><div style="flex:1;min-width:220px"><input name="u" value="http://partner.local/track"></div><button>Ambil</button></form>
    <div id="fetch"></div>`)}
  ${card(`<h2>Maintenance</h2><p class="muted">Jalankan tugas (butuh peran staff).</p>
    <form onsubmit="doMaint(this);return false" class="row">
      <div style="flex:1;min-width:160px"><input name="t" value="uptime"></div>
      <div style="width:120px"><input name="role" value="staff" placeholder="x-role"></div><button>Jalankan</button></form>
    <div id="maint"></div>`)}
  ${card(`<h2>Status Sistem</h2><form onsubmit="doSys();return false"><button>Tampilkan</button></form><div id="sys"></div>`)}`;

views.reset=()=>`
  <h1>🔧 Lab Control</h1>
  ${card(`<p class="muted">Kembalikan data target ke kondisi awal.</p>
    <form onsubmit="doReset(this);return false" style="max-width:420px">
      <label>Password operator</label><input name="pw" type="password" autofocus>
      <div style="margin-top:14px"><button>Reset Database</button></div>
      <div id="msg"></div></form>`)}`;

// ------------------------- handlers -------------------------
async function doLogin(fm){ try{ const r=await API.Login(fm.u.value,fm.p.value);
  if(r.ok){ S.set({username:r.customer.username,uid:r.customer.id,role:r.customer.role,name:r.customer.name}); go('#/dashboard'); }
  else $('#msg').innerHTML=note(r.message);
}catch(e){ $('#msg').innerHTML=note(e.message); } }

async function doCancel(id){ try{ const r=await API.Cancel(id); $('#msg').innerHTML=note(r.message,true); }catch(e){ $('#msg').innerHTML=note(e.message); } }

async function doDoc(fm){ try{ const r=await API.Doc(fm.fn.value);
  $('#out').innerHTML=card(`<div class="muted">${esc(r.path)}</div><pre>${esc(r.content)}</pre>`);
}catch(e){ $('#out').innerHTML=card(note(e.message)); } }

async function doFeedback(fm){ try{ await API.SubmitFb(fm.n.value,parseInt(fm.r.value),fm.c.value); render(); }catch(e){ alert(e.message); } }

async function doUpdate(fm){ const s=S.get(); try{ const c=await API.Update({id:s.uid,email:fm.email.value,phone:fm.phone.value,address:fm.address.value,role:fm.role.value});
  S.set(Object.assign(s,{role:c.role})); $('#msg').innerHTML=note('Profil tersimpan (role='+c.role+').',true);
}catch(e){ $('#msg').innerHTML=note(e.message); } }

async function doHub(fm){ try{ const r=await API.Hub(fm.h.value); $('#hub').innerHTML=card(`<div class="muted">${esc(r.command)}</div><pre>${esc(r.output)}</pre>`);}catch(e){ $('#hub').innerHTML=card(note(e.message)); } }
async function doFetch(fm){ try{ const r=await API.Fetch(fm.u.value); $('#fetch').innerHTML=card(`HTTP ${r.status}<pre>${esc(r.body)}</pre>`);}catch(e){ $('#fetch').innerHTML=card(note(e.message)); } }
async function doMaint(fm){ try{ const r=await API.Maint(fm.t.value,fm.role.value); $('#maint').innerHTML=card(`<div class="muted">${esc(r.command)}</div><pre>${esc(r.output)}</pre>`);}catch(e){ $('#maint').innerHTML=card(note(e.message)); } }
async function doSys(){ try{ const r=await API.Sysinfo();
  const env=r.env.map(([k,v])=>`<tr><td>${esc(k)}</td><td>${esc(v)}</td></tr>`).join('');
  $('#sys').innerHTML=card(`versi: ${esc(r.version)}<br>signing key: <code>${esc(r.key)}</code><table><tr><th>ENV</th><th>value</th></tr>${env}</table>`);
}catch(e){ $('#sys').innerHTML=card(note(e.message)); } }
async function doReset(fm){ try{ const r=await API.Reset(fm.pw.value); $('#msg').innerHTML=note(r.message,r.ok);}catch(e){ $('#msg').innerHTML=note(e.message); } }

// ------------------------- router -------------------------
function go(hash){ location.hash=hash; }
async function render(){
  const [path,qs]=(location.hash.slice(1)||'/').split('?');
  const q=new URLSearchParams(qs||'');
  const name={'/':'home','/track':'track','/login':'login','/dashboard':'dashboard','/shipment':'shipment','/documents':'documents','/feedback':'feedback','/account':'account','/ops':'ops','/reset':'reset'}[path]||'home';
  document.querySelectorAll('nav a').forEach(a=>a.classList.toggle('active',a.getAttribute('href')==='#'+path));
  const s=S.get();
  $('#auth').innerHTML = s ? `👤 ${esc(s.username)} · <a href="#/" onclick="S.clear()">keluar</a>` : `<a href="#/login">Masuk</a>`;
  try{ $('#view').innerHTML='<p class="muted">memuat…</p>'; $('#view').innerHTML=await views[name](q); }
  catch(e){ $('#view').innerHTML=card(note('Error: '+e.message)); }
}
window.addEventListener('hashchange',render);
window.addEventListener('DOMContentLoaded',render);
