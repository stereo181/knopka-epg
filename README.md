# Knopka EPG

Телепрограмма для приложения Knopka на телевизорах LG, Samsung и в Media Station X.

Большой XMLTV-файл телевизору не по силам, поэтому GitHub каждые 6 часов раскладывает его на маленькие файлы по каналам:

- `index.json` — список каналов: `{"at": время, "ch": [[название, id], ...]}`
- `epg/<id>.json` — программа канала: `{"epg_data": [{"name", "time", "time_to", "descr"?}, ...]}` (формат как у epg.ott-play.com)

Окно: 3 дня назад и 7 дней вперёд. Адрес: https://stereo181.github.io/knopka-epg/

Источник: публичное зеркало [Lorax121/epg_v2](https://github.com/Lorax121/epg_v2) (iptvx.one), запасной — iptvx.one напрямую.
Собрать вручную: `python3 build.py out <xmltv.xml.gz>`
