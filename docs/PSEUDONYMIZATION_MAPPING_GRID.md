# CSM v1.0 — pseudonymization mapping grid

Status: rc16 local hygiene draft  
Purpose: single source of truth for what CSM should detect, how placeholders should be named, what must not be detected, and how restore must be validated.

This grid is intentionally broader than the current code. Rows marked `implemented` are expected to be covered by the current detector layer. Rows marked `candidate` are required by the product model but may still need detector, UI and test implementation before final 1.0 or 0.7.

## Validation rules common to every category

1. Every masked value must have a reversible restore entry.
2. The restore operation must return the original text byte-for-byte for plain-text cases covered by `tools/evaluate_pseudonymization_grid.py`.
3. Detection must be span-safe: only detected ranges may be masked. Do not reintroduce broad blind global replacement.
4. A legal role label must not be swallowed into the placeholder value. Correct: `Pozwany [FIRMA_1]`. Incorrect: `[FIRMA_1] = "Pozwany Mucha sp. z o.o."`.
5. Ordinary words that can also be surnames or localities, such as `Mucha`, `Pustynia`, `Lis`, `Wilk`, `Kot`, `Kowal`, `Kurek`, `Mazur`, `Baran`, must be masked only when legal context makes them identifying.

## Grid

| Category | Status | Placeholder | Detects | Must not detect | Positive examples | Negative examples | Legal context | Aliases | Reversible | Validation / tests |
|---|---:|---|---|---|---|---|---|---|---|---|
| PERSON | implemented | `[OSOBA_N]` | Full personal names, inflected names, legal-role persons, title-prefixed single-token surname in context | Generic title-case legal phrases | `Jan Nowak`, `Pani Iwony Teresy Ustrzyckiej`, `Pani Mucha` | `Ogólne Warunki`, `Kodeks Cywilny`, ordinary `mucha` | party, representative, witness, attorney, PESEL/address context | yes | yes | legacy regression suites and grid evaluator |
| PERSON_ALIAS | implemented | `[OSOBA_N_ALIAS_M]` | Unambiguous surname/first-name variants of detected persons | Ambiguous bare surname shared by several persons | `Nowakowi`, `Ustrzyckiej`, unique `Mucha` | bare `Kowalski` when two Kowalskis exist | later references in pleadings/contracts | yes | yes | identity ledger tests, ambiguity warning tests |
| COMPANY | implemented | `[FIRMA_N]` | Companies with legal suffix/prefix and private legal entities | Headings and document titles | `Mucha sp. z o.o.`, `ABC S.A.` | `UMOWA SPRZEDAŻY`, `WEZWANIE DO ZAPŁATY` | party/contractor/corporate context | yes | yes | rc16 heading/asset hygiene regression, release hygiene |
| CONTRACTOR | implemented | `[FIRMA_N]` | Party-context company or contractor without legal suffix | Legal headings, role labels | `OLIMP LABORATORIES` after `Powód:` or `w imieniu Klienta` | `SPRZEDAŻY` after `UMOWA` | client, plaintiff, defendant, counterparty | yes | yes | grid evaluator |
| COMPANY_ALIAS | implemented | `[FIRMA_N_ALIAS_M]` | Short names, acronyms and inflected company aliases derived from a detected company | Legal/common abbreviations | `OLIMP`, unique acronym from company name | `VAT`, `KRS`, `UMOWA`, `SLA` | later references and contract numbers | yes | yes | alias and context tests |
| COMPANY_CODE_CONTEXT | implemented | `[FIRMA_N_ALIAS_M]` | Company-like tokens embedded in contract numbers | B2B/B2C/date-only segments | `NOVUS` in `NOVUS/B2B/05/2026` | `B2B`, `2026` | contract number context | yes | yes | contract number tests |
| ADDRESS | implemented | `[ADRES_N]` | Street address or residence locality in context | City/locality names without context | `zamieszkały w Pustyni`, `ul. Dąbrowskiego 23/35` | `Pustynia` used as landscape noun | residence/registered office/address context | no | yes | legacy regression suite and grid evaluator |
| ADDRESS_FULL | implemented | `[ADRES_N]` | Full address with street, number, postcode and city | Isolated postcode/city only | `ul. Czesława Hake 9, 15-001 Białystok` | `15-001` alone as full address | address label or direct full format | no | yes | address tests |
| ADDRESS_RURAL | implemented | `[ADRES_N]` | Rural/locality address with building number and postcode | Ordinary noun/locality without number/postcode | `Pustynia 84F, 39-200 Dębica` | `opisano pustynię` | address clause | no | yes | grid evaluator |
| ADDRESS_SIEDZIBA | implemented | `[ADRES_N]` | Locality after registered-office wording | Cities without registered-office context | `z siedzibą w Pustyni` | `w Pustyni występują grunty` | company seat context | no | yes | address context tests |
| POSTCODE_PL | implemented | `[KOD_POCZTOWY_N]` | Polish postcodes | Date fragments, case numbers | `42-200`, `15-001` | `12/200` | address context or direct postcode format | no | yes | validator tests |
| PESEL | implemented | `[PESEL_N]` | 11-digit PESEL | Other 11-digit numbers if not intended as PESEL, where context disambiguates | `PESEL: 90010112345` | invoice/order numbers | identity/legal person context | no | yes | grid evaluator |
| NIP | implemented | `[NIP_N]` | 10-digit tax IDs and hyphenated NIP | 10-digit invoice numbers | `NIP 123-456-32-18` | `Faktura VAT numer: 1234567890` | tax/company context preferred | no | yes | legal identifier tests, grid evaluator |
| REGON | implemented | `[REGON_N]` | 9- or 14-digit REGON | Random numeric strings | `REGON: 123456789` | amount/date/order fragments | company registry context | no | yes | identifier tests |
| KRS | implemented | `[KRS_N]` | KRS numbers | Other 10-digit numbers | `KRS 0000123456` | invoice number | registry context | no | yes | identifier tests |
| IDCARD_PL | implemented | `[DOWOD_OSOBISTY_N]` | Polish ID card numbers with checksum or context | Random `ABC123456` without context | `dowód osobisty ABC 123456` | product code | identity document context | no | yes | idcard checksum tests |
| PASSPORT | implemented as PASSPORT_PL/PASSPORT_CONTEXT | `[PASZPORT_N]` | Passport numbers in direct or label context | Product/reference codes | `paszport AB1234567` | ordinary code | identity document context | no | yes | passport tests |
| BANK_ACCOUNT | implemented | `[RACHUNEK_BANKOWY_N]` | Polish NRB/IBAN in payment context, including fictional test numbers | Non-account 26-digit sequences without context | `rachunek bankowy PL...` | random long numeric string | payment clause | no | yes | bank account tests |
| IBAN | implemented | `[RACHUNEK_BANKOWY_N]` | Checksum-valid IBAN/NRB | Fictional invalid IBAN outside context | `PL61109010140000071219812874` | fake 26 digits without context | direct financial identifier | no | yes | bank account tests |
| COURT | implemented | `[SAD_N]` | Court names | Generic `sąd` as common noun | `Sąd Okręgowy w Rzeszowie` | `sąd uznał` | pleading/case heading | yes | yes | court tests |
| COURT_ALIAS | candidate | `[SAD_N_ALIAS_M]` | Short court references | Generic court words | `SO w Rzeszowie` after full court | `sąd` | later pleading reference | yes | yes | candidate |
| SYGNATURA | implemented | `[SYGNATURA_N]` | Court case signatures | invoice/order numbers | `I C 123/24`, `sygn. akt V GC 55/25` | `FV/123/2024` | court/proceeding context | no | yes | pleading identifier tests |
| CASE_NUMBER | implemented as CASE_REF | `[CASE_NUMBER_N]` | Case or letter references after labels | Pure dates/amounts | `nr sprawy ABC.123.4.2026` | `123/2026` without label | case/letter context | no | yes | legal identifier tests |
| FINANCIAL_DOC_ID | implemented | `[DOKUMENT_FINANSOWY_N]` | Invoice/proforma/payment/terminal IDs | NIP/REGON when labelled as tax IDs | `Faktura VAT numer: 1234567890` | `NIP: 1234567890` | accounting/payment context | no | yes | grid evaluator |
| INVOICE_NUMBER | candidate | `[INVOICE_NUMBER_N]` | Invoice numbers as a distinct category | NIP/REGON/KRS | `FV/12/05/2026` | tax IDs | invoice context | no | yes | candidate or mapped to FINANCIAL_DOC_ID |
| ORDER_NUMBER | implemented as PROJECT_ID | `[ORDER_NUMBER_N]` | Order/project/ticket IDs | Dates and amounts | `zamówienie nr ORD-2026-001` | `2026` alone | order/project context | no | yes | project/order tests |
| NOTARY_REPERTORY | implemented as REPERTORIUM | `[NOTARY_REPERTORY_N]` | Notarial repertory numbers | Case signatures | `Rep. A nr 1234/2026` | `I C 123/24` | notarial deed | no | yes | identifier tests |
| LAND_AND_MORTGAGE_REGISTER | implemented as KW/LAND_REGISTER | `[KSIEGA_WIECZYSTA_N]` | Polish land and mortgage registers | Generic slash numbers | `RZ1Z/00012345/6` | `FV/123/2024` | real-estate context/direct KW format | no | yes | property tests |
| REAL_ESTATE_IDENTIFIER | implemented as PROPERTY_ID | `[NR_DZIALKI_N]` | Plot/parcel identifiers | Paragraph numbers | `działka nr 123/4`, `181701_1.0001.123/4` | `§ 123/4` | property context | no | yes | property tests |
| EMAIL | implemented | `[EMAIL_N]` | Email addresses | Non-email strings | `jan@example.pl` | `example.pl` alone | direct | domain alias | yes | smoke tests |
| PHONE | implemented | `[TELEFON_N]` | Polish phone numbers | Short numeric fragments | `+48 600 700 800` | amounts/date fragments | contact context/direct format | no | yes | phone tests |
| DOMAIN | implemented | `[DOMENA_N]` | Domains and domain aliases | Legal abbreviations with dots | `example.pl`, `www.example.pl` | `art.` | internet context/direct domain | yes | yes | internet tests |
| URL | implemented | `[URL_N]` | HTTP/HTTPS URLs | Plain path without scheme unless repository context | `https://panel.example.pl` | `C:\CSM` | direct URL | domain alias | yes | internet tests |
| LOGIN | implemented | `[LOGIN_N]` | Login/user IDs after labels | Ordinary words | `login: admin.test` | `admin` in prose | account/login context | no | yes | grid evaluator |
| SECRET | implemented | `[SEKRET_N]` | API keys/tokens/password-like values | Short ordinary words | `sk-proj-...`, `ghp_...` | `hasło` without value | secret/token context or known formats | no | yes | grid evaluator |
| TOKEN | implemented via SECRET | `[TOKEN_N]` | Access tokens | ordinary words | `access token: abcdef123456` | `token` alone | token label | no | yes | candidate split or SECRET |
| API_KEY | implemented via SECRET | `[API_KEY_N]` | API keys | public IDs unless sensitive | `api key: sk-...` | `API` | API key label | no | yes | candidate split or SECRET |
| IP_ADDRESS | implemented | `[IP_N]` | IPv4 addresses | Invalid IPs | `192.168.0.1` | `999.999.999.999` | direct | no | yes | internet tests |
| DATE_SENSITIVE | implemented as BIRTH_DATA / candidate general date | `[DATE_N]` | Birth data and sensitive dates | Generic contract dates unless policy says otherwise | `ur. 1 stycznia 1980 r. w Rzeszowie` | `dnia 18 maja 2026 r.` | birth/person context | no | yes | birth data tests |
| VEHICLE_REGISTRATION | implemented as VEHICLE_ID | `[NR_REJESTRACYJNY_N]` | VIN and registration numbers in context | Random plate-like strings | `nr rejestracyjny RZE12345`, `VIN ...` | product code | vehicle context | no | yes | vehicle tests |
| BDO | implemented | `[BDO_N]` | BDO registry numbers | REGON/NIP | `nr BDO 000123456` | `123456789` without label | waste registry context | no | yes | identifier tests |
| CEIDG_ID | implemented | `[NR_CEIDG_N]` | CEIDG entry identifiers | Generic company names | `CEIDG-ID ABC12345` | random code | sole proprietor context | no | yes | CEIDG tests |
| PERMIT_ID | implemented | `[NR_ZEZWOLENIA_N]` | Decisions, permits, concessions, licences | Case signatures unless labelled | `decyzja nr ABC.123.2026` | `I C 123/24` | administrative context | no | yes | admin identifier tests |
| RESIDENCE_CARD | implemented | `[KARTA_POBYTU_N]` | Residence card numbers | Other codes | `karta pobytu PL-ABC123` | product code | identity context | no | yes | identity tests |
| DRIVING_LICENSE | implemented | `[PRAWO_JAZDY_N]` | Driving licence numbers in context | Generic reference codes | `prawo jazdy nr ...` | order ID | identity context | no | yes | identity tests |
| PROF_LICENSE | implemented | `[UPRAWNIENIA_ZAWODOWE_N]` | Professional licence/wpis numbers | Generic licence word | `PWZ 1234567` | `licencja MIT` | professional/legal context | no | yes | professional ID tests |
| EDELIVERY_ID | implemented | `[NR_EDORECZENIA_N]` | ePUAP/e-delivery addresses | URLs/emails already covered | `/ABC/skrytka`, `AE:PL...` | ordinary path | e-delivery context | no | yes | e-delivery tests |
| POLICY_CLAIM_ID | implemented | `[NR_POLISY_N]` | Policy/claim/damage numbers | Case signatures unless insurance label | `nr szkody ABC12345` | `I C 123/24` | insurance context | no | yes | claim tests |
| SHIPMENT_ID | implemented | `[NR_PRZESYLKI_N]` | Tracking/shipment IDs | Invoice numbers | `tracking ABC123456` | `FV/1/2026` | shipment context | no | yes | shipment tests |
| ACCOUNT_ID | implemented | `[NR_KONTA_N]` | Account/customer/campaign IDs in named systems | Generic numbers | `GA4 ID G-ABC12345` | amount/date | marketing/payment/account context | no | yes | account ID tests |
| REPOSITORY | implemented | `[REPOZYTORIUM_N]` | Repo URLs or owner/repo references | Ordinary slash strings | `GitHub: owner/repo` | `art. 1/2` | repository context | no | yes | repository tests |

## Current rc16 local additions

- `UMOWA SPRZEDAŻY` and similar generic document-title tails are rejected as company/contractor candidates.
- `tools/evaluate_pseudonymization_grid.py` provides a plain-text evaluator for false negatives, false positives, wrong categories and restore failures.
- `server/data/regression_cases/pseudonymization_mapping_grid_cases.json` is the default corpus for the evaluator; current local corpus covers 16 cases across person, company, address, registry identifiers, identity documents, courts, case numbers, financial IDs, real-estate identifiers, internet/contact data, secrets, birth data, vehicle identifiers and bank/order identifiers.
- Case references such as `nr sprawy ABC.123.4.2026` are masked as one full identifier, without swallowing the next sentence.
- URLs followed by punctuation are masked without absorbing the following comma/full stop.
- Birth-date labels `data urodzenia` and short vehicle-registration labels `nr rej.` are covered by local regressions.

## Release gate for final 1.0

Final 1.0 must not be tagged unless the evaluator reports zero false negatives, false positives, wrong categories and restore failures for the default corpus, and Windows/Word/Inno/.NET testing confirms the same detector behavior inside the Word workflow.
