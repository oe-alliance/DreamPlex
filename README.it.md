# DreamPlex

**Client per server multimediali su decoder Enigma2.**

Sfoglia le tue librerie di film, serie TV e musica direttamente dal decoder e
riproducile sul televisore, con locandine, sfondi e metadati.

![Licenza](https://img.shields.io/badge/licenza-GPL--2.0--or--later-blue)
![Python](https://img.shields.io/badge/python-3.8%2B-blue)
![Piattaforma](https://img.shields.io/badge/piattaforma-Enigma2-lightgrey)

🇬🇧 *This document is also available [in English](README.md).*

---

## Server supportati

| Server | Rilevamento in rete | Autenticazione |
|---|---|---|
| **Plex** | GDM (multicast) | locale oppure account plex.tv, con utenti Home |
| **Jellyfin** | scansione HTTP della sottorete | nome utente e password, oppure chiave API |

Entrambi convivono: puoi configurare più server, di tipo diverso, e passare
dall'uno all'altro dal menu.

## Funzionalità

**Librerie e navigazione**
- Film, serie TV, musica e sezioni miste
- Più viste selezionabili (elenco, elenco lungo, con sfondi) e vista
  predefinita configurabile per tipo di libreria
- Filtri per genere, anno, valutazione, durata, e ricerca testuale
- Conteggio visti / non visti per le serie TV
- Cache locale delle risposte del server per una navigazione più rapida

**Riproduzione**
- Riproduzione diretta, locale diretta (via percorsi di rete mappati) o
  transcodificata, con profili di qualità selezionabili
- Ripresa da dove avevi interrotto, con stato riportato al server
- Selezione di traccia audio e sottotitoli, con lingue preferite e supporto
  ai sottotitoli forzati
- **Proposta della puntata successiva**: verso la fine di un episodio compare
  in basso a destra un riquadro con conto alla rovescia. `OK` passa subito
  alla puntata seguente, `EXIT` annulla, e in assenza di azione il passaggio
  avviene allo scadere del countdown. Soglia e durata sono configurabili.

**Contenuti offline**
- Sincronizzazione di locandine e sfondi sul disco del decoder
- Resa degli sfondi come video di sottofondo nelle viste

**Altro**
- Utenti multipli, con protezione tramite PIN
- Wake on Lan per accendere il server prima della connessione
- Player remoto: comanda la riproduzione da un'app compatibile
- Interfaccia tradotta in 8 lingue

## Installazione

Il pacchetto è indipendente dall'architettura: lo stesso `.ipk` vale per
Zgemma, Vu+ e gli altri decoder Enigma2.

```
opkg install ./dreamplex_*_all.ipk
```

Dopo l'installazione il plugin compare fra le estensioni. Al primo avvio
aggiungi un server dal menu **Server**, usando il rilevamento automatico
oppure inserendo indirizzo e porta a mano.

### Requisiti

- Immagine Enigma2 con **Python 3.8 o superiore**
- Pacchetto richiesto: `python3-six`

Questi sono facoltativi, ciascuno serve a una singola funzione. Il plugin si
avvia e funziona anche senza, e segnala quando ne manca uno:

| Pacchetto | Serve per |
|---|---|
| `gstreamer1.0-plugins-bad-fragmented` | riproduzione transcodificata |
| `python3-pillow`, `mjpegtools` | resa degli sfondi come video |

## Compilazione dai sorgenti

```
autoreconf -i
./configure --prefix=/usr
make
make DESTDIR=/percorso/di/staging install
```

Non ci sono componenti native da compilare: il plugin è interamente in
Python, e l'unico passo di compilazione riguarda i cataloghi di traduzione
(`.po` → `.mo`), che sono indipendenti dall'architettura.

## Skin

Grazie di cuore agli autori delle skin :-)

- **Blockbuster** — [vuplus-support.org](http://www.vuplus-support.org/wbb3/index.php?page=Thread&threadID=69568&s=e395351f57ca026d487fb76176f04b75bbb59c0f)
- **YouPlex** (Blue, Green, Purple, Red) — [OpenViX/DreamPlexSkins](https://github.com/OpenViX/DreamPlexSkins)
- **Plex_Experience** — [OpenViX/DreamPlexSkins](https://github.com/OpenViX/DreamPlexSkins)

Il plugin include le skin `default`, `default_FHD`, `BlueMod`, `BlueMod_FHD`,
`Carousel` e `Carousel_FHD`, disponibili in risoluzione 720p e 1080p.

`Carousel` reinterpreta il menu principale e quello server con una barra
laterale verticale: le voci di menu hanno una scorciatoia numerica (1-9), e
il menu server mostra un banner "hero" con rotazione (locandina, trama,
conto alla rovescia al prossimo suggerimento) avviabile direttamente con OK
o il tasto blu. I suggerimenti uniscono titoli in corso/prossimo episodio
("Continua a guardare") e aggiunti di recente ("Proposto"), ciascuno
etichettato; scegliendo una serie intera si apre la sfoglia
stagioni/episodi invece di avviarne la riproduzione. L'intervallo di
rotazione, dopo quanti giri recuperare nuovi suggerimenti, e il numero
massimo di suggerimenti richiesti sono tutti configurabili in Impostazioni
(intervallo 0 disattiva la rotazione). Nel selettore server (nessun server
ancora scelto), un testo contestuale accanto al banner DreamPlex spiega cosa
fa ciascuna voce di menu.

## Traduzioni

Ceco, danese, tedesco, inglese, inglese britannico, spagnolo, francese e
italiano. I cataloghi si trovano in [`po/`](po/): per contribuire, aggiorna il
file della tua lingua e apri una pull request.

## Licenza

GNU General Public License, versione 2 o successiva. Vedi
[`src/LICENSE.txt`](src/LICENSE.txt).

## Crediti

Creato da **DonDavici** (2012) e **jbleyel** (2021), con codice proveniente da
altri plugin: tutti i meriti ai rispettivi autori.

Progetto originale: [oe-alliance/DreamPlex](https://github.com/oe-alliance/DreamPlex)
