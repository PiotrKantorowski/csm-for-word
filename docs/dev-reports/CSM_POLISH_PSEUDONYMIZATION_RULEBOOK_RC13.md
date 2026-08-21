# CSM — reguły pseudonimizacji dokumentów prawnych po polsku

Wersja robocza: `rc13`  
Cel: uzupełnić dotychczasowe reguły CSM, a nie zastąpić istniejące detektory.

## 1. Podstawa jakościowa

Pseudonimizacja w CSM ma być odwracalna dla uprawnionego użytkownika, ale dla odbiorcy dokumentu zanonimizowanego ma uniemożliwiać przypisanie treści do konkretnej osoby lub podmiotu bez dodatkowej mapy. Mapa przywracania jest „dodatkową informacją” i musi być przechowywana osobno oraz chroniona technicznie.

Źródła referencyjne:

- RODO art. 4 pkt 5: pseudonimizacja wymaga, aby danych nie można było przypisać osobie bez dodatkowych informacji, a te informacje mają być przechowywane osobno i zabezpieczone.
- RODO motyw 26: dane pseudonimizowane nadal mogą być danymi osoby możliwej do zidentyfikowania, jeżeli dodatkowe informacje pozwalają na identyfikację.
- RODO art. 32: pseudonimizacja i szyfrowanie są przykładowymi środkami bezpieczeństwa, a środki muszą być regularnie testowane i oceniane.
- ENISA: przy pseudonimizacji należy uwzględniać modele ataku, w tym brute force, dictionary search i guesswork.
- Microsoft Presidio: poprawny model rozdziela wykrywanie encji, operatory anonimizacji/pseudonimizacji i mechanizm deanonymizacji; trzeba świadomie obsługiwać nakładanie się encji.

## 2. Zasada nadrzędna CSM

CSM nie ma tworzyć „ładnego tekstu”, tylko bezpieczny dokument roboczy do dalszej pracy z AI. Dlatego:

1. Dane identyfikujące i quasi-identyfikatory mają być maskowane, nawet jeżeli fragment wygląda jak zwykłe słowo.
2. Elementy prawne, które nie identyfikują strony, należy zostawiać, aby dokument zachował sens: przepisy, paragrafy, jednostki redakcyjne, terminy procesowe, kwoty typowe dla żądania lub kapitału, opisy instytucji prawnych.
3. Jeżeli wynik jest niepewny, lepszy jest placeholder z ostrzeżeniem niż pozostawienie danych jawnych bez komunikatu.
4. Każda reguła musi mieć test pozytywny, test fałszywie pozytywny i test roundtrip.

## 3. Osoby fizyczne

Maskować jako `PERSON`:

- pełne imię i nazwisko we wszystkich przypadkach gramatycznych: `Jan Nowak`, `Jana Nowaka`, `Janowi Nowakowi`, `Annę Kowalską`, `Annie Kowalskiej`, `Iwony Teresy Ustrzyckiej`;
- osoby z tytułem lub rolą: `Pan`, `Pani`, `Pana`, `Panią`, `Panu`, `Mec.`, `adwokat`, `radca prawny`, `notariusz`, `komornik`, `biegły`, `świadek`, `pełnomocnik`, `prokurent`, `prezes`, `członek zarządu`;
- osoby w rolach procesowych: `powód`, `pozwany`, `wnioskodawca`, `uczestnik`, `oskarżony`, `pokrzywdzony`, `wierzyciel`, `dłużnik`, `spadkobierca`;
- osoby w konstrukcjach rodzinnych: `syn Jana i Marii`, `córka Piotra`, `matka dziecka`, `ojciec`, `małżonek`, `z domu`, `poprzednio`;
- wieloczłonowe imiona i nazwiska, w tym nazwiska dwuczłonowe: `Anna Maria Kowalska-Szulc`;
- nazwiska będące zwykłymi słowami, jeśli występują w kontekście osoby: `Jan Mucha`, `Renata Mucha`, `Piotr Pustynia`;
- samo nazwisko lub samo imię, jeżeli w dokumencie wcześniej wykryto jednoznaczną osobę i kontekst wskazuje, że chodzi o tę samą osobę.

Nie maskować jako osoby:

- tytułów dokumentów: `Ogólne Warunki`, `Kodeks Cywilny`, `Uchwała nr 1`;
- nazw organów lub instytucji publicznych, chyba że są elementem konkretnej sprawy do zamaskowania jako `COURT`/`PUBLIC_AUTHORITY`;
- nazw miejscowości poza kontekstem adresu, siedziby lub zamieszkania.

## 4. Nazwiska i miejscowości będące zwykłymi słowami

Słowa typu `Mucha`, `Pustynia`, `Góra`, `Lis`, `Wilk`, `Sokół`, `Baran`, `Kowal`, `Jagoda`, `Róża` mogą być nazwiskiem, imieniem, miejscowością albo zwykłym słowem. Reguła CSM:

- z imieniem lub tytułem osoby → `PERSON`;
- po `zamieszkały w`, `zam. w`, `według oświadczenia zamieszkały w` → `ADDRESS`;
- po `z siedzibą w`, `adres`, `siedziba` → `ADDRESS` albo część `COMPANY/CONTRACTOR`, zależnie od zasięgu;
- samotne słowo bez kontekstu → nie maskować automatycznie, ale oznaczyć w ostrzeżeniach, jeżeli jest zgodne z nazwiskiem/miejscowością z mapy.

## 5. Adresy i lokalizacje

Maskować:

- pełne adresy uliczne: `ul. Długa 5/7, 00-001 Warszawa`;
- adresy wiejskie: `Pustynia 84F, 39-200 Dębica`;
- miejsce zamieszkania bez ulicy: `zamieszkały w Pustyni`;
- siedzibę spółki: `z siedzibą w Białymstoku`, jeżeli jest powiązana z konkretną stroną;
- adres do doręczeń, adres ePUAP, skrytki pocztowe, adresy e-mail i domeny.

Co do zasady nie maskować samego miasta w treści ogólnej, np. `rozprawa odbyła się w Warszawie`, chyba że połączone jest z osobą, adresem, sądem, siedzibą albo unikalnym zdarzeniem.

## 6. Firmy i organizacje

Maskować jako `COMPANY`, `CONTRACTOR` albo aliasy:

- pełne nazwy z formą prawną: `sp. z o.o.`, `S.A.`, `sp.k.`, `sp.j.`, `PSA`, `fundacja`, `stowarzyszenie`, `spółdzielnia`;
- nazwy bez formy prawnej, jeśli są w roli strony: `Powód: OLIMP LABORATORIES`, `Klient: Meble New Concept`, `w imieniu Klienta – OLIMP LABORATORIES`;
- skróty i aliasy zdefiniowane w dokumencie: `dalej jako „NOVUS”`, `zwany dalej Wykonawcą`;
- kody firmowe w numerach umów lub zleceń, gdy pochodzą od wykrytej firmy: `NOVUS/OMNITEX/B2B/05/2026`;
- jednoosobową działalność z imieniem i nazwiskiem właściciela.

Nie maskować nagłówków i generycznych sformułowań: `UMOWA NAJMU`, `WEZWANIE DO ZAPŁATY`, `PROTOKÓŁ`, `Zgromadzenie Wspólników`, chyba że są częścią nazwy własnej strony.

## 7. Identyfikatory i numery

Maskować:

- PESEL, NIP, REGON, KRS, BDO, CEIDG;
- seria i numer dowodu osobistego oraz paszportu; jeżeli checksum jest niepoprawny, ale kontekst mówi `dowód osobisty`, maskować jako kontekstowy dokument;
- IBAN/NRB i rachunki bankowe, także fikcyjne numery testowe w kontekście `rachunek bankowy`, `konto`, `do przelewu`;
- sygnatury spraw, repertorium A, numery decyzji, numery postępowań, znaki sprawy;
- księgi wieczyste, VIN/rejestracje pojazdów, numery polis/szkód, przesyłki, zamówienia, zlecenia i faktury;
- loginy, repozytoria, tokeny API, domeny, URL, IP.

Nie maskować:

- numerów paragrafów, artykułów, ustępów, punktów i załączników;
- zwykłych kwot, procentów, terminów i dat, chyba że są elementem identyfikującym osobę lub sprawę;
- PKD, jeżeli nie jest częścią danych identyfikujących konkretną firmę.

## 8. Sądy, organy i sprawy

Maskować:

- nazwę sądu w konkretnej sprawie, np. `Sąd Rejonowy dla Warszawy-Mokotowa w Warszawie`;
- sygnaturę, repertorium, identyfikator wydruku KRS, znak sprawy;
- komornika, notariusza, syndyka, kuratora, biegłego, pełnomocnika jako osoby.

Ostrożnie z organami publicznymi w treści ogólnej. `Rada Gminy Przemyśl` może być informacją publiczną i nie zawsze wymaga maskowania, ale jeśli jest elementem konkretnego postępowania lub adresu strony, powinna być analizowana kontekstowo.

## 9. Odwracalność i mapa

Wymogi minimalne:

1. Każdy placeholder ma jednoznacznie wskazywać kategorię i numer: `[PERSON_1]`, `[COMPANY_1]`, `[ADDRESS_FULL_1]`.
2. Ten sam oryginalny ciąg w jednym dokumencie ma otrzymać ten sam placeholder albo alias prowadzący do tego samego bytu.
3. Odmiany gramatyczne tej samej osoby mogą mieć aliasy, ale restore musi przywracać dokładny tekst sprzed pseudonimizacji.
4. Mapa restore nie może być przechowywana w jawnych plikach pomocniczych. Backup ma być chroniony i separowany od pliku pseudonimizowanego.
5. Test roundtrip jest obowiązkowy dla każdej nowej reguły: `oryginał → maska → restore = oryginał`.
6. Test musi obejmować DOCX, nie tylko tekst plain, bo dane mogą być w nagłówkach, stopkach, komentarzach, metadanych, alt textach i custom XML.

## 10. Precedencja i nakładanie encji

Priorytety:

1. Sekrety, PESEL, dokumenty tożsamości, rachunki bankowe, NIP/REGON/KRS.
2. Pełne adresy i adresy wiejskie.
3. Pełne osoby z rolami i osobowe wiersze tabel.
4. Firmy i kontrahenci.
5. Alias/samo nazwisko/samo imię tylko po potwierdzeniu z kontekstu.
6. Domeny, URL, IP, loginy, numery techniczne.

Jeżeli encje nachodzą na siebie, preferować dłuższy i bardziej konkretny zakres, ale nie wolno przez to zostawić PESEL/NIP/rachunku w środku większej encji.

## 11. Korpus testowy dla CSM

Claude Code powinien rozbudować testy o plik JSON/CSV z przypadkami:

- `input`,
- `must_mask`,
- `must_keep`,
- `expected_categories`,
- `roundtrip_required`,
- `document_profile`: `pleadings`, `contracts`, `notarial`, `krs`, `general`.

Minimalne profile:

1. Pisma procesowe: pozew, odpowiedź na pozew, wniosek, pełnomocnicy, sądy, sygnatury.
2. Umowy: strony, reprezentanci, rachunki, adresy do doręczeń, aliasy.
3. Akty notarialne i protokoły: repertorium, stawający, PESEL, rodzice, spółki, udziały.
4. Dokumenty korporacyjne/KRS: spółki, organy, wspólnicy, adresy, kapitał.
5. Dokumenty techniczne/AI: tokeny, loginy, domeny, repozytoria.

## 12. Kryteria akceptacji reguł

Nowa reguła może wejść do CSM tylko wtedy, gdy:

- maskuje co najmniej jeden realny problem z testów użytkowników;
- ma test false positive, np. nie maskuje nagłówka lub przepisu;
- ma test roundtrip;
- nie łamie dotychczasowych kategorii i map;
- nie zwiększa zależności instalacyjnych bez potrzeby;
- jest opisana w raporcie zmian.
