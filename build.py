"""Knopka EPG: большой XMLTV -> маленькие JSON по каналам (для телевизоров LG/Samsung и MSX).

Вход: один или несколько XMLTV (.xml / .xml.gz), по ссылке или файлу.
Выход (папка out/):
  index.json           — {"src": "...", "at": unix, "ch": [[название, id], ...]}  (только каналы, у которых есть программа)
  epg/<id>.json        — {"epg_data": [{"name", "time", "time_to", "descr"?}, ...]}  (тот же формат, что у epg.ott-play.com)
Окно: 3 дня назад … 7 дней вперёд.
"""
import gzip, io, json, os, re, shutil, sys, time, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime

BACK, FWD = 3 * 86400, 7 * 86400

def open_src(src):
    if re.match(r'https?://', src):
        req = urllib.request.Request(src, headers={'User-Agent': 'Mozilla/5.0 (KnopkaEPG)'})
        data = urllib.request.urlopen(req, timeout=300).read()
    else:
        data = open(src, 'rb').read()
    if data[:2] == b'\x1f\x8b':
        data = gzip.decompress(data)
    return io.BytesIO(data)

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

def main(out, srcs):
    now = int(time.time())
    names, progs = {}, {}
    for src in srcs:
        for ev, el in ET.iterparse(open_src(src), events=('end',)):
            if el.tag == 'channel':
                cid = el.get('id')
                for dn in el.findall('display-name'):
                    if dn.text and cid:
                        names.setdefault(cid, [])
                        if dn.text.strip() not in names[cid]:
                            names[cid].append(dn.text.strip())
                el.clear()
            elif el.tag == 'programme':
                cid, s, e = el.get('channel'), ts(el.get('start', '')), ts(el.get('stop', ''))
                if cid and s and e and e > now - BACK and s < now + FWD:
                    t = el.findtext('title') or ''
                    d = el.findtext('desc') or ''
                    t = re.sub(r'\s*┊\s*', ' · ', t.replace('⋗', '')).strip()   # служебные значки iptvx.one
                    row = {'name': t, 'time': s, 'time_to': e}
                    if d.strip():
                        row['descr'] = d.strip()[:600]
                    progs.setdefault(cid, {})[s] = row   # тот же старт из второго источника не дублируем
                el.clear()
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, 'epg'))
    index, total = [], 0
    for cid, rows in progs.items():
        if re.match(r'no_?epg', cid, re.I):
            continue   # заглушки «нет программы» (no_epg, no_epg_sport…): у сотен каналов одна и та же чужая программа
        lst = [rows[k] for k in sorted(rows)]
        fn = safe(cid)
        with open(os.path.join(out, 'epg', fn + '.json'), 'w', encoding='utf-8') as f:
            json.dump({'epg_data': lst}, f, ensure_ascii=False, separators=(',', ':'))
        for n in names.get(cid, [cid]):
            index.append([n, fn])
        total += len(lst)
    with open(os.path.join(out, 'index.json'), 'w', encoding='utf-8') as f:
        json.dump({'at': now, 'ch': index}, f, ensure_ascii=False, separators=(',', ':'))
    open(os.path.join(out, '.nojekyll'), 'w').close()
    print('channels', len(progs), 'programmes', total)

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2:])
