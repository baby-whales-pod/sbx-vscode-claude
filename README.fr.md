# My Secure IDE — VS Code + Claude Code dans une Docker Sandbox

*🇬🇧 English version: [README.md](README.md)*

Une démo **Kits v3** pour Docker Sandboxes (`sbx`) : VS Code et Claude Code tournent **dans** une sandbox (microVM), et seule la **fenêtre VS Code** apparaît sur ton bureau.

- L'agent (Claude Code) et l'IDE ne voient que le **projet monté**, pas le reste de la machine.
- Le réseau est limité à **ce que le kit autorise** (API Anthropic et connexion).
- Tout (VS Code, l'extension Claude Code, la CLI `claude`, les réglages) est **intégré à l'image** : une commande, et tout le monde a le même environnement.

![VS Code dans la sandbox](docs/images/vscode-in-sandbox.png)

> Architecture et schémas : [docs/architecture.fr.md](docs/architecture.fr.md)

---

## Prérequis

| Élément | Détail |
|---|---|
| Docker Sandboxes | `sbx` **v0.48+** (support des Kits v3) |
| Option `--display` | **Expérimentale**. Si `sbx run --help` ne l'affiche pas, active le feature flag : `export DOCKER_SANDBOXES_FEATURE_SANDBOX_DISPLAY=1` |
| Compte Claude | Abonnement Claude ou clé API Anthropic, pour Claude Code |

## Contenu du dossier

```
sbx-vscode-claude/
├── kit/                         # le kit v3 (ce que sbx construit)
│   ├── kit.yaml                 # descripteur : args, capacités, network policy, agent context
│   ├── kit.dockerfile           # l'image : VS Code + Claude Code sur le template shell
│   ├── bin/
│   │   ├── sbx-vscode-claude-session   # entrypoint : attend l'affichage Wayland puis lance VS Code
│   │   ├── sandbox-code            # lance VS Code avec les options « sans GPU / Wayland »
│   │   └── sandbox-desktop         # bureau labwc imbriqué, avec la disposition clavier des kit args
│   ├── config/                  # réglages VS Code (pas de télémétrie, pas de mises à jour, pas de Copilot)
│   ├── applications/            # entrée .desktop
│   └── sbx-vscode-claude-context.md # consignes données à l'agent (agent-context)
├── tests/
│   ├── test-display.sh          # test sans sbx (compositeur Wayland headless)
│   ├── test-desktop.sh          # même principe, pour sandbox-desktop
│   └── wayland-headless.Dockerfile
└── docs/
    ├── architecture.md / architecture.fr.md
    ├── wayland-keyboard.md / wayland-keyboard.fr.md  # Wayland, --display et la disposition clavier
    ├── diagrams/                # .drawio (éditable) + .svg + .png, générés par generate.py
    └── images/
```

## Lancer l'IDE

Depuis le dossier `sbx-vscode-claude` :

```bash
# Lance VS Code sur un projet (ici ~/projects/my-app)
sbx run --display --name sbx-vscode-claude ./kit ~/projects/my-app
```

- `--display` est **obligatoire**. Il fournit à la sandbox une socket Wayland (`/run/display/wayland-0`) dont les fenêtres s'affichent sur ton bureau. Il faut le passer **à la création** de la sandbox.
- `./kit` est la référence du kit. Les chemins relatifs doivent être explicites (`./…`).
- Sans chemin de workspace, c'est le **répertoire courant** qui est monté.
- Au premier lancement, `sbx` construit l'image du kit. Les lancements suivants la réutilisent.

La fenêtre VS Code s'ouvre sur le projet, avec **Claude Code** (icône dans la barre latérale et dans la barre d'état). **Fermer la fenêtre termine la session.**

### Figer les versions (kit args)

```bash
sbx run --display --name sbx-vscode-claude \
  --kit-arg vscodeVersion=1.141.1 \
  --kit-arg claudeCodeVersion=2.1.299 \
  ./kit ~/projects/my-app
```

| Arg | Défaut | Rôle |
|---|---|---|
| `vscodeVersion` | `latest` | Version de VS Code (dépôt apt Microsoft) |
| `claudeCodeVersion` | `latest` | Version de la CLI `@anthropic-ai/claude-code` (npm) |
| `waylandSocket` | `/run/display/wayland-0` | Socket Wayland sur laquelle VS Code dessine |

### Utiliser Claude Code

- **Dans VS Code** : clique sur l'icône Claude Code (barre latérale) et connecte-toi au premier lancement.
- **Dans le terminal** : ouvre le terminal intégré de VS Code (`` Ctrl+` ``) et lance `claude`.
- **Depuis l'hôte**, sans passer par la fenêtre :
  ```bash
  sbx exec sbx-vscode-claude claude --version
  ```

### Clavier AZERTY (bureau labwc)

Les fenêtres dessinées directement sur l'affichage de la sandbox ne suivent pas la disposition clavier de l'hôte : on se retrouve en QWERTY. Le kit embarque `sandbox-desktop`, qui ouvre un bureau **labwc** imbriqué dans l'affichage. Les applications lancées dedans utilisent la disposition choisie dans les kit args.

```bash
sbx exec -it sbx-vscode-claude -- sandbox-desktop           # un terminal foot
sbx exec -it sbx-vscode-claude -- sandbox-desktop <commande> # n'importe quelle autre application
```

La disposition se règle à la création :

```bash
sbx run --display --name sbx-vscode-claude \
  --kit-arg keyboardLayout=ch --kit-arg keyboardVariant=fr \
  ./kit ~/projects/my-app
```

| Arg | Défaut | Rôle |
|---|---|---|
| `keyboardLayout` | `fr` | Disposition XKB (`fr`, `ch`, `de`, `us`…) |
| `keyboardVariant` | `mac` | Variante XKB : `mac` pour un clavier Apple, vide (`keyboardVariant=`) pour un clavier PC |

Fermer la fenêtre labwc (ou Ctrl+C dans le terminal de l'hôte) termine le bureau. Le VS Code de l'entrypoint, lui, reste dessiné directement sur l'affichage, donc en QWERTY (voir *Limites connues*).

Pour comprendre le mécanisme (Wayland, `--display`, compositeur imbriqué) : [docs/wayland-keyboard.fr.md](docs/wayland-keyboard.fr.md).

### Se rattacher, lister, supprimer

```bash
sbx run --name sbx-vscode-claude          # se rattacher à la sandbox existante (spec déjà connue)
sbx ls                                 # lister les sandboxes
sbx rm sbx-vscode-claude                   # supprimer la sandbox
```

## Network policy

Le kit n'autorise que les hôtes dont Claude Code a besoin (`kit.yaml` → `network-policy@1`) :

```yaml
allow:
  - api.anthropic.com
  - anthropic.com / *.anthropic.com
  - claude.ai / *.claude.ai
  - claude.com / *.claude.com
```

Le **marketplace VS Code est bloqué** à l'exécution, car les extensions sont installées au build de l'image. Pour permettre aux développeurs d'installer d'autres extensions, décommente les lignes marketplace dans `kit.yaml`. Les policies de l'organisation (AI Gov) s'appliquent toujours en plus de celles du kit.

## Partager le kit avec l'équipe

```bash
sbx kit validate ./kit                               # valider le kit
sbx kit push ./kit registry.example.com/team/sbx-vscode-claude:0.1.0
# Puis, pour tout le monde :
sbx run --display registry.example.com/team/sbx-vscode-claude:0.1.0 ~/projects/my-app
```

## Tester sans sbx (CI ou machine sans écran)

`tests/test-display.sh` construit l'image, démarre un **compositeur Wayland headless** (sway) qui remplace celui fourni par `sbx`, lance l'IDE dessus et fait une capture d'écran :

```bash
./tests/test-display.sh
# ==> Windows on the compositor:  "app_id": "com.microsoft.VSCode"
# ==> Screenshot: tests/out/screenshot.png
```

`tests/test-desktop.sh` fait de même pour `sandbox-desktop`. Il vérifie que labwc ouvre une seule fenêtre sur le compositeur, que foot se dessine à l'intérieur de labwc et pas directement sur l'affichage, et que la disposition vient bien des kit args :

```bash
./tests/test-desktop.sh
# ==> OK. Screenshot: tests/out/desktop-screenshot.png
```

## Scénario de démo (≈ 5 min)

1. **Le problème** : « Les agents de code ont accès à toute la machine : `~/.ssh`, `~/.aws`, le réseau… »
2. **Une commande** : `sbx run --display ./kit ~/projects/my-app`. La fenêtre VS Code s'ouvre comme une application locale.
3. **L'agent au travail** : demande à Claude Code de modifier un fichier du projet. La modification apparaît sur l'hôte, dans le projet.
4. **Le confinement** : dans le terminal intégré, `ls ~/.ssh` et `cat /etc/hostname` montrent qu'on est dans la sandbox, pas sur l'hôte. `curl https://example.com` est bloqué par la policy.
5. **La reproductibilité** : `sbx kit push …` publie le kit, et chaque membre de l'équipe obtient **exactement** le même IDE.

## Limites connues

- `--display` est **expérimental** (feature flag `feature.sandbox-display`).
- **Pas de GPU** : rendu logiciel. C'est assez fluide pour un IDE, pas pour du graphisme lourd.
- **Disposition clavier** : les fenêtres dessinées directement sur l'affichage de la sandbox (dont le VS Code de l'entrypoint) restent en QWERTY. Seules les applications lancées via `sandbox-desktop` suivent `keyboardLayout`. Lancer `sandbox-code` dans `sandbox-desktop` ne suffit pas pendant que le VS Code de l'entrypoint tourne : VS Code n'autorise qu'une instance, et la fenêtre s'ouvrirait dans celle qui existe déjà.
- **Pas de keyring / D-Bus** : VS Code stocke ses secrets avec `--password-store=basic`. Il faudra peut-être se reconnecter après la recréation d'une sandbox.
- L'image est volumineuse (≈ 4,9 Go décompressée, dont 2,1 Go pour le template shell ; VS Code et Claude Code font le reste). Le premier build prend quelques minutes.
- **Pas encore validé de bout en bout avec `sbx`** : l'image et l'affichage Wayland ont été testés avec un compositeur headless (voir `tests/`). Il reste à vérifier sur une machine avec `sbx` : le vrai `sbx run --display`, la network policy et la connexion de Claude Code depuis la sandbox.
