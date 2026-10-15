# Wayland, l'affichage de sbx et le clavier

*🇬🇧 English version: [wayland-keyboard.md](wayland-keyboard.md)*

Ce document explique comment une application Linux qui tourne dans une Docker Sandbox peut afficher une fenêtre sur ton Mac, pourquoi le clavier s'y retrouve en QWERTY, et comment `sandbox-desktop` règle le problème. Il liste aussi les fonctionnalités de sbx et de Docker utilisées.

## Wayland en deux minutes

**Wayland** est le protocole d'affichage des bureaux Linux modernes, le successeur de X11. Il met en relation deux rôles :

- **Le compositeur** (le « serveur ») possède l'écran, le clavier et la souris. Il assemble les fenêtres de tout le monde en une seule image et décide qui reçoit les frappes clavier.
- **Les clients** sont les applications (VS Code, un terminal…). Chacun dessine le contenu de ses fenêtres dans des tampons mémoire et les confie au compositeur.

Les deux se parlent par une **socket Unix**. Un client trouve son compositeur grâce à deux variables d'environnement : `XDG_RUNTIME_DIR` (le répertoire) et `WAYLAND_DISPLAY` (le nom de la socket, par exemple `wayland-0`). Un chemin absolu dans `WAYLAND_DISPLAY` est aussi accepté.

### Et le clavier ?

C'est le point clé pour la suite. Le compositeur n'envoie pas des lettres aux applications. Il envoie :

1. une **keymap XKB**, la table qui dit « la touche n° 16 donne `a` » (c'est la disposition : `fr`, `us`, `ch`…) ;
2. puis, à chaque frappe, **le numéro physique de la touche**.

L'application traduit le numéro en caractère avec la keymap reçue. **La disposition clavier est donc choisie par le compositeur, pas par l'application.**

### Un compositeur dans un compositeur

Un compositeur peut lui-même être le client d'un autre compositeur. On parle de compositeur **imbriqué**. Il ouvre une seule fenêtre chez son parent, y affiche ses propres clients et **leur envoie sa propre keymap**. C'est tout le principe de la solution décrite plus bas.

## Comment une fenêtre de la sandbox arrive sur ton Mac

```
 Mac (hôte)                                        Sandbox (microVM Linux)
┌───────────────────────────────┐                ┌─────────────────────────────────────┐
│ sailor (crates/compositor)    │◄──── vsock ────┤ compositor-guest (crates/compositor- │
│ winit · une fenêtre macOS     │  scancodes bruts│ guest, smithay) — vrai serveur       │
│ native par surface Wayland    │                 │ Wayland, crée /run/display/wayland-0 │
└───────────────────────────────┘                │        ▲ client Wayland              │
                                                  │   VS Code (entrypoint du kit)        │
                                                  └─────────────────────────────────────┘
```

1. `sbx run --display` demande un affichage pour la sandbox. sandboxd pose le label `com.docker.sandbox.display=wayland` sur le conteneur.
2. Le moteur de la sandbox (docker-next, v0.6.0 ou plus) lit ce label et démarre, dans la microVM, le compositeur guest de sailor (`compositor-guest`) qui crée la socket **`/run/display/wayland-0`**.
3. Les événements clavier/souris sont capturés côté Mac par `sailor` (le process hôte, `crates/compositor`, basé sur winit) et relayés **bruts** par **vsock** (le canal entre la VM et l'hôte) jusqu'à `compositor-guest`, qui ouvre en retour une fenêtre macOS native pour chaque fenêtre Wayland qu'il affiche.
4. VS Code, lancé avec `--ozone-platform=wayland` et en rendu logiciel (la VM n'a pas de GPU), se connecte directement à `compositor-guest` — **pas** à un simple relais passif. Sa fenêtre apparaît sur ton bureau comme une application ordinaire.

## Pourquoi le clavier est en QWERTY

*Mis à jour d'après le code source de [`docker/sailor`](https://github.com/docker/sailor) (dépôt interne Docker) — ce qui suit n'est plus une déduction depuis l'extérieur, mais vérifié dans les sources.*

Il y a en réalité **deux compositeurs**, pas un seul :

- côté Mac, `crates/compositor` (basé sur **winit**) ouvre une fenêtre native par surface et relaie les événements clavier **bruts** (scancodes evdev, pas des caractères) vers la microVM par **vsock** ;
- côté Linux, dans la microVM, `crates/compositor-guest` (basé sur **smithay**) est le **vrai serveur Wayland** : c'est lui qui crée `/run/display/wayland-0`, possède `wl_seat`/`wl_keyboard`, et à qui VS Code se connecte directement.

![Pourquoi le clavier est fixé en QWERTY](diagrams/keyboard-path.png)

La disposition clavier est une **constante** dans ce second compositeur, pas un réglage manquant : dans `crates/compositor-guest/src/state.rs`, le clavier est initialisé avec `XkbConfig { layout: "us", .. }`, et la keymap réellement utilisée est une chaîne **US précompilée et embarquée dans le binaire** (`xkb_bootstrap/us_keymap.xkb`). C'est un contournement volontaire d'un bug : compiler une keymap depuis des noms RMLVO (`xkb_keymap_new_from_names`) nécessite une base XKB sur disque, absente des images guest minimales, ce qui faisait **segfaulter** `libxkbcommon` ([`docker/sailor#1677`](https://github.com/docker/sailor/issues/1677), corrigé en embarquant la keymap US à la place). VS Code ne peut rien y faire : il reçoit la keymap que `compositor-guest` lui envoie, et celle-ci est toujours `us`.

Fait notable : la plomberie pour un réglage par disposition existe déjà en partie. `compositor-guest` retraduit déjà certaines touches au cas par cas — `keymap.rs` transforme ⌘ (Super) en Ctrl ou Ctrl+Maj selon l'application focalisée (terminal ou non), activable/désactivable via `sailor run --no-key-remap` (qui passe `display.keymap=0` au kernel de la microVM, lu par `container-init`). Un futur `--keyboard-layout` suivrait vraisemblablement le même chemin — mais à ce jour, **aucune issue n'est ouverte dessus** côté `docker/sailor`.

## Une solution partielle (et coûteuse) : un compositeur imbriqué, labwc

```
 Mac (hôte)                         Sandbox
┌───────────────────────┐        ┌────────────────────────────────────────────────┐
│ Compositeur de sailor │◄─vsock─┤ compositor-guest (déjà un vrai compositeur)    │
│  └ fenêtre « labwc »  │        │        ▲ client (une seule fenêtre) ─ keymap us│
└───────────────────────┘        │      labwc  ← keymap fr / mac                  │
                                 │        ▲ socket labwc ($XDG_RUNTIME_DIR)       │
                                 │      foot, ou autre application                │
                                 └────────────────────────────────────────────────┘
```

**labwc** est un petit compositeur Wayland, basé sur la bibliothèque wlroots. `sandbox-desktop` le lance **comme client de `compositor-guest`** — donc, avec ce qu'on sait maintenant, comme un **troisième** compositeur dans la chaîne (sailor → compositor-guest → labwc → application), pas un second :

- labwc ouvre **une seule fenêtre** sur le Mac et crée sa propre socket pour les applications qu'il lance ;
- il reçoit les frappes de sailor, et les **retraduit avec sa propre keymap** : celle de `XKB_DEFAULT_LAYOUT` / `XKB_DEFAULT_VARIANT`, lue dans `~/.config/labwc/environment` ;
- les applications lancées **dans** labwc (foot, ou ce que tu passes à `sandbox-desktop`) reçoivent cette keymap : elles sont en AZERTY.

Ce que fait `sandbox-desktop` (dans `kit/bin/`), dans l'ordre :

| Étape | Pourquoi |
|---|---|
| Vérifie que `/run/display/wayland-0` existe | Sans `--display` à la création, il n'y a pas d'affichage |
| `WAYLAND_DISPLAY=/run/display/wayland-0` (chemin absolu) | sbx positionne par défaut `WAYLAND_DISPLAY=wayland-0` dans `XDG_RUNTIME_DIR=/run/user/1000`. Cette socket-là est le **pont presse-papier** de sbx, pas un compositeur : labwc échouerait en s'y connectant |
| `WLR_RENDERER=pixman` | Rendu logiciel : la VM n'a pas de GPU |
| `LANG=fr_FR.UTF-8` | Locale générée dans l'image (`locale-gen`), sans quoi foot se plaint d'une locale `C` |
| Écrit `~/.config/labwc/environment` à partir des kit args | C'est la façon documentée de régler la disposition de labwc, et celle qui a été validée à la main dans une vraie sandbox |
| Lance l'application avec `SANDBOX_WAYLAND_SOCKET` pointant vers la socket de labwc | `sandbox-code` lit cette variable : sans ça, VS Code se connecterait à l'affichage de la sandbox plutôt qu'à labwc |

## Les fonctionnalités utilisées

### Docker Sandboxes (sbx)

| Fonctionnalité | Rôle ici |
|---|---|
| **Sandbox = microVM** (moteur docker-next, hyperviseur sailor) | Isole l'IDE et l'agent du Mac. Chaque sandbox a son propre noyau Linux et son propre réseau |
| **`--display`** (expérimental, feature flag `feature.sandbox-display`, activable avec `DOCKER_SANDBOXES_FEATURE_SANDBOX_DISPLAY=1`) | Fournit la socket Wayland `/run/display/wayland-0`, relayée en vsock vers le compositeur de sailor sur l'hôte. À passer **à la création** de la sandbox. Le presse-papier et le glisser-déposer sont volontairement désactivés sur cet affichage |
| **Kits v3** (`kind: workload`, `kit.yaml` + `kit.dockerfile`) | Décrivent l'environnement : l'image à construire, l'entrypoint (VS Code), les capacités |
| **Kit args** (`--kit-arg nom=valeur`) | `vscodeVersion` et `claudeCodeVersion` sont des arguments de **build** (`buildArg`). `waylandSocket`, `keyboardLayout` et `keyboardVariant` sont des arguments d'**exécution**, transmis comme variables d'environnement (`env`) |
| **Capacité `network-policy`** | Liste les seuls domaines joignables quand l'IDE tourne, appliquée depuis l'extérieur de la VM |
| **Capacité `agent-context`** | Explique à Claude Code l'environnement dans lequel il tourne |
| **`sbx exec -it`** | Lance `sandbox-desktop` dans une sandbox déjà démarrée, avec un terminal attaché |
| **Validation des kits** | `kit.yaml` a été vérifié avec le validateur officiel de la spec v3 (`sandbox-kit-spec`), sans erreur ni avertissement |

### Docker

| Fonctionnalité | Rôle ici |
|---|---|
| **Dockerfile / BuildKit** | `kit.dockerfile` construit l'image du kit. `RUN --mount=type=bind` rend le dossier du kit disponible pendant le build sans le copier dans une couche : seuls les lanceurs installés restent dans l'image |
| **Image de base** `docker/sandbox-templates:shell` | Le template officiel d'une sandbox (Ubuntu 26.04, utilisateur `agent`, outils de base) |
| **Volume Docker partagé** (tests) | `tests/test-display.sh` et `tests/test-desktop.sh` partagent la socket d'un compositeur **sway headless** entre deux conteneurs, dans le rôle de `/run/display/wayland-0`. On peut ainsi tester sans `sbx` ni écran |

### Côté Linux, dans l'image

| Composant | Rôle |
|---|---|
| **labwc** | Compositeur imbriqué, qui applique la disposition clavier |
| **xkbcommon** (`XKB_DEFAULT_LAYOUT`, `XKB_DEFAULT_VARIANT`) | La bibliothèque qui construit la keymap à partir de la disposition |
| **foot** | Terminal Wayland léger, l'application lancée par défaut |
| **locales** (`fr_FR.UTF-8`) | La locale française, générée au build |

## Ce qui a été vérifié

- **Dans une vraie sandbox**, à la main : labwc imbriqué avec le fichier `~/.config/labwc/environment` donne bien de l'AZERTY.
- **Sans sbx**, avec un compositeur headless : l'étape d'installation passe sur Ubuntu 26.04, labwc ouvre une seule fenêtre, foot se dessine à l'intérieur de labwc, et la disposition vient des kit args.
- **Limite n°1** : VS Code n'autorise qu'une instance. Tant que le VS Code de l'entrypoint tourne (dessiné directement sur l'affichage, donc en QWERTY), lancer `sandbox-code` dans `sandbox-desktop` ouvre la fenêtre dans l'instance existante. Pour un VS Code en AZERTY, il faudrait que l'entrypoint lui-même démarre VS Code dans labwc.
- **Limite n°2, plus grave** : en testant ce scénario (entrypoint démarrant dans labwc), l'image perd en netteté. L'explication la plus probable, maintenant qu'on sait que labwc s'imbrique dans `compositor-guest` (déjà un compositeur complet, pas un simple relais) : un compositeur wlroots imbriqué ne négocie pas forcément le facteur d'échelle HiDPI de son parent, et rend à l'échelle 1 pendant que `compositor-guest`/sailor affichent en Retina — d'où le flou. Rien d'impossible à corriger en théorie (forcer l'échelle de sortie de labwc), mais ça ne se vérifie que dans une vraie sandbox, et ça n'a pas été retenu comme solution pour ce kit.

**Conclusion pratique** : la disposition clavier n'est pas un réglage qu'il manque au kit, ni quelque chose de corrigible proprement par un compositeur imbriqué côté image — c'est une constante dans le compositeur guest de `sailor` (`layout: "us"` en dur). La bonne correction se ferait en amont, dans `docker/sailor`, en suivant le même schéma de plomberie que le remap ⌘→Ctrl déjà en place (un flag `--keyboard-layout`, une poignée de keymaps précompilées embarquées comme `us_keymap.xkb`). Il n'y a pas d'issue ouverte sur le sujet à ce jour.
