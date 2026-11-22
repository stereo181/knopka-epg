"""Knopka EPG: большие XMLTV -> маленькие JSON по каналам (для телевизоров LG/Samsung и MSX).

Вход: один или несколько XMLTV (.xml / .xml.gz), по ссылке или файлу. Первый — главный (его id совпадают
с tvg-id плейлистов вида iptvx.one); у следующих id, уже занятые предыдущими, получают приставку «<n>~».
Источник с «=» впереди (=ссылка) — с теми же id, что у главного (например, программа провайдера на базе iptvx):
его каналы не получают приставку, а заменяют канал главного, если программа у них полнее.
Метка источника: «метка@ссылка» (например, uk@https://…) — на неё ссылается aliases.txt.
--aliases файл: свои соответствия «id:<tvg-id> = метка:<id>» (копия программы под tvg-id плейлиста)
и «name:<название> = метка:<id>» (лишнее название в index.json) — для каналов, которые в источниках названы иначе.
Выход (папка out/):
  index.json           — {"at": unix, "ch": [[название, id], ...]}  (только каналы, у которых есть программа;
                         каналы с описаниями идут раньше — при одинаковом названии приложение берёт первый)
  epg/<id>.json        — {"epg_data": [{"name", "time", "time_to", "descr"?, "img"?}, ...]}  (формат epg.ott-play.com)
Окно: 2 дня назад … 4 дня вперёд. Описание: жанр · текст, до 400 знаков.
"""
import gzip, json, os, re, shutil, sys, tempfile, time, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

BACK, FWD = 2 * 86400, 4 * 86400 + 6 * 3600   # приложение держит 4 дня вперёд; +6 ч — до следующей сборки

def open_src(src):
    """Поток XML. Ссылку сначала скачиваем во временный файл: распакованный XMLTV в память не кладём."""
    path = src
    if re.match(r'https?://', src):
        req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0 (KnopkaEPG)'})
        fd, path = tempfile.mkstemp(suffix='.xmltv')
        with os.fdopen(fd, 'wb') as f, urllib.request.urlopen(req, timeout=600) as r:
            shutil.copyfileobj(r, f, 1 << 20)
    f = open(path, 'rb')
    gz = f.read(2) == b'\x1f\x8b'
    f.seek(0)
    return gzip.GzipFile(fileobj=f) if gz else f

def ts(s):
    s = s.strip()
    m = re.match(r'(\d{14})\s*([+-]\d{4})?', s)
    if not m:
        return None
    dt = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2) or '+0000'
    sign = 1 if off[0] == '+' else -1
    secs = sign * (int(off[1:3]) * 3600 + int(off[3:5]) * 60)
    return int((dt - datetime(1970, 1, 1)).total_seconds()) - secs

def safe(id_):
    # имя файла: id как есть, только без / \ и управляющих символов
    return re.sub(r'[\\/\x00-\x1f?#%]', '_', id_)

def main(out, srcs, aliases=None):
    now = int(time.time())
    names, progs, owner = {}, {}, {}   # owner: id -> номер источника
    icons = {}   # id -> логотип канала из источника (<icon> у <channel>): у плейлистов без tvg-logo (TapTV) значки берутся отсюда
    byTag = {}   # метка -> {id в источнике: id в выдаче}
    alts = []   # каналы источников «=»: [{id: {start: row}}]
    for si, src in enumerate(srcs):
        mine = {}   # id в этом источнике -> id в выдаче
        same = src.startswith('=')
        src = src.lstrip('=')
        m = re.match(r'^(\w+)@(.+)$', src)
        tag, src = (m.group(1), m.group(2)) if m else ('', src)
        alt = {}
        if tag:
            byTag[tag] = mine
        if same:
            alts.append(alt)
        def oid(cid):
            if same:
                mine[cid] = cid
                return cid
            if cid not in mine:
                mine[cid] = cid if owner.get(cid, si) == si else '%d~%s' % (si, cid)
                owner.setdefault(mine[cid], si)
            return mine[cid]
        try:
            stream = open_src(src)
            n0 = len(progs) + len(alt)
            for ev, el in ET.iterparse(stream, events=('end',)):
                if el.tag == 'channel':
                    cid = el.get('id')
                    if cid:
                        ic = el.find('icon')
                        if ic is not None and re.match(r'https?://', ic.get('src') or ''):
                            icons.setdefault(oid(cid), ic.get('src'))
                        lst = names.setdefault(oid(cid), [])
                        for dn in el.findall('display-name'):
                            if dn.text and dn.text.strip() not in lst:
                                lst.append(dn.text.strip())
                    el.clear()
                elif el.tag == 'programme':
                    cid, s, e = el.get('channel'), ts(el.get('start', '')), ts(el.get('stop', ''))
                    if cid and s and e and e > now - BACK and s < now + FWD:
                        t = el.findtext('title') or ''
                        d = (el.findtext('desc') or '').strip()
                        cat = [c.text.strip() for c in el.findall('category') if c.text and c.text.strip()]
                        t = re.sub(r'\s*┊\s*', ' · ', t.replace('⋗', '')).strip()   # служебные значки iptvx.one
                        row = {'name': t, 'time': s, 'time_to': e}
                        if cat and d and cat[0].lower() not in d[:80].lower():
                            d = ', '.join(cat[:2]) + ' · ' + d
                        if d:
                            row['descr'] = (d[:399] + "…" if len(d) > 400 else d)
                        ic = el.find('icon')
                        if ic is not None and re.match(r'https?://', ic.get('src') or ''):
                            row['img'] = ic.get('src')
                        rows = (alt if same else progs).setdefault(oid(cid), {})
                        if s not in rows:   # тот же старт из другого источника не дублируем
                            rows[s] = row
                    el.clear()
            print('source', si, re.sub(r'\?.*', '', src), 'channels +%d' % (len(progs) + len(alt) - n0))
        except Exception as ex:   # один источник упал — остальные всё равно выкладываем
            print('source', si, 'FAILED', ex)
    def score(rows):   # сколько из ближайших суток покрыто программой, затем — сколько передач с описанием
        cov = sum(max(0, min(r['time_to'], now + 86400) - max(r['time'], now)) for r in rows.values())
        return (min(cov, 86400) // 3600, sum(1 for r in rows.values() if 'descr' in r))
    for alt in alts:
        for cid, rows in alt.items():
            if cid not in progs or score(rows) > score(progs[cid]):
                progs[cid] = rows
                owner[cid] = 0
    if not progs:
        sys.exit('no programmes')
    extra, na = [], 0   # свои соответствия
    for line in open(aliases, encoding='utf-8') if aliases else []:
        m = re.match(r'^(id|name):(.+?)\s+=\s+(\w+):(.+)$', line.strip())
        if not m:
            continue
        kind, alias, tag, sid = m.groups()
        cid = byTag.get(tag, {}).get(sid)
        if not cid or cid not in progs or alias == cid:
            continue
        if kind == 'name':
            extra.append([alias, safe(cid)]); na += 1
        elif alias not in progs or score(progs[alias])[0] < score(progs[cid])[0]:
            progs[alias] = progs[cid]; names.setdefault(alias, []); owner[alias] = 0; na += 1
    print('aliases', na)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, 'epg'))
    chans, total, logos = [], 0, {}
    for cid, rows in progs.items():
        if re.match(r'(\d+~)?no_?epg', cid, re.I):
            continue   # заглушки «нет программы» (no_epg, no_epg_sport…): у сотен каналов одна и та же чужая программа
        lst = [rows[k] for k in sorted(rows)]
        fn = safe(cid)
        if cid in icons:
            logos[fn] = icons[cid]
        with open(os.path.join(out, 'epg', fn + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'epg_data': lst}, f, ensure_ascii=False, separators=(',', ':'))
        q = sum(1 for r in lst if 'descr' in r) / len(lst)
        chans.append((owner.get(cid, 0) > 0, -round(q, 1), fn, names.get(cid) or [cid]))
        total += len(lst)
    # при одинаковом названии побеждает первый в списке: у кого больше описаний, при равенстве — главный источник
    chans.sort(key=lambda c: (c[1], c[0]))
    index = extra + [[n, fn] for _, _, fn, ns in chans for n in ns]
    with open(os.path.join(out, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'at': now, 'ch': index}, f, ensure_ascii=False, separators=(',', ':'))
    with open(os.path.join(out, 'logos.json'), 'w', encoding='utf-8') as f:   # id -> логотип канала
        json.dump(logos, f, ensure_ascii=False, separators=(',', ':'))
    open(os.path.join(out, '.nojekyll'), 'w').close()
    print('channels', len(chans), 'programmes', total)

if __name__ == '__main__':
    a = sys.argv[1:]
    al = None
    if '--aliases' in a:
        i = a.index('--aliases'); al = a[i + 1]; del a[i:i + 2]
    main(a[0], a[1:], al)
