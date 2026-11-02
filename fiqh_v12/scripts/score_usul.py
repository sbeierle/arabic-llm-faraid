import json,sys,collections,re
sys.path.insert(0,"."); from classify import n
K={ # Kriterium = Liste von Schlagwortgruppen; Tupel = alle muessen vorkommen
"USUL_001":[["لتركبوها","للركوب","امتن","ليس للتحريم","لا يدل","لم يرد بذلك"],["مكي"],["خيبر"]],
"USUL_002":[["اضاف","نسب","فعلن في انفسهن","حتي تنكح","استقلال"],["تصرفها في مالها","كتصرفها","مالها"],["امه","المقيد","حمل المطلق"],["الزهري","انكر الخبر","لم يعرفه"]],
"USUL_003":[["اعظم منفعت","اعظم ما يبتغي","منفعته"],[("ابو حنيفه","الخرز"),("محمد","الخرز"),("ابي حنيفه","للخرز")],["استحسان","اقرار","النكير","اساكف","الحمام","الاستصناع","سكوت"],["حياه","شعر الميته","لم يكن فيه حياه"]],
"USUL_004":[["شمول الاسم","شموله","شمول"],["خلقه","لا فرق"],["يخطيهم","لم يخطي","في التسميه","حقيقه"]],
"USUL_005":[["عطف","المعطوف"],["حاشيتان","متساويتان","شفع","الاربع","الست"],["اقل جمع","الخمس","اثنان","اثنين"],["واجب","لا يقول بفرضيه الوتر","الفرق بين الواجب"]],
"USUL_006":[["لم يكتب","معاويه","لم يجب قط","لم يفرض قبل"],["نسخ","الحنفيه","اول ما فرض","بلفظ الامر","ابن عمر","عائشه"],["نيه من الليل","النيه","من الليل"]],
"USUL_007":[["روايه واحده","متعه","موسم","القاضي"],["روايتان","روايتين","ابن عقيل","مجد","جدي"],["حمل المطلق","مقيده","مجمله","مفسره","ابو بكر","ابو محمد","ابن قدامه"]],
}
def txt(p):
    if not isinstance(p,dict): return ""
    out=[]
    for v in p.values():
        out.append(" ".join(map(str,v)) if isinstance(v,list) else str(v))
    return n(" ".join(out))
def hit(t,groups):
    for g in groups:
        if isinstance(g,tuple):
            if all(n(x) in t for x in g): return True
        elif n(g) in t: return True
    return False
res=collections.defaultdict(lambda:[0,0,0,0])  # hits, crit, valid, calls
for model in ("jais","qwen"):
    R=json.load(open(f"fiqh_v12_results_{model}.json",encoding="utf-8"))
    for x in R:
        if x["suite"]!="USUL": continue
        a=res[(model,x["mode"])]; a[3]+=1
        if x.get("finish")!="stop" or not x.get("parsed"): continue
        t=txt(x["parsed"]); cr=K[x["usul_id"]]
        a[0]+=sum(hit(t,[g] if not isinstance(g,list) else g) for g in cr) if False else sum(hit(t,g) for g in cr); a[1]+=len(cr); a[2]+=1
print("Schlagwort-Treffer je Kriterium (grobe Naeherung, keine inhaltliche Bewertung)")
for (m,mo),a in sorted(res.items()): print(f" {m:5} {mo:12} Kriterien-Treffer {a[0]}/{a[1]} ({100*a[0]/a[1]:.0f}%) | gueltige Antworten {a[2]}/{a[3]}")
# je Fall
per=collections.defaultdict(lambda:[0,0])
for model in ("jais","qwen"):
    R=json.load(open(f"fiqh_v12_results_{model}.json",encoding="utf-8"))
    for x in R:
        if x["suite"]!="USUL" or x.get("finish")!="stop" or not x.get("parsed"): continue
        t=txt(x["parsed"]); cr=K[x["usul_id"]]; p=per[(x["usul_id"],model,x["mode"])]
        p[0]+=sum(hit(t,g) for g in cr); p[1]+=len(cr)
print("\nFall | Jais zu/offen | Qwen zu/offen")
for u in sorted(K):
    f=lambda m,mo:"%d%%"%(100*per[(u,m,mo)][0]/per[(u,m,mo)][1]) if per[(u,m,mo)][1] else "-"
    print(u,"|",f("jais","CLOSED_BOOK"),"/",f("jais","OPEN_BOOK"),"|",f("qwen","CLOSED_BOOK"),"/",f("qwen","OPEN_BOOK"))
