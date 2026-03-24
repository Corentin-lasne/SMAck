# run.py - Simulation Runner Guide

Le fichier `run.py` fournit une interface en ligne de commande complète pour lancer les simulations avec logs de debug, configuration flexible et support du batch running.

## Démarrage rapide

### Mode par défaut (single run avec logs de debug)
```bash
python run.py
```
Lance une simulation standard avec:
- 3 agents de chaque couleur (green, yellow, red)
- Déchets initiaux: 6 green, 3 yellow, 5 red
- 40 étapes
- **Logs debug ACTIVÉS** pour voir la communication entre agents

### Avec nombre de pas personnalisé
```bash
python run.py --steps 100
```

### Avec une graine fixe (reproducibilité)
```bash
python run.py --seed 42
```

### Désactiver les logs debug
```bash
python run.py --no-debug
```

---

## Modes de fonctionnement

### 1. Mode Single Run (par défaut)

Lance une seule simulation avec visualisation des logs.

#### Options disponibles:

```bash
python run.py \
  --steps 80 \
  --seed 42 \
  --green-agents 4 \
  --yellow-agents 3 \
  --red-agents 3 \
  --green-waste 8 \
  --yellow-waste 2 \
  --red-waste 4
```

**Paramètres:**
- `--steps N`: Nombre d'étapes (défaut: 40)
- `--seed N`: Graine aléatoire (défaut: None = aléatoire)
- `--debug / --no-debug`: Activer/désactiver les logs (défaut: activé)
- `--green-agents N`: Nombre d'agents verts (défaut: 3)
- `--yellow-agents N`: Nombre d'agents jaunes (défaut: 3)  
- `--red-agents N`: Nombre d'agents rouges (défaut: 3)
- `--green-waste N`: Déchets verts initiaux (défaut: 6)
- `--yellow-waste N`: Déchets jaunes initiaux (défaut: 3)
- `--red-waste N`: Déchets rouges initiaux (défaut: 5)

**Exemple - Tester la communication yellow→red:**
```bash
python run.py --steps 50 --seed 42 --debug --yellow-agents 3 --red-agents 3 --yellow-waste 3 --green-agents 0 --green-waste 0
```

---

### 2. Mode Batch (parameter sweep)

Lance plusieurs simulations avec variations de paramètres. Utile pour l'exploration systématique et l'analyse statistique.

#### Lancement batch standard:
```bash
python run.py --batch --iterations 10 --steps 100
```

Cela lance un **parameter sweep** par défaut qui varie:
- `n_yellow_agents`: [2, 3, 4]
- `n_red_agents`: [2, 3, 4]

**Résultat:** 3×3×10 = **90 simulations** (9 combinaisons × 10 itérations)

#### Sauvegarder les résultats en CSV:
```bash
python run.py --batch --iterations 20 --output results_batch.csv
```

Crée un fichier `results_batch.csv` contenant:
- Paramètres de chaque run
- Statistiques finales (déchets restants, robots vides, etc.)
- Graine aléatoire utilisée

#### Utiliser dans Python pour analyse:
```python
import pandas as pd

# Charger les résultats
df = pd.read_csv("results_batch.csv")

# Filtrer par nombre d'agents jaunes
yellow_2 = df[df['n_yellow_agents'] == 2]

# Calculer la moyenne des déchets restants
print(f"Moyenne déchets restants: {yellow_2['waste_remaining'].mean()}")

# Visualiser
import seaborn as sns
sns.lineplot(data=df, x='n_yellow_agents', y='red_waste_disposed', hue='n_red_agents')
```

---

## Affichage des logs DEBUG

Quand le mode debug est **activé** (`--debug` ou par défaut en single run), vous verrez des logs comme:

```
[DEBUG][step=2][agent=5][yellow] QUERY_SENT {'query_id': 1, 'to_role': 'red', 'waste_type': 'yellow', 'waste_id': 'W_1'}
[DEBUG][step=2][agent=7][red] QUERY_RECEIVED {'query_id': 1, 'from_agent': 5, 'locked': False}
[DEBUG][step=2][agent=7][red] QUERY_ACCEPT_REPLYING {'query_id': 1, 'agent_pos': (18, 9)}
[DEBUG][step=3][agent=5][yellow] QUERY_REPLY_RECEIVED {'query_id': 1, 'from_agent': 7, 'from_pos': (18, 9), 'num_replies_so_far': 1}
[DEBUG][step=3][agent=5][yellow] TASK_ASSIGNMENT_SENT {'to_agent': 7, 'waste_type': 'yellow', 'waste_id': 'W_1'}
[DEBUG][step=3][agent=7][red] TASK_ASSIGNMENT_RECEIVED {'from_agent': 5, 'pos': (7, 9), 'waste_type': 'yellow', 'waste_id': 'W_1'}
[DEBUG][step=3][agent=7][red] TASK_ASSIGNMENT_ACTIVE {'waste_type': 'yellow', 'waste_id': 'W_1'}
[DEBUG][step=3][agent=5][yellow] LOCK_SENT {'to_role': 'red', 'pos': (7, 9), 'waste_type': 'yellow', 'waste_id': 'W_1', 'reserved_for': 7}
[DEBUG][step=3][agent=7][red] LOCK_RECEIVED {'pos': (7, 9), 'waste_type': 'yellow', 'waste_id': 'W_1', 'from_agent': 5, 'reserved_for': 7}
[DEBUG][step=3][agent=7][red] LOCK_REGISTERED {'pos': (7, 9), 'reserved_for': 7, 'my_id': 7, 'i_am_reserved': True}
```

**Événements clés à observer:**

1. `QUERY_SENT` - Agent jaune envoie une query à red
2. `QUERY_RECEIVED` - Agent rouge reçoit la query
3. `QUERY_ACCEPT_REPLYING` - Agent rouge accepte de répondre
4. `QUERY_REPLY_RECEIVED` - Agent jaune reçoit la(les) réponse(s)
5. `TASK_ASSIGNMENT_SENT` - Agent jaune envoie l'assignement de tâche
6. `TASK_ASSIGNMENT_RECEIVED` - Agent rouge reçoit et accepte la tâche
7. `LOCK_SENT` - Agent jaune crée un verrou sur le déchet
8. `LOCK_RECEIVED` / `LOCK_REGISTERED` - Agent rouge reçoit et enregistre le verrou

#### Vérification rapide du handover:
- ✅ Query est bien envoyée
- ✅ Red agent reçoit et répond
- ✅ Assignment arrive et est accepté
- ✅ Lock est créé et le destinataire est marqué comme `reserved_for`

---

## Exemples complets

### Test 1: Lancer 50 étapes avec logs
```bash
python run.py --steps 50 --seed 123
```

### Test 2: Reproductibilité - même graine = même résultat
```bash
python run.py --seed 42 > run_seed42.log
python run.py --seed 42 > run_seed42_repeat.log
# Les deux fichiers devraient être identiques
```

### Test 3: Batch focalisé sur yellow→red
```bash
python run.py --batch \
  --iterations 15 \
  --steps 80 \
  --output yellow_red_analysis.csv
```

Puis analyser en Python:
```python
import pandas as pd
import seaborn as sns

df = pd.read_csv("yellow_red_analysis.csv")
sns.scatterplot(data=df, x='n_yellow_agents', y='red_waste_disposed', hue='n_red_agents', size='waste_remaining')
plt.show()
```

### Test 4: Run sans debug (plus rapide)
```bash
python run.py --no-debug --steps 200 --iterations 1
```

---

## Aide en ligne
```bash
python run.py --help
```

---

## Avec Solara (serveur interactif)

Pour voir la **visualisation 3D en direct**, utilise toujours:
```bash
solara run server.py
```

`run.py` est complémentaire pour:
- Lancer des **simulations sans UI** (ci-haut)
- **Collecter des data** en batch
- **Debugger** avec les logs
- **Automatiser** des tests

