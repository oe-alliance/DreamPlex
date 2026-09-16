# Note di rilascio

🇬🇧 *These notes are also available [in English](RELEASENOTES.md).*

---

## 3.1.1

### 🐛 Correzioni

- I server Jellyfin 12.0 rifiutavano ogni richiesta con "401 unauthorized" -
  sfoglia, immagini e riproduzione diretta si basavano tutte su metodi di
  autenticazione (`X-Emby-Authorization`, `X-MediaBrowser-Token`,
  `?api_key=`) rimossi del tutto dalla 12.0. Passato ovunque al moderno
  header `Authorization: MediaBrowser ...`, incluso un espediente per gli
  URL di riproduzione diretta passati direttamente al player nativo.
  Funziona invariato anche con qualsiasi server Jellyfin dalla 10.8 in poi.

---

## 3.1.0

### ✨ Novità

- Supporto Jellyfin: rilevamento in rete, autenticazione (nome utente e
  password, oppure chiave API), profili di qualità, override immediato di
  traccia audio/sottotitoli
- Configurazione XML unificata per tutte le impostazioni e i server, al posto
  dei tre archivi separati precedenti
- Proposta della puntata successiva con conto alla rovescia configurabile, in
  stile con le principali piattaforme di streaming
- Nuova skin opzionale "Carousel" (HD e FHD): menu a barra laterale verticale
  con scorciatoie numeriche, e un banner "hero" con rotazione nel menu
  server - locandina, trama, conto alla rovescia al prossimo suggerimento,
  avviabile con OK o il tasto blu
- Il banner hero ora unisce "Continua a guardare" (in corso/prossimo
  episodio) e "Proposto" (aggiunti di recente), ciascuno etichettato; una
  serie intera suggerita così apre la sfoglia stagioni/episodi invece di non
  fare nulla, e il numero di suggerimenti richiesti è personalizzabile
- Pannello dettagli con cast/regia/valutazione (tasto EPG), prima
  disponibile solo durante la riproduzione, ora anche mentre sfogli le
  cartelle
- Un secondo tasto (LIST, PVR, ARCHIVE, MEDIA o FILE, quale che sia inviato
  dal telecomando) apre anch'esso la schermata Aiuto, per i telecomandi il
  cui tasto HELP non arriva al decoder come KEY_HELP
- "Aggiorna libreria" (giallo, schermate di sfoglio) è ora un'unica azione
  prevedibile - sempre un aggiornamento completo, incluse locandine/sfondi,
  con un avviso a schermo "Aggiornamento in corso..."

### ⬆️ Aggiornamento dalla 3.0

- La configurazione esistente viene migrata automaticamente al primo avvio —
  server, impostazioni globali, utenti Home, associazioni dei percorsi; nulla
  da reinserire
- Installare sopra la versione precedente cancella la cache e i media
  scaricati (locandine/sfondi vanno risincronizzati); nel dubbio, prima un
  backup: `tar czf /tmp/dreamplex-backup.tar.gz /hdd/dreamplex /etc/enigma2/settings`
- Sostituisce automaticamente i pacchetti separati del feed ufficiale

### 🐛 Correzioni

- Il plugin non si avviava affatto, in diversi modi a seconda dell'immagine:
  un ciclo di auto-import, due residui di Python 2, un crash da log troppo
  precoce, un `UnboundLocalError` nelle impostazioni Jellyfin, e un import di
  Twisted che si scontrava con il reactor di enigma2
- Un nuovo server creato non veniva mai salvato davvero, e annullarne la
  creazione andava in crash invece di scartarlo
- L'autoplay saltava l'ultimo episodio di una lista, e non partiva mai con
  due soli episodi
- Il plugin non compilava affatto per un errore di indentazione
- Vari crash `NameError`/`ModuleNotFoundError` da residui di Python 2
- Un server poteva venire salvato involontariamente subito dopo un login
  remoto riuscito, anche chiudendo la conferma successiva con Annulla/Exit
  invece di confermarla davvero
- Il tasto STOP del telecomando (chiude il plugin), e i pulsanti
  sincronizza/cache e cambia utente del menu server, funzionavano ma non
  erano mai mostrati a schermo né nella legenda Help - in alcune skin il
  pulsante cambia utente mancava del tutto
- Cambiare skin richiedeva un riavvio completo della GUI; ora basta uscire e
  rientrare nel plugin, con un promemoria a schermo dopo il salvataggio
- Le locandine/sfondi di Jellyfin potevano non scaricarsi in silenzio per i
  contenuti mai messi in cache prima
- Il cambio skin da Impostazioni proponeva solo "default" - ogni altra skin
  installata veniva ignorata in silenzio
- La cache delle liste veniva scritta ma mai riletta - ogni cambio di
  schermata ricaricava dal server; ora una cartella vista di recente si apre
  all'istante, con una finestra di validità di 5 minuti
- "Aggiorna libreria" chiedeva al server di riscansionare solo su Plex, su
  Jellyfin andava in crash; ora riceve la stessa richiesta reale
- "Elimina cache" (Impostazioni) cancellava solo la cache delle liste, mai
  le locandine/sfondi scaricati - l'unico modo per forzarne un nuovo
  download era cancellarli a mano
- Il tasto Help non faceva nulla nel selettore server, nel menu server e
  nelle schermate di sfoglio - le descrizioni c'erano, ma niente apriva
  davvero la schermata Aiuto in quelle tre
- Una serie intera suggerita dal banner hero (a differenza di un singolo
  episodio) non faceva nulla in silenzio, o mandava in crash la sfoglia
  stagioni se aperta da lì
- I metadati (anno, cast, genere...) potevano restare nascosti a caso per un
  film in una cartella mista, finché non si visitava prima un'altra riga
- Alcune etichette a schermo non erano mai tradotte ("set 'Seen'",
  "fastScroll 'On/Off'", "playback mode '...'") o erano proprio sbagliate
  ("Runtime:" appariva come "Stato corrente" in italiano)
- Jellyfin non selezionava mai automaticamente un sottotitolo incorporato
  forzato, a differenza di Plex
- Testi ed evidenziazioni poco leggibili/invisibili nella skin Carousel (un
  presupposto sbagliato su come Enigma2 gestisce la trasparenza dei colori)
- Il Wake on Lan è ora disponibile anche per Jellyfin, non solo per Plex; il
  messaggio di server irraggiungibile non dice più "Plexserver"
  indipendentemente dal backend in uso
- Lo Scarica catalogo poteva scaricare locandine/sfondi senza un header di
  autenticazione su un server Jellyfin raggiungibile direttamente, e andava
  in crash se l'header veniva effettivamente allegato
- L'impostazione "preferisci sottotitoli forzati" del player non veniva mai
  letta
- Un paio di testi a schermo citavano "Plex" anche configurando un server
  Jellyfin

### 🔒 Sicurezza

- Ripristinata la verifica del certificato per le connessioni a plex.tv
- La resa degli sfondi non passa più da una shell
- I file di cache vengono rifiutati se non scritti dal plugin stesso

### ⚡ Reattività

- Il rilevamento Jellyfin e Plex non blocca più il decoder durante la
  scansione della rete
- L'attesa del Wake on Lan non blocca più l'interfaccia

### 🔧 Sotto il cofano

- Compatibilità Python da 3.8 a 3.14
- Correzioni di packaging: sottopacchetti mancanti, dipendenze ridotte,
  niente più bytecode residuo spedito o lasciato dagli aggiornamenti
- Sostituite le clausole `except:` nude in tutto il codice
- Aggiunta la configurazione per l'analisi statica e alcuni script di test
- Rimossi alcuni handler di tasti del telecomando morti, mai implementati
- Il test di raggiungibilità del server e le impostazioni Wake on Lan sono
  ora dichiarati sull'interfaccia comune dei server, così un backend futuro
  non può più saltarli in silenzio

### 🌍 Traduzioni

- Le stringhe di Jellyfin sono ora estratte e traducibili
- Il catalogo sale a 568 stringhe; l'italiano è completo

---

## 1.06
- risolto #56: la sigla smetteva di suonare all'uscita

## 1.05
- corretto il controllo del percorso in riproduzione diretta per i server Windows
- aggiunto codice per prevenire errori di configurazione nella riproduzione diretta (barre e barre rovesciate)
- corretto l'ordinamento (i valori predefiniti di Plex ora non vengono toccati :-)
- corretti "newest" e "recently added" nelle serie TV
- corretto il greenscreen con l'opzione live TV attiva
- corretta la modalità streaming (buffer esaurito)
- corretta la funzione di aggiornamento
- corretta la selezione del media quando è disponibile più di una versione
- corretto il nome del tasto giallo in modalità locale diretta
- aggiunti i dettagli sui font nell'xml, per gli autori di skin
- diverse pulizie

## 1.04a (rilascio correttivo)
- corretto il greenscreen nella sezione serie TV

## 1.04
- corretta la modalità locale diretta con percorsi UNC
- corretta la modalità locale diretta per Plex su Windows
- nuova finestra di scelta quando in Plex esiste più di una versione del media
- nuova funzione: mostra la posizione del file => tasto menu
- nuove viste (elenco lungo ed elenco con sfondi), grazie a tobi79ac per le skin :-) => tasto blu
- gestore delle associazioni per la modalità locale diretta completamente rifatto
- nuovo conteggio visti/non visti per le serie TV
- diverse correzioni
- nuova posizione per gli aggiornamenti => bintray

## 1.03
- ritocchi all'interfaccia
- aggiunta la guida
- aggiunta la schermata "Informazioni"
- corretto il comportamento quando l'arresto della live TV è disattivato

## 1.02
- aggiunta la funzione di aggiornamento
- corretta la navigazione nelle serie TV
- rimosse le impostazioni del buffer (non funzionavano)
- corretto un problema di qualità nella modalità "transcodificata"
- le opzioni compaiono solo quando servono, in base alle altre impostazioni
- la modalità locale diretta è ora disponibile anche per Plex su Windows
- aggiunta la rotazione dei log, per avere un log anche dopo un greenscreen
- diverse correzioni e migliorie

## 1.01
- aggiunta la funzione di scorrimento rapido
- corretti "onDeck" e "recentlyViewed" nelle serie TV
- aggiunta l'opzione: arresta la live TV all'avvio
- aggiunta l'opzione: raggruppa le sezioni
- implementato il menu dei media
- nuova funzione nel menu dei media => segna come visto, non visto e aggiorna la sezione della libreria
- piccoli ritocchi alle skin
- piccole correzioni

## 1.00
- nuova skin HD (un grande grazie a IPMAN)
- rimosse per ora le skin SD e XD
- una montagna di correzioni
- un'altra montagna di correzioni
