#!/usr/bin/env python3
import os
from typing import Tuple, List, Dict, Any
from flask import Flask, jsonify, render_template_string, request
import psycopg2

app = Flask(__name__)

def env(k: str, d: str = "") -> str:
    return os.environ.get(k, d)

def db(host: str) -> psycopg2.extensions.connection:
    return psycopg2.connect(
        host=host,
        user=env("ERP_DB_USER"),
        password=env("ERP_DB_PASS"),
        dbname=env("ERP_DB_NAME"),
        connect_timeout=5,
    )

def one(conn, q: str, p: Tuple = ()) -> Any:
    with conn.cursor() as c:
        c.execute(q, p)
        r = c.fetchone()
        return r[0] if r else None

def all_(conn, q: str, p: Tuple = ()) -> List[Tuple]:
    with conn.cursor() as c:
        c.execute(q, p)
        return c.fetchall()

def hosts() -> Dict[str, str]:
    return {"branch_a": "127.0.0.1", "branch_b": env("ERP_REMOTE_DB_HOST")}

# cache for table columns
_TABLE_COLUMNS: Dict[str, List[str]] = {}

def table_allowed(table: str) -> bool:
    return table in ("inventory", "sales")

def table_columns(conn, table: str) -> List[str]:
    if table in _TABLE_COLUMNS:
        return _TABLE_COLUMNS[table]
    cols = []
    with conn.cursor() as c:
        c.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        cols = [r[0] for r in c.fetchall()]
    _TABLE_COLUMNS[table] = cols
    return cols

def to_json_row(cols: List[str], row: Tuple) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for i, col in enumerate(cols):
        v = row[i]
        # stringify types that are not JSON-serializable (e.g., Decimal, datetime)
        if hasattr(v, 'isoformat'):
            out[col] = v.isoformat()
        else:
            try:
                import decimal
                if isinstance(v, decimal.Decimal):
                    out[col] = str(v)
                else:
                    out[col] = v
            except Exception:
                out[col] = v
    return out

INDEX_HTML = """<!doctype html><html><head>
<meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>ERP Sync Dashboard</title>
<style>
:root{--bg:#0e1116;--card:#151a22;--muted:#9aa4b2;--acc:#40c463;--acc2:#58a6ff;--err:#ff6b6b;--warn:#f2c744;--text:#dce2ea}
*{box-sizing:border-box}
body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;margin:0;background:var(--bg);color:var(--text)}
header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;background:#0b0f14;border-bottom:1px solid #1f2630;position:sticky;top:0;z-index:5}
header h1{margin:0;font-size:18px;letter-spacing:.5px}
.container{padding:20px;max-width:1200px;margin:0 auto}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.card{background:var(--card);border:1px solid #1f2630;border-radius:12px;padding:16px;box-shadow:0 4px 20px rgba(0,0,0,.2)}
h2{margin:0 0 .75rem 0;font-size:14px;color:#cbd5e1;letter-spacing:.4px;text-transform:uppercase}
.table{border-collapse:collapse;width:100%;font-size:14px}
.table th,.table td{border-bottom:1px solid #222b36;padding:10px;text-align:left}
.badge{display:inline-block;padding:2px 8px;border-radius:100px;font-size:12px}
.ok{color:var(--acc)}.warn{color:var(--warn)}.err{color:var(--err)}
.btn{background:linear-gradient(135deg,var(--acc2),#7ee787);color:#0b0f14;border:none;padding:8px 12px;border-radius:8px;cursor:pointer;font-weight:600}
.btn.secondary{background:#1f2630;color:#cbd5e1}
.btn.danger{background:#3a2121;color:#ffb4b4}
.input{width:100%;background:#0e131b;border:1px solid #1f2630;color:#e5eaf0;padding:8px 10px;border-radius:8px}
.row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.kv{display:grid;grid-template-columns:140px 1fr;gap:8px;font-size:14px;color:#cbd5e1}
small{color:var(--muted)}
.tabbar{display:flex;gap:8px;margin:8px 0 0}
.tabbar .tab{padding:6px 10px;border-radius:8px;background:#0e131b;border:1px solid #1f2630;color:#cbd5e1;cursor:pointer}
.tabbar .tab.active{background:#1a2330;border-color:#2b3a4f;color:#e5f1ff}
.code{background:#0e131b;border:1px solid #1f2630;border-radius:8px;padding:8px;color:#cbd5e1;white-space:pre-wrap}
</style></head><body>
<header><h1>ERP Sync Dashboard</h1><div class="tabbar">
  <div class="tab active" id="tab-home" onclick="showTab('home')">Overview</div>
  <div class="tab" id="tab-inventory" onclick="showTab('inventory')">Inventory</div>
  <div class="tab" id="tab-sales" onclick="showTab('sales')">Sales</div>
</div></header>
<div class="container">
  <div id="view-home">
    <div class="grid">
      <div class="card"><h2>Status</h2><div id="status"></div></div>
      <div class="card"><h2>Counts</h2><div id="counts"></div></div>
      <div class="card"><h2>Health</h2><div id="health"></div></div>
    </div>
    <div class="card" style="margin-top:16px;"><h2>Recent Sync Logs</h2><div id="logs"></div></div>
  </div>

  <div id="view-inventory" style="display:none;">
    <div class="card"><h2>Create / Update Inventory</h2>
      <div class="row" style="margin-bottom:10px;">
        <input id="inv-id" class="input" placeholder="id (blank for new)"/>
        <input id="inv-name" class="input" placeholder="product_name"/>
        <input id="inv-qty" class="input" type="number" placeholder="quantity"/>
        <input id="inv-price" class="input" type="number" step="0.01" placeholder="price"/>
      </div>
      <div class="row" style="grid-template-columns:repeat(4,1fr);">
        <input id="inv-branch" class="input" type="number" placeholder="branch_id (optional)"/>
        <button class="btn" onclick="saveInventory()">Save</button>
        <button class="btn secondary" onclick="clearInvForm()">Clear</button>
        <small id="inv-msg"></small>
      </div>
    </div>
    <div class="card" style="margin-top:16px;"><h2>Inventory (Branch‑A)</h2><div id="inventory"></div></div>
  </div>

  <div id="view-sales" style="display:none;">
    <div class="card"><h2>Sales (read-only)</h2><div id="sales"></div><small>Use DB or existing flows to create sales; UI create can be added later.</small></div>
  </div>
</div>
<script>
function showTab(name){
  for(const v of ['home','inventory','sales']){
    document.getElementById('view-'+v).style.display=(v===name)?'block':'none';
    document.getElementById('tab-'+v).classList.toggle('active', v===name)
  }
}
async function j(u, opt){const r=await fetch(u, opt); if(!r.ok){throw new Error(await r.text())} return await r.json()}
function ts(x){try{return new Date(x).toLocaleString()}catch(e){return x}}

async function refreshOverview(){
  try{
    const [st,ct,h,lg]=await Promise.all([
      j('/api/status'), j('/api/counts'), j('/health'), j('/api/logs?limit=20')
    ]);
    document.getElementById('status').innerHTML =
      `<div class="kv"><div>Last Success</div><div><span class="badge ok">${ts(st.last_success||'N/A')}</span></div></div>
       <div class="kv"><div>Last Failure</div><div><span class="badge err">${ts(st.last_failure||'N/A')}</span></div></div>
       <div class="kv"><div>Last Run Status</div><div><span class="badge ${st.last_status==='SUCCESS'?'ok':(st.last_status==='FAILURE'?'err':'')}">${st.last_status||'N/A'}</span></div></div>`;
    document.getElementById('counts').innerHTML =
      `<table class="table"><thead><tr><th>Branch</th><th>Inventory</th><th>Sales</th></tr></thead>
        <tbody>
          <tr><td>Branch‑A</td><td>${ct.branch_a.inventory}</td><td>${ct.branch_a.sales}</td></tr>
          <tr><td>Branch‑B</td><td>${ct.branch_b.inventory}</td><td>${ct.branch_b.sales}</td></tr>
        </tbody></table>`;
    document.getElementById('health').innerHTML =
      `<div class="kv"><div>Local DB</div><div><span class="badge ${h.local_db_ok?'ok':'err'}">${h.local_db_ok?'OK':'FAIL'}</span></div></div>
       <div class="kv"><div>Remote DB</div><div><span class="badge ${h.remote_db_ok?'ok':'err'}">${h.remote_db_ok?'OK':'FAIL'}</span></div></div>
       <div class="kv"><div>Last Sync Age (min)</div><div><span class="badge ${h.last_sync_min<=10?'ok':(h.last_sync_min<=30?'warn':'err')}">${h.last_sync_min}</span></div></div>`;
    document.getElementById('logs').innerHTML =
      `<table class="table"><thead><tr><th>Time</th><th>Records</th><th>Status</th><th>Type</th><th>Error</th></tr></thead>
        <tbody>${lg.map(l=>`<tr><td>${ts(l.sync_time)}</td><td>${l.records_synced}</td><td class="${l.status==='SUCCESS'?'ok':'err'}">${l.status}</td><td>${l.sync_type}</td><td><span class="code">${(l.error_message||'')}</span></td></tr>`).join('')}</tbody></table>`;
  }catch(e){document.getElementById('status').innerHTML='<span class="err">Failed to load</span>';console.error(e)}
}

function clearInvForm(){['inv-id','inv-name','inv-qty','inv-price','inv-branch'].forEach(id=>document.getElementById(id).value='');document.getElementById('inv-msg').textContent=''}
async function saveInventory(){
  const id=document.getElementById('inv-id').value.trim();
  const body={};
  const name=document.getElementById('inv-name').value.trim(); if(name) body.product_name=name;
  const qty=document.getElementById('inv-qty').value.trim(); if(qty) body.quantity=Number(qty);
  const price=document.getElementById('inv-price').value.trim(); if(price) body.price=price;
  const branch=document.getElementById('inv-branch').value.trim(); if(branch) body.branch_id=Number(branch);
  const url=id?`/api/inventory/${id}`:'/api/inventory';
  const method=id?'PUT':'POST';
  try{
    const r=await j(url,{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    document.getElementById('inv-msg').textContent = `Saved id=${r.id}`;
    clearInvForm();
    await loadInventory();
  }catch(e){document.getElementById('inv-msg').textContent = `Error: ${e.message}`}
}
async function loadInventory(){
  try{
    const rows=await j('/api/inventory?limit=100');
    const html = `<table class="table"><thead><tr><th>ID</th><th>Product</th><th>Qty</th><th>Price</th><th>Updated</th><th>Actions</th></tr></thead>
      <tbody>${rows.filter(r=>r.branch==='BRANCH-A').map(r=>
        `<tr>
           <td>${r.id}</td><td>${r.product_name||''}</td><td>${r.quantity||''}</td><td>${r.price||''}</td><td>${ts(r.last_updated)||''}</td>
           <td>
             <button class="btn secondary" onclick="prefillInv(${r.id},'${(r.product_name||'').replace(/'/g,"&#39;")}',${r.quantity||0},'${r.price||''}')">Edit</button>
             <button class="btn danger" onclick="delInv(${r.id})">Delete</button>
           </td>
         </tr>`).join('')}</tbody></table>`;
    document.getElementById('inventory').innerHTML = html;
  }catch(e){document.getElementById('inventory').innerHTML='<span class="err">Failed to load</span>'}
}
function prefillInv(id,name,qty,price){
  document.getElementById('inv-id').value=id;document.getElementById('inv-name').value=name;document.getElementById('inv-qty').value=qty;document.getElementById('inv-price').value=price
}
async function delInv(id){
  if(!confirm('Delete inventory id='+id+'?')) return;
  try{await j('/api/inventory/'+id,{method:'DELETE'});await loadInventory();}catch(e){alert('Delete failed: '+e.message)}
}

async function loadSales(){
  try{
    const rows=await j('/api/sales?limit=50');
    const cols = rows.length?Object.keys(rows[0]):[];
    const head = cols.map(c=>`<th>${c}</th>`).join('');
    const body = rows.map(r=>`<tr>${cols.map(c=>`<td>${r[c]!==undefined?r[c]:''}</td>`).join('')}</tr>`).join('');
    document.getElementById('sales').innerHTML = `<table class="table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
  }catch(e){document.getElementById('sales').innerHTML='<span class="err">Failed to load</span>'}
}

async function boot(){ await Promise.all([refreshOverview(), loadInventory(), loadSales()]); }
boot(); setInterval(refreshOverview,10000);
</script></body></html>"""

@app.route("/")
def index(): return render_template_string(INDEX_HTML)

@app.route("/api/status")
def api_status():
    res={"last_success":None,"last_failure":None,"last_status":None}
    try:
        with db("127.0.0.1") as c:
            res["last_success"]=one(c,"SELECT MAX(sync_time) FROM sync_logs WHERE status='SUCCESS'")
            res["last_failure"]=one(c,"SELECT MAX(sync_time) FROM sync_logs WHERE status='FAILURE'")
            res["last_status"]=one(c,"SELECT status FROM sync_logs ORDER BY sync_time DESC LIMIT 1")
    except Exception: pass
    return jsonify(res)

@app.route("/api/counts")
def api_counts():
    out={"branch_a":{"inventory":0,"sales":0},"branch_b":{"inventory":0,"sales":0}}
    for k,h in hosts().items():
        try:
            with db(h) as c:
                out[k]["inventory"]=int(one(c,"SELECT COUNT(*) FROM inventory") or 0)
                out[k]["sales"]=int(one(c,"SELECT COUNT(*) FROM sales") or 0)
        except Exception: pass
    return jsonify(out)

@app.route("/api/logs")
def api_logs():
    limit=int(request.args.get("limit","50"))
    rows=[]
    try:
        with db("127.0.0.1") as c:
            rs=all_(c,"SELECT sync_time,records_synced,status,COALESCE(error_message,''),sync_type FROM sync_logs ORDER BY sync_time DESC LIMIT %s",(limit,))
            rows=[{"sync_time":r[0],"records_synced":r[1],"status":r[2],"error_message":r[3],"sync_type":r[4]} for r in rs]
    except Exception: pass
    return jsonify(rows)

@app.route("/api/inventory")
def api_inventory():
    limit=int(request.args.get("limit","20"))
    out=[]
    for b,h in {"BRANCH-A":"127.0.0.1","BRANCH-B":env("ERP_REMOTE_DB_HOST")}.items():
        try:
            with db(h) as c:
                rs=all_(c,"SELECT id,product_name,quantity,price,last_updated FROM inventory ORDER BY last_updated DESC,id DESC LIMIT %s",(limit,))
                out.extend([{"branch":b,"id":r[0],"product_name":r[1],"quantity":r[2],"price":str(r[3]),"last_updated":r[4]} for r in rs])
        except Exception: pass
    out.sort(key=lambda r:(str(r["last_updated"]),r["id"]),reverse=True)
    return jsonify(out)

@app.route("/health")
def health():
    local_ok=False; remote_ok=False; last_sync_min=99999
    try:
        with db("127.0.0.1") as c:
            local_ok=True
            v=one(c,"SELECT COALESCE(EXTRACT(EPOCH FROM (NOW()-MAX(sync_time)))/60,99999) FROM sync_logs WHERE status='SUCCESS'")
            last_sync_min=int(v) if v is not None else 99999
    except Exception: pass
    try:
        with db(env("ERP_REMOTE_DB_HOST")) as c:
            remote_ok=True
    except Exception: remote_ok=False
    return jsonify({"local_db_ok":local_ok,"remote_db_ok":remote_ok,"last_sync_min":last_sync_min})

# Generic CRUD for local Branch-A DB
@app.route('/api/<table>', methods=['GET','POST'])
def table_list_create(table: str):
    if not table_allowed(table):
        return jsonify({"error":"table not allowed"}), 400
    if request.method == 'GET':
        limit=int(request.args.get('limit','50'))
        try:
            with db("127.0.0.1") as c:
                cols = table_columns(c, table)
                collist = ", ".join(['"' + x.replace('"','""') + '"' for x in cols])
                with c.cursor() as cur:
                    cur.execute(f"SELECT {collist} FROM {table} ORDER BY 1 DESC LIMIT %s", (limit,))
                    rows = [to_json_row(cols, r) for r in cur.fetchall()]
                return jsonify(rows)
        except Exception as e:
            return jsonify({"error":str(e)}), 500
    # POST create
    data = request.get_json(silent=True) or {}
    try:
        with db("127.0.0.1") as c:
            cols = table_columns(c, table)
            body_keys = [k for k in data.keys() if k in cols and k != 'id']
            if not body_keys:
                return jsonify({"error":"no valid columns"}), 400
            placeholders = ', '.join(['%s']*len(body_keys))
            collist_ins = ', '.join(['"' + k.replace('"','""') + '"' for k in body_keys])
            values = tuple([data[k] for k in body_keys])
            with c.cursor() as cur:
                cur.execute(f"INSERT INTO {table} ({collist_ins}) VALUES ({placeholders}) RETURNING id", values)
                new_id = cur.fetchone()[0]
                c.commit()
            with c.cursor() as cur:
                collist = ", ".join(['"' + x.replace('"','""') + '"' for x in cols])
                cur.execute(f"SELECT {collist} FROM {table} WHERE id=%s", (new_id,))
                row = cur.fetchone()
            return jsonify(to_json_row(cols, row))
    except Exception as e:
        return jsonify({"error":str(e)}), 500

@app.route('/api/<table>/<int:item_id>', methods=['GET','PUT','PATCH','DELETE'])
def table_item(table: str, item_id: int):
    if not table_allowed(table):
        return jsonify({"error":"table not allowed"}), 400
    try:
        with db("127.0.0.1") as c:
            cols = table_columns(c, table)
            collist = ", ".join(['"' + x.replace('"','""') + '"' for x in cols])
            if request.method == 'GET':
                with c.cursor() as cur:
                    cur.execute(f"SELECT {collist} FROM {table} WHERE id=%s", (item_id,))
                    row = cur.fetchone()
                    if not row: return jsonify({"error":"not found"}), 404
                    return jsonify(to_json_row(cols, row))
            if request.method in ('PUT','PATCH'):
                data = request.get_json(silent=True) or {}
                keys = [k for k in data.keys() if k in cols and k != 'id']
                if not keys:
                    return jsonify({"error":"no valid columns"}), 400
                sets = ', '.join(['"' + k.replace('"','""') + '"=%s' for k in keys])
                values = tuple([data[k] for k in keys]) + (item_id,)
                with c.cursor() as cur:
                    cur.execute(f"UPDATE {table} SET {sets} WHERE id=%s", values)
                    c.commit()
                    cur.execute(f"SELECT {collist} FROM {table} WHERE id=%s", (item_id,))
                    row = cur.fetchone()
                    if not row: return jsonify({"error":"not found"}), 404
                    return jsonify(to_json_row(cols, row))
            if request.method == 'DELETE':
                with c.cursor() as cur:
                    cur.execute(f"DELETE FROM {table} WHERE id=%s", (item_id,))
                    c.commit()
                return jsonify({"deleted":True,"id":item_id})
    except Exception as e:
        return jsonify({"error":str(e)}), 500

if __name__=="__main__": app.run(host="0.0.0.0",port=8080)
