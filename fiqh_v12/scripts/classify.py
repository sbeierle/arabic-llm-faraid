import re,json
D=re.compile(r"[ً-ٰٟـ]")
def n(s): return re.sub(r"\s+"," ",re.sub("[أإآٱ]","ا",D.sub("",str(s or "")).replace("ى","ي"))).strip().lower()
def has(t,*ks): return any(k in t for k in ks)
def cls(q,txt):
    t=n(txt)
    if t in ("","none","null"): return "N"
    if re.search("[a-z]{4}",t) and q=="FIQH_005": return "?"
    if q=="FIQH_001":
        if has(t,"شهو") and has(t,"اذا","بشهو","ان كان","مع"): return "COND"
        if has(t,"لا ينقض","لا يبطل","does not","not invalid","no")and not has(t,"يستحب") or t in ("لا","no"): 
            if has(t,"لا ينقض","لا يبطل","does not","not invalid") or t in("لا","no"): return "NOT"
        if has(t,"شهو","لذه","بلا شهوه"): return "COND"
        if has(t,"ينقض","نعم","yes","invalidat","يبطل"): return "INV"
        return "?"
    if q=="FIQH_002":
        if t.startswith("سنه") or has(t,"ليس فرض","ليس بفرض","لا فرض","ليس واجب"): return "SUNNA"
        if has(t,"فرض","واجب","ركن","شرط"): return "FARD"
        if has(t,"سنه","مستحب"): return "SUNNA"
        return "?"
    if q=="FIQH_003":
        if has(t,"مكروه","makruh"): return "MAKRUH"
        if has(t,"لا يجوز","لا يحل","غير مباح","غير حلال","حرام","haram","محرم") and not has(t,"ليس بحرام","لا يحرم"): return "HARAM"
        if has(t,"مباح","حلال","جايز","جائز","halal","permiss","يجوز","يحل","allowed"): return "HALAL"
        return "?"
    if q=="FIQH_004":
        if has(t,"مكروه"): return "MAKRUH"
        if has(t,"حرام","haram","محرم","لا يجوز","لا يحل"): return "HARAM"
        if has(t,"مباح","حلال","halal","جائز","يجوز","permiss"): return "HALAL"
        return "?"
    if q=="FIQH_005":
        sirr=has(t,"سرا","سر ","الاسرار","اسرار","السر","يسر","silent","خفيه","خفض")
        jahr=has(t,"جهر","تجهر","يجهر","aloud","loud")
        nojahr=has(t,"لا يجهر","لا تجهر","ولا تجهر","لا ينبغي الجهر","لا جهر")
        noread=has(t,"لا تقرا","لا يقرا","لا تقرا","تترك","لا تشرع","مكروه","لا يقرا")
        perm=has(t,"لا مانع","لا باس","لا حرج","جايز","جائز","يجوز")
        if noread and not has(t,"سرا"): return "NOREAD"
        if sirr and (perm or (jahr and not nojahr)): return "BOTH"
        if sirr and not (jahr and not nojahr): return "SIRR"
        if jahr and not nojahr: return "JAHR"
        if nojahr: return "SIRR"
        return "?"
    if q=="FIQH_006":
        if has(t,"لا يصح","باطل","بطل","غير صحيح","لا ينعقد","يفسخ","لا يجوز","invalid","not valid") or t in ("لا","no"): return "INVALID"
        if has(t,"يصح","صحيح","جائز","يجوز","valid","ينعقد"): return "VALID"
        return "?"
    if q=="FIQH_007":
        if t in ("لا","no") or has(t,"لا يثبت","لا خيار","غير ثابت","لا يعترف"): return "NOT"
        if has(t,"yes","نعم","يثبت","ثابت","له الخيار","لكل","يوجد","موجود","مشروع"): return "RECOG"
        return "?"
    if q=="FIQH_008":
        if has(t,"واجب","فرض","عزيمه","تجب","يجب"): return "WAJIB"
        if has(t,"سنه","رخصه","مستحب","جائز","يجوز","مندوب","mubah"): return "SUNNA"
        return "?"
    if q=="FIQH_009":
        if has(t,"طاهر شعره","شعره طاهر","طهاره","طاهر","طهور","pure"): 
            if has(t,"نجس") and not has(t,"شعره"): return "?"
            return "TAHIR"
        if has(t,"نجس","najis","impure","unclean"): return "NAJIS"
        return "?"
    if q=="FIQH_010":
        if has(t,"السريه","السرية","سريه") and has(t,"جهر","ينصت","انصات","استماع","سكت"): return "?"
        if has(t,"لا تجب","لا يجب","لا تجبر","لا تجبي","ليس بواجب","لا تلزم","يستحب","لا يقرا","لا تشرع","not oblig"): return "NOT"
        if has(t,"السريه","السرية") : return "?"
        if has(t,"تجب","يجب","واجب","وجوب","oblig"): return "WAJIB"
        return "?"
    return "?"
# Gold-Label pro (Frage,Stimme): Menge akzeptierter Labels (R), teilweise (P)
GL={
("FIQH_001","hanafi"):({"NOT"},set()),("FIQH_001","maliki"):({"COND"},{"INV"}),("FIQH_001","shafii"):({"INV"},set()),("FIQH_001","hanbali"):({"INV","COND"},set()),
("FIQH_001","ibn_baz"):({"NOT"},set()),("FIQH_001","ibn_uthaymin"):({"NOT"},set()),
("FIQH_002","hanafi"):({"SUNNA"},set()),("FIQH_002","maliki"):({"SUNNA"},set()),("FIQH_002","shafii"):({"FARD"},set()),("FIQH_002","hanbali"):({"FARD"},set()),("FIQH_002","ibn_baz"):({"FARD"},set()),
("FIQH_003","maliki"):({"HALAL"},set()),("FIQH_003","shafii"):({"HALAL"},set()),("FIQH_003","ibn_baz"):({"HALAL"},set()),("FIQH_003","ibn_uthaymin"):({"HALAL"},set()),
("FIQH_004","hanafi"):({"MAKRUH"},{"HALAL"}),("FIQH_004","maliki"):({"HARAM","MAKRUH"},set()),("FIQH_004","shafii"):({"HALAL"},set()),("FIQH_004","hanbali"):({"HALAL"},set()),("FIQH_004","ibn_baz"):({"HALAL"},set()),
("FIQH_005","hanafi"):({"SIRR"},set()),("FIQH_005","maliki"):({"NOREAD","SIRR"},set()),("FIQH_005","shafii"):({"JAHR","BOTH"},set()),("FIQH_005","hanbali"):({"SIRR"},set()),
("FIQH_005","ibn_baz"):({"BOTH","SIRR"},set()),("FIQH_005","ibn_uthaymin"):({"BOTH","SIRR"},set()),
("FIQH_006","hanafi"):({"VALID"},set()),("FIQH_006","maliki"):({"INVALID"},set()),("FIQH_006","shafii"):({"INVALID"},set()),("FIQH_006","hanbali"):({"INVALID"},set()),
("FIQH_006","ibn_baz"):({"INVALID"},set()),("FIQH_006","ibn_uthaymin"):({"INVALID"},set()),
("FIQH_007","hanafi"):({"NOT"},set()),("FIQH_007","maliki"):({"NOT"},set()),("FIQH_007","shafii"):({"RECOG"},set()),("FIQH_007","hanbali"):({"RECOG"},set()),("FIQH_007","ibn_baz"):({"RECOG"},set()),
("FIQH_008","hanafi"):({"WAJIB"},set()),("FIQH_008","maliki"):({"SUNNA"},set()),("FIQH_008","shafii"):({"SUNNA"},set()),("FIQH_008","hanbali"):({"SUNNA"},set()),("FIQH_008","ibn_uthaymin"):({"SUNNA"},set()),
("FIQH_009","hanafi"):({"TAHIR"},set()),("FIQH_009","maliki"):({"TAHIR"},set()),("FIQH_009","shafii"):({"NAJIS"},set()),("FIQH_009","hanbali"):({"NAJIS"},set()),("FIQH_009","ibn_baz"):({"NAJIS"},set()),("FIQH_009","ibn_uthaymin"):({"NAJIS"},set()),
("FIQH_010","hanafi"):({"NOT"},set()),("FIQH_010","maliki"):({"NOT"},set()),("FIQH_010","shafii"):({"WAJIB"},set()),("FIQH_010","hanbali"):({"NOT"},set()),("FIQH_010","ibn_baz"):({"WAJIB"},set()),("FIQH_010","ibn_uthaymin"):({"WAJIB"},set()),
}
def verdict(q,v,txt):
    if (q,v) not in GL: return None
    c=cls(q,txt)
    if c=="N": return "N"
    if c=="?": return "?"
    R,P=GL[(q,v)]
    return "R" if c in R else ("P" if c in P else "F")
