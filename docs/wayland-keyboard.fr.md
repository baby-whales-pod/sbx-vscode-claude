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
 Mac (hôte)                               Sandbox (microVM Linux)
┌──────────────────────────────┐        ┌──────────────────────────────────┐
│ Compositeur Wayland de sailor│◄─vsock─┤ /run/display/wayland-0           │
│ (une fenêtre macOS native    │        │        ▲                         │
│  par fenêtre Wayland)        │        │        │ client Wayland          │
└──────────────────────────────┘        │   VS Code (entrypoint du kit)    │
                                        └──────────────────────────────────┘
```

1. `sbx run --display` demande un affichage pour la sandbox. sandboxd pose le label `com.docker.sandbox.display=wayland` sur le conteneur.
2. Le moteur de la sandbox (docker-next, v0.6.0 ou plus) lit ce label et crée la socket **`/run/display/wayland-0`** dans la microVM.
3. Cette socket est relayée par **vsock** (le canal entre la VM et l'hôte) jusqu'à un compositeur Wayland qui tourne sur l'hôte, fourni par **sailor**, l'hyperviseur de Docker Sandboxes. Il ouvre une fenêtre macOS native pour chaque fenêtre Wayland.
4. VS Code, lancé avec `--ozone-platform=wayland` et en rendu logiciel (la VM n'a pas de GPU), se connecte à cette socket. Sa fenêtre apparaît sur ton bureau comme une application ordinaire.

## Pourquoi le clavier est en QWERTY

Le compositeur de sailor est une bibliothèque native (Rust/winit) qui ne propose aucun réglage de disposition clavier : ni sbx, ni docker-next, ni l'API d'affichage n'exposent une telle option. En pratique, les applications dessinées directement sur `/run/display/wayland-0` reçoivent une keymap qui ne suit pas la disposition du Mac, et on tape en QWERTY. L'application ne peut rien y faire : elle utilise la keymap que le compositeur lui donne.

## La solution : un compositeur imbriqué, labwc

```
 Mac (hôte)                         Sandbox
┌───────────────────────┐        ┌───────────────────────────────────────────┐
│ Compositeur de sailor │◄─vsock─┤ /run/display/wayland-0                    │
│  └ fenêtre « labwc »  │        │        ▲ client (une seule fenêtre)       │
└───────────────────────┘        │      labwc  ← keymap fr / mac             │
                                 │        ▲ socket labwc ($XDG_RUNTIME_DIR)  │
                                 │      foot, ou autre application           │
                                 └───────────────────────────────────────────┘
```

**labwc** est un petit compositeur Wayland, basé sur la bibliothèque wlroots. `sandbox-desktop` le lance **comme client** de l'affichage de la sandbox :

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
- **Limite** : VS Code n'autorise qu'une instance. Tant que le VS Code de l'entrypoint tourne (dessiné directement sur l'affichage, donc en QWERTY), lancer `sandbox-code` dans `sandbox-desktop` ouvre la fenêtre dans l'instance existante. Pour un VS Code en AZERTY, il faudrait que l'entrypoint lui-même démarre VS Code dans labwc.
