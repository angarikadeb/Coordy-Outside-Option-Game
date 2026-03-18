# Coordy-Outside-Option-Game
This is for the specific game, 'traits as outside options'

## How to use

  

There are two CLI scripts. Run them in this order:

  

### 1) Assign players to teams

  

This reads an input players JSON and assigns each player to a team (`red` / `blue`) according to the chosen proportion.

  

Example:


```bash

python assign_teams_cli.py \

  --players-input outputs/players_input.json \

  --red-prop 0.5 \

  --seed 123 \

  --outdir outputs \

  --file-prefix test
```


Output:  

outputs/test_players_output.json

outputs/test_meta.json

### 2) Generate pairings

  

This reads the players_output.json file and generates the pairing schedule JSON for the experiment.

  

Example:


```bash
python generate_pairs_cli.py \

  --players outputs/test_players_output.json \

  --intro-rounds 8 \

  --rounds 20 \

  --block-size 5 \

  --seed 123 \

  --outdir outputs \

  --file-prefix test
```
 

  Output:  

outputs/test_pairing.json

outputs/test_meta.json
#### Notes


--seed makes the result reproducible.

  

--intro-rounds adds Instruction_1, Instruction_2, etc. at the beginning.

  

--block-size controls how many playing rounds happen before change_partner.

  

--rounds is the number of playing rounds.