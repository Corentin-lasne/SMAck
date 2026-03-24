"""Simulation world objects placed on the grid.

Contains:
- `radioactivityAgent`: static background marker used to encode zone hazard level
- `wasteAgent`: collectible/transformable waste token
"""

from mesa import Agent

import random

class radioactivityAgent(Agent):
    """Static marker describing radioactivity for one grid cell.

    The model places one instance per cell. Agents do not interact with it directly,
    but the visualization uses it to highlight zones and disposal location.
    """
    def __init__(self, model, zone):
        super().__init__(model)
        if zone == 1 :
            self.radioactivity = random.uniform(0,0.33)
        elif zone == 2 :
            self.radioactivity = random.uniform(0.33,0.66)
        elif zone == 3 :
            self.radioactivity = random.uniform(0.66,1)
        # Waste Disposal Zone
        else :
            self.radioactivity = 10

class wasteAgent(Agent):
    """Passive waste token carried, dropped, and transformed by robot agents."""
    def __init__(self, model, waste_type, waste_id=None):
        super().__init__(model)
        self.waste_type = waste_type
        self.waste_id = waste_id if waste_id is not None else model.make_waste_id()
