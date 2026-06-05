# WAL Contest Logger

Mažas savarankiškas loggeris Lietuvos mobiliųjų-portabiliųjų RS čempionatui (WAL).
Veikia offline ant Windows laptopo. Telefonas (Android) duoda GPS -> Sent WAL kvadratą.

## Diegimas (Windows)

Reikia tik Python 3. Trys žingsniai:

1. **Python** (jei dar nėra): https://www.python.org/downloads/ - diegiant pažymėk **"Add Python to PATH"**
   (arba `winget install Python.Python.3.12`). Patikra: `python --version`.
2. **Parsisiųsk projektą** - vienas iš:
   - `git clone https://github.com/LY5AT/wal-logger.git`  (ar `gh repo clone LY5AT/wal-logger`), arba
   - GitHub puslapyje **Code -> Download ZIP** -> išarchyvuok.
3. Aplanke dukart spustelėk **`install.bat`** (įdiegs `cryptography`).

Tada paleisk **`Start WAL Logger.bat`**. (Jei 3 žingsnį praleidai - pirmą kartą jis priklausomybes įdiegs pats.)

## Paleidimas

Dukart spustelėk **`Start WAL Logger.bat`** (arba `python wal_logger.py`).
Atsidaro naršyklė: **http://localhost:8782**

Konsolėje pamatysi ir telefono GPS adresą, pvz.:
```
Phone GPS :  https://192.168.x.x:8443/gps
```

## Telefono GPS (Android)

1. Įjunk telefono **hotspot**, prie jo prijunk laptopą (kad būtų tame pačiame tinkle).
2. Telefone (Chrome) atidaryk laptopo konsolėje parodytą adresą `https://192.168.x.x:8443/gps`.
3. Bus įspėjimas dėl sertifikato (self-signed) -> *Advanced -> Proceed*.
4. Paspausk **Įjungti GPS**, leisk vietos prieigą.
5. Telefonas rodo tavo WAL kvadratą ir siunčia jį į loggerį. Laptope **SENT WAL** atsinaujina automatiškai.

Kiekvienoje naujoje vietoje (kvadrate) tiesiog pažiūrėk į telefoną - SENT WAL pasikeičia pats.
Jei GPS nenaudoji, SENT WAL lauką laptope gali įvesti ranka.

**Kad telefonas nenustotų siųsti:** puslapis laiko ekraną įjungtą (wake lock) ir siunčia poziciją
kas 5 s, net kai stovi vietoje. Jei užrakinai telefoną - atrakinus siuntimas atsinaujina automatiškai.
Laptope prie „GPS" matomas amžius sekundėmis: žalia = šviežia, geltona/raudona = telefonas nustojo
siųsti (atrakink / patapšnok ekraną). Telefono puslapyje mirksintis taškas = gyvas, siunčia.

## Logginimas

- Modą (SSB/CW) ir kHz nustatai **viršuje** (header) - jie galioja visiems naujiems QSO.
- Įvedimo zonoje tik: **Call** -> (`Tab`) -> **Rcv WAL** (pvz. `A18`; užsienis = `DX`) -> **Enter**.
- **`Tab` po Call** peršoka tiesiai prie WAL lauko. Jei tą stotį jau darei - WAL užsipildo iš praeito ryšio (gali pertaisyti).
- RST užsipildo pagal modą (59 / 599).
- Dublis ar negaliojantis kvadratas - parodomas įspėjimas (logginti vis tiek galima, `Alt`+Enter).
- Taškai automatiškai: /m = 5, /p = 3, kita = 1.
- Žemėlapyje skverai sudėlioti pagal tikrą padėtį (Lietuvos forma); viršuje stulpelių numeriai, kairėje eilučių raidės. Žali = padaryti.

## Papūga (voice keyer)

F1/F2/F3 mygtukai (arba klaviatūros `F1`/`F2`/`F3`) groja iš anksto įrašytą garsą - pvz. `CQ CQ LY5AT/M`.
- **⏺** - įrašyti iš laptopo mikrofono (paspaudi - kalbi - paspaudi dar kartą sustabdyti).
- **📁** - įkelti paruoštą `.wav` (ar kitą garso) failą.
- Pavadinimą (CQ / Rpt / TU) gali pakeisti laukelyje.
- **Stop** arba `Esc` - nutraukti grojimą.
- Garsas eina į laptopo garso išvestį -> į transiverį (per garso sąsają / VOX). Įrašai išlieka (`macro_*.*`).

## Turai (sessions)

Varžybos = trys 1 val. turai pagal UTC: **06:00-06:59 (T1), 07:00-07:59 (T2), 08:00-08:59 (T3)**.
Turas nustatomas automatiškai pagal QSO laiką; viršuje matosi dabartinis turas ir likęs laikas.
Dublio tikrinimas - **per turą**, t.y. tą pačią stotį gali daryti iš naujo kiekviename ture.

## Žurnalo redagavimas

- **✎** eilutėje - redaguoti QSO (call, modas, sent/rcv WAL, RST); taškai persiskaičiuoja.
- **✕** - ištrinti.
- Viskas išsaugoma iškart (SQLite), redagavimas irgi.

## Nustatymai (prieš startą)

Header'yje užpildyk: **Mano** (šaukinys, pvz. `LY5AT/M`), **Vardas**, **Kat.** (M/P/S/K/SWL/KL).
Šie laukai įrašomi į Cabrillo (CALLSIGN, NAME, kategorija).

## Ataskaita

- **⬇ Cabrillo** -> `<saukinys>_WAL.log` - šitą failą siųsk į **walcontest@lrmd.lt** (per 14 d.).
- **⬇ ADIF** -> bendram žurnalui.

Visi ryšiai saugomi `wal_log.sqlite` (autosave kiekvieną QSO). SENT WAL irgi išsaugomas -
jei programą perkrauni varžybų metu, kvadratas neprapuola.

**Apsauga nuo praradimo (3 sluoksniai):**
1. Kiekvienas QSO iškart įrašomas į `wal_log.sqlite` (SQLite, fsync). Serverio/laptopo mirtis ryšių nepraranda - patikrinta hard-kill testu.
2. Kiekvienas QSO dar pridedamas į `qso_journal.csv` - append-only juosta (fsync). Net jei SQLite failas dingtų/sugestų, visi ryšiai lieka šitam faile.
3. Automatinė pilna kopija į `backups/` kas 5 min (+ prieš kiekvieną „Naujas" valymą).

Atstatymas: tiesiog paleisk iš naujo (`Start WAL Logger.bat`) - viskas grįžta iš `wal_log.sqlite`.

## Naujas žurnalas / kopijos (testavimui)

- **💾 Kopija** - rankinė atsarginė kopija į `backups/`.
- **🗑 Naujas** - išvalo žurnalą (po patvirtinimo). PRIEŠ tai automatiškai padaro kopiją į `backups/`,
  tad nieko neprarandi. Papūgos įrašai ir nustatymai lieka. Patogu po testavimo prieš tikras varžybas.

## Score
Rodomas **apytikslis** rezultatas (taškai x daugiklis). Galutinį skaičiuoja organizatoriai iš Cabrillo.
Daugiklis = skirtingi gauti kvadratai + savi aktyvuoti kvadratai (/m) + DX šalys.
