"""ONE PIECE LIFE community prototype: FastAPI + SQLite + OpenAI API GM (Render, no GPU server)."""
import os,json,sqlite3,secrets,hashlib,hmac,random,time,re,urllib.request
from pathlib import Path
from contextlib import contextmanager
from fastapi import FastAPI,HTTPException,Request,Response
from fastapi.responses import FileResponse
from pydantic import BaseModel,Field

ROOT=Path(__file__).resolve().parent
DB=os.getenv('DATABASE_PATH',str(ROOT/'game.sqlite3'))
AI_URL='https://api.openai.com/v1'
AI_MODEL=os.getenv('OPENAI_MODEL','gpt-4.1-mini')
AI_TOKEN=os.getenv('OPENAI_API_KEY','')
COOKIE_SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true'
app=FastAPI(title='ONE PIECE LIFE')
STAT_KEYS=['근력','타격 파괴력','순간 폭발력','최고 속도','반응속도','민첩성','신체 내구력','지구력','검술 숙련도','격투술 숙련도','전투 판단력','전술 적응력','집중력','의지력']
RACES=['인간','어인족','인어족','거인족','소인족','밍크족','하늘섬 주민','루나리아족','긴팔족','긴다리족','삼안족']
FACTIONS=['해적','해군','혁명군','세계정부','시민']
PATHS={'해적':['독립 해적','해적단 선원','현상금 사냥꾼'], '해군':['해군 병사','해군 장교 후보'], '혁명군':['혁명군 신입','정보원'], '세계정부':['CP5 요원','임펠 다운 간수','행정직'], '시민':['항해사','상인','의사','모험가','조선공']}
CANON=[{'id':'luffy_departure','day':0,'name':'루피 출항','location':'후샤 마을','status':'canon_reference'}, {'id':'shells_town','day':3,'name':'셸즈 타운의 소동','location':'셸즈 타운','status':'gameplay_assumption'}, {'id':'orange_town','day':7,'name':'오렌지 타운의 소동','location':'오렌지 타운','status':'gameplay_assumption'}]
MASTER=(ROOT/'rules/master_rules.txt').read_text(encoding='utf-8')
EXT=(ROOT/'rules/extension_rules.txt').read_text(encoding='utf-8')
# First sections are high-priority rules; full texts remain shipped for future retrieval.
RULE_CONTEXT=MASTER[:14500]+'\n\n확장 규칙:\n'+EXT[:10500]

@contextmanager
def db():
    c=sqlite3.connect(DB,timeout=15);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
    try: yield c; c.commit()
    finally:c.close()

def init():
    Path(DB).parent.mkdir(parents=True,exist_ok=True)
    with db() as c:
        c.execute('PRAGMA journal_mode=WAL')
        c.executescript('''CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, salt TEXT NOT NULL, password_hash TEXT NOT NULL, created INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id INTEGER NOT NULL,expires INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS games(user_id INTEGER PRIMARY KEY,state TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0,updated INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));
        CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL,role TEXT NOT NULL,content TEXT NOT NULL,created INTEGER NOT NULL,FOREIGN KEY(user_id) REFERENCES users(id));''')
init()

def hashpass(p,s):return hashlib.scrypt(p.encode(),salt=bytes.fromhex(s),n=16384,r=8,p=1).hex()
def auth(req):
    tok=req.cookies.get('opl_session','')
    if not tok:raise HTTPException(401,'로그인이 필요합니다.')
    with db() as c:
        row=c.execute('SELECT user_id FROM sessions WHERE token_hash=? AND expires>?',(hashlib.sha256(tok.encode()).hexdigest(),int(time.time()))).fetchone()
    if not row:raise HTTPException(401,'세션이 만료되었습니다.')
    return row['user_id']

def fresh():return {'phase':'race','race':None,'faction':None,'path':None,'answers':[],'name':None,'level':1,'xp':0,'level_pending':0,'stats':{},'hp':100,'max_hp':100,'fatigue':0,'berries':0,'bounty':0,'skills':[],'inventory':[],'crew':[],'npc_memory':[],'quests':[],'day':0,'minute':480,'location':'이스트 블루','turn':0,'timeline':[],'branches':[],'last_scene':'','combat':None}
def load(uid):
    with db() as c:
        r=c.execute('SELECT state,version FROM games WHERE user_id=?',(uid,)).fetchone()
        if r:return json.loads(r['state']),r['version']
        s=fresh();c.execute('INSERT INTO games(user_id,state,updated) VALUES(?,?,?)',(uid,json.dumps(s,ensure_ascii=False),int(time.time())))
        return s,0

def save(uid,state,version):
    with db() as c:
        result=c.execute('UPDATE games SET state=?,version=version+1,updated=? WHERE user_id=? AND version=?',(json.dumps(state,ensure_ascii=False),int(time.time()),uid,version))
        if result.rowcount!=1:raise HTTPException(409,'동시에 다른 요청으로 저장이 변경되었습니다. 새로고침하세요.')

def power(s):
    a=s['stats'];
    if not a:return None
    avg=lambda keys:sum(float(a.get(k,0)) for k in keys)/len(keys)
    base=avg(STAT_KEYS[:8])*.5+avg(STAT_KEYS[8:12])*.35+avg(STAT_KEYS[12:])*.15
    condition=max(.2,s['hp']/max(1,s['max_hp']))*(1-min(90,s['fatigue'])/200)
    return max(1,round(base*condition*(1.08 if any('패기' in x for x in s['skills']) else 1)))

def view(s):return {**s,'power':power(s),'canon_events':[{**e,'access':'근처에서 관련 정보를 얻거나 현장에 도착해야 개입 가능' if s['location']!=e['location'] else '현장 조사 가능'} for e in CANON if e['day']<=s['day']+3]}

class Credentials(BaseModel):username:str=Field(min_length=3,max_length=24,pattern=r'^[a-zA-Z0-9_]+$');password:str=Field(min_length=8,max_length=128)
@app.post('/api/register')
def register(data:Credentials,response:Response):
    salt=secrets.token_hex(16)
    try:
        with db() as c:
            cur=c.execute('INSERT INTO users(username,salt,password_hash,created) VALUES(?,?,?,?)',(data.username,salt,hashpass(data.password,salt),int(time.time())))
            uid=cur.lastrowid
    except sqlite3.IntegrityError:raise HTTPException(409,'이미 사용 중인 아이디입니다.')
    return login_session(uid,response)

def login_session(uid,response):
    tok=secrets.token_urlsafe(32)
    with db() as c:c.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(tok.encode()).hexdigest(),uid,int(time.time())+86400*14))
    response.set_cookie('opl_session',tok,httponly=True,secure=COOKIE_SECURE,samesite='lax',max_age=86400*14)
    return {'ok':True}
@app.post('/api/login')
def login(data:Credentials,response:Response):
    with db() as c:r=c.execute('SELECT id,salt,password_hash FROM users WHERE username=?',(data.username,)).fetchone()
    if not r or not hmac.compare_digest(hashpass(data.password,r['salt']),r['password_hash']):raise HTTPException(401,'아이디 또는 비밀번호를 확인하세요.')
    return login_session(r['id'],response)
@app.post('/api/logout')
def logout(req:Request,response:Response):
    tok=req.cookies.get('opl_session','')
    with db() as c:c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(tok.encode()).hexdigest(),))
    response.delete_cookie('opl_session');return {'ok':True}
@app.get('/api/me')
def me(req:Request):
    uid=auth(req);s,v=load(uid);return {'state':view(s),'version':v,'ai_ready':bool(AI_TOKEN)}

class Setup(BaseModel):value:str=Field(min_length=1,max_length=100)
@app.post('/api/setup')
def setup(data:Setup,req:Request):
    uid=auth(req);s,v=load(uid);x=data.value.strip();p=s['phase']
    if p=='race':
        if x not in RACES:raise HTTPException(400,'종족을 선택하세요.')
        s['race']=x;s['phase']='faction'
    elif p=='faction':
        if x not in FACTIONS or (s['race']=='루나리아족' and x=='세계정부'):raise HTTPException(400,'선택할 수 없는 진영입니다.')
        s['faction']=x;s['phase']='path'
    elif p=='path':
        if x not in PATHS[s['faction']]:raise HTTPException(400,'경로를 선택하세요.')
        s['path']=x;s['phase']='questions'
    elif p=='questions':
        if len(s['answers'])>=5:raise HTTPException(400,'이름을 입력하세요.')
        if len(x)>90:raise HTTPException(400,'응답이 너무 깁니다.')
        s['answers'].append(x)
        if len(s['answers'])==5:s['phase']='name'
    elif p=='name':
        if len(x)>32:raise HTTPException(400,'이름은 32자 이하입니다.')
        s['name']=x;s['phase']='game'
        s['stats']={k:random.randint(12,24) for k in STAT_KEYS}
        if s['race']=='어인족':s['stats']['근력']*=10
        if s['faction']=='세계정부' and s['path']=='CP5 요원':s['skills']=random.sample(['체','월보','지회','철괴','람각','지건'],2)
        if s['faction'] in ('해적','혁명군'):s['bounty']=random.randint(1,5)*10000
        s['berries']=1000000000000 if s['path']=='천룡인' else 5000
        s['location']='이스트 블루 · 항구';s['last_scene']=f'해원력 1539년, 루피 출항 당일. {x}의 여정이 시작된다.'
    else:raise HTTPException(400,'이미 생성이 완료되었습니다.')
    save(uid,s,v);return {'state':view(s)}

class Level(BaseModel):stats:list[str]
@app.post('/api/level')
def level(data:Level,req:Request):
    uid=auth(req);s,v=load(uid)
    if s['level_pending']<=0:raise HTTPException(400,'레벨업 대기 중이 아닙니다.')
    if len(data.stats)!=5 or len(set(data.stats))!=5 or any(k not in STAT_KEYS for k in data.stats):raise HTTPException(400,'서로 다른 능력치 5개를 선택하세요.')
    for k in data.stats:s['stats'][k]+=1
    s['level']+=1;s['level_pending']-=1
    save(uid,s,v);return {'state':view(s)}

def ai_chat(messages):
    if not AI_TOKEN:raise HTTPException(503,'OPENAI_API_KEY가 설정되지 않았습니다. Render 환경 변수에 등록하세요.')
    url=AI_URL+'/chat/completions'
    payload={'model':AI_MODEL,'messages':messages,'temperature':0.72,'max_tokens':1100,'response_format':{'type':'json_object'}}
    headers={'Content-Type':'application/json','Authorization':'Bearer '+AI_TOKEN}
    try:
        req=urllib.request.Request(url,json.dumps(payload).encode(),headers=headers,method='POST')
        with urllib.request.urlopen(req,timeout=110) as r:data=json.load(r)
        raw=data['choices'][0]['message']['content'];raw=re.sub(r'^```(?:json)?|```$','',raw.strip(),flags=re.M).strip()
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        if e.code==401: raise HTTPException(502,'OpenAI API 인증에 실패했습니다. Render의 OPENAI_API_KEY를 확인하세요.')
        if e.code==429: raise HTTPException(503,'OpenAI API 요청 한도 또는 결제 한도에 도달했습니다.')
        raise HTTPException(502,f'OpenAI API 응답 오류 (HTTP {e.code}). Render 로그를 확인하세요.')
    except Exception:raise HTTPException(502,'AI GM 연결에 실패했습니다. 잠시 후 다시 시도하세요.')

class Turn(BaseModel):action:str=Field(min_length=1,max_length=1400)
@app.post('/api/turn')
def turn(data:Turn,req:Request):
    uid=auth(req);s,v=load(uid)
    if s['phase']!='game':raise HTTPException(400,'캐릭터 생성을 먼저 완료하세요.')
    if s['level_pending']:raise HTTPException(400,'레벨업 능력치 배분을 먼저 완료하세요.')
    action=data.action.strip();p=power(s) or 0
    recent=[]
    with db() as c:
        recent=[{'role':r['role'],'content':r['content']} for r in reversed(c.execute('SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 12',(uid,)).fetchall())]
    prompt='''당신은 ONE PIECE LIFE의 한국어 AI GM입니다. 플레이어의 의도를 해석하고 장면과 NPC 대화를 자연스럽게 진행합니다. 원작 설정과 게임용 추정, 역사 분기를 구분합니다. 플레이어의 행동이 자동 성공하지 않습니다. 원작 인물은 실제 위치·시간·인과관계를 따릅니다. 임의로 장거리 순간 이동, 큰 자금 획득, 원작 인물 등장, 원작 역사를 변경하지 마세요. 게임 엔진이 최종 상태를 검증합니다.
반드시 JSON 객체만 출력: {"narrative":"한국어로 2~5문단, 장면과 대사 포함", "outcome":"success|partial|failure", "effects":{"minutes":0,"xp":0,"hp":0,"fatigue":0,"berries":0}, "npc_actions":[{"name":"이름","action":"행동"}], "quest":{"title":"제목","description":"설명"}, "branch":{"event_id":"luffy_departure 등","description":"변경 사유"}}.
NPC 행동은 이미 등장했거나 상황에 맞게 새로 등장한 인물만. quest/branch는 해당하지 않으면 null. JSON 이외 출력 금지.
규칙 발췌:\n'''+RULE_CONTEXT
    state={'name':s['name'],'race':s['race'],'faction':s['faction'],'path':s['path'],'answers':s['answers'],'level':s['level'],'power':p,'hp':s['hp'],'fatigue':s['fatigue'],'berries':s['berries'],'bounty':s['bounty'],'day':s['day'],'minute':s['minute'],'location':s['location'],'crew':s['crew'],'npc_memory':s['npc_memory'][-8:],'quests':s['quests'][-8:],'branches':s['branches'][-8:],'last_scene':s['last_scene'],'canon_reference':CANON}
    messages=[{'role':'system','content':prompt},{'role':'system','content':'검증된 게임 상태: '+json.dumps(state,ensure_ascii=False)}]+recent+[{'role':'user','content':action}]
    out=ai_chat(messages)
    narrative=str(out.get('narrative','')).strip()[:5500]
    if not narrative:raise HTTPException(502,'AI가 장면을 생성하지 못했습니다.')
    outcome=out.get('outcome','partial')
    if outcome not in ('success','partial','failure'):outcome='partial'
    effects=out.get('effects') if isinstance(out.get('effects'),dict) else {}
    def clamp(k,lo,hi):
        try:return max(lo,min(hi,int(effects.get(k,0))))
        except:return 0
    # AI may suggest changes, but deterministic engine caps all numerical effects.
    minutes=clamp('minutes',1,180);xp=clamp('xp',0,90);hp=clamp('hp',-35,20);fatigue=clamp('fatigue',-20,30);berries=clamp('berries',-300,500)
    s['minute']+=minutes;s['day']+=s['minute']//1440;s['minute']%=1440
    s['hp']=max(0,min(s['max_hp'],s['hp']+hp));s['fatigue']=max(0,min(100,s['fatigue']+fatigue));s['berries']=max(0,s['berries']+berries)
    s['xp']+=xp
    while s['level']+s['level_pending']<1000 and s['xp']>=100*(s['level']+s['level_pending']):
        s['xp']-=100*(s['level']+s['level_pending']);s['level_pending']+=1
    npc=out.get('npc_actions') if isinstance(out.get('npc_actions'),list) else []
    for n in npc[:3]:
        if isinstance(n,dict):s['npc_memory'].append({'day':s['day'],'name':str(n.get('name','NPC'))[:50],'action':str(n.get('action',''))[:180]})
    s['npc_memory']=s['npc_memory'][-60:]
    q=out.get('quest')
    if isinstance(q,dict) and q.get('title'):s['quests'].append({'title':str(q['title'])[:90],'description':str(q.get('description',''))[:300],'status':'제안됨','day':s['day']})
    b=out.get('branch')
    # A branch requires a matching event and same location; never silently rewrite canon.
    if isinstance(b,dict) and b.get('event_id'):
        event=next((e for e in CANON if e['id']==b['event_id']),None)
        if event and event['location'] in s['location'] and s['day']>=event['day']:
            s['branches'].append({'event_id':event['id'],'description':str(b.get('description',''))[:350],'day':s['day'],'status':'gameplay_branch'})
    s['quests']=s['quests'][-80:];s['branches']=s['branches'][-80:]
    s['turn']+=1;s['last_scene']=narrative[-2000:];s['timeline'].append({'day':s['day'],'action':action[:200],'outcome':outcome,'effects':{'xp':xp,'hp':hp,'berries':berries,'minutes':minutes}});s['timeline']=s['timeline'][-150:]
    save(uid,s,v)
    with db() as c:
        c.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(uid,'user',action,int(time.time())))
        c.execute('INSERT INTO messages(user_id,role,content,created) VALUES(?,?,?,?)',(uid,'assistant',narrative,int(time.time())))
    return {'narrative':narrative,'outcome':outcome,'effects':{'minutes':minutes,'xp':xp,'hp':hp,'fatigue':fatigue,'berries':berries},'state':view(s)}

@app.get('/api/history')
def history(req:Request):
    uid=auth(req)
    with db() as c:return {'messages':[{'role':r['role'],'content':r['content']} for r in c.execute('SELECT role,content FROM messages WHERE user_id=? ORDER BY id DESC LIMIT 80',(uid,)).fetchall()][::-1]}
@app.get('/api/export')
def export(req:Request):
    uid=auth(req);s,_=load(uid)
    return {'format':'one-piece-life-save-v1','state':s}
@app.get('/api/health')
def health():return {'ok':True,'ai_configured':bool(AI_TOKEN)}
@app.get('/')
def index():return FileResponse(ROOT/'static/index.html')
